#!/usr/bin/env python
# started from
# https://github.com/razius/flask-github-webhook/blob/master/index.py
import io
import os
import re
import sys
import json
import subprocess
import requests
import ipaddress
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from email.generator import Generator
import email.charset
import email.header
import pystache
import textwrap
from cStringIO import StringIO

email.charset.add_charset('utf-8', email.charset.QP, email.charset.QP, 'utf-8')

class InvalidConfiguration(Exception):
    pass

def validate_repos(config):
    # TODO: Check that all configured repos have events with matching templates?
    # that they all have an email.to field?
    repos = json.loads(io.open(config['repos'], 'r').read())
    import os.path
    for (repo,data) in repos.iteritems():
        for e in data["events"]:
            generic_template = config['TEMPLATES_DIR'] + '/generic/' + e
            specific_template = config['TEMPLATES_DIR'] + '/repos/' + repo + '/' + e
            if not (os.path.isfile(generic_template)
            or os.path.isfile(specific_template)):
                raise InvalidConfiguration("No template matching event %s defined in %s in %s (looked at %s and %s)" % (e, config['repos'], repo, generic_template, specific_template))
    pass

def event_id(event, payload):
    if event.split(".")[0] == "issues":
        return payload["issue"]["id"]
    elif event.split(".")[0] == "issue_comment":
        return payload["comment"]["id"]
    elif event == "push":
        return payload["head_commit"]["id"]
    elif event.split(".")[0] == "pull_request":
        return payload["pull_request"]["id"]

def event_timestamp(event, payload):
    def timestamp(date):
        from dateutil import parser
        import calendar
        try:
            return calendar.timegm(parser.parse(date).utctimetuple())
        except:
            return date
    ts = None
    if event == "push":
        ts = payload["repository"]["pushed_at"]
    elif event == "issue_comment.created":
        ts = payload["comment"]["created_at"]
    elif event.split(".")[0] in ["issues", "pull_request"]:
        action = event.split(".")[1]
        key = "issue" if event.split(".")[0] == "issues" else "pull_request"
        if action == "opened":
            ts = payload[key]["created_at"]
        elif action == "closed":
            ts = payload[key]["closed_at"]
        elif action == "reopened" or action == "synchronize":
            ts = payload[key]["updated_at"]
    if ts:
        return timestamp(ts)

def refevent(event, payload):
    if event in ["issues.reopened", "issues.closed", "issue_comment.created"]:
        return ("issues.opened", payload["issue"]["id"])
    elif event in ["pull_request.closed", "pull_request.reopened",
                   "pull_request.synchronized",
                   "pull_request_review_comment.created"]:
        return ("pull_request.opened", payload["pull_request"]["id"])
    return (None,None)


def serveRequest(config, postbody):
    request_method = os.environ.get('REQUEST_METHOD', "GET")
    remote_addr = os.environ.get('HTTP_X_FORWARDED_FOR', os.environ.get('REMOTE_ADDR'))
    # Store the IP address blocks that github uses for hook requests.
    hook_blocks = requests.get('https://api.github.com/meta').json()['hooks']
    output = ""

    if request_method == 'GET':
        output += "Content-Type: text/plain; charset=utf-8\n\n"
        output += " Nothing to see here, move along ..."
        return output
    elif request_method == 'POST':
        # Check if the POST request if from github.com
        for block in hook_blocks:
            ip = ipaddress.ip_address(u'%s' % remote_addr)
            if ipaddress.ip_address(ip) in ipaddress.ip_network(block):
                break #the remote_addr is within the network range of github
        else:
            output += "Status: 403 Unrecognized IP\n"
            output += "Content-Type: application/json\n\n"
            output += json.dumps({'msg': 'Unrecognized IP address', 'ip': remote_addr})
            return output

        event = os.environ.get('HTTP_X_GITHUB_EVENT', None)
        if event == "ping":
            output += "Content-Type: application/json\n\n"
            output += json.dumps({'msg': 'Hi!'})
            return output
        repos = json.loads(io.open(config['repos'], 'r').read())
        payload = json.loads(postbody)
        repo_meta = {
	    'name': payload['repository'].get('name')
	    }
        repo_meta['owner'] = payload['repository']['owner'].get('name', payload['repository']['owner'].get('login'))
	match = re.match(r"refs/heads/(?P<branch>.*)", payload.get('ref', ''))
	if match:
	    repo_meta['branch'] = match.groupdict()['branch']
        repo = repos.get('{owner}/{name}'.format(**repo_meta), None)
        if repo and repo.get('email', None):
            if payload.get("action", False):
                event = event + "." + payload['action']
            if event not in repo['events'] and (not repo_meta.has_key("branch") or event not in repo.get('branches', {}).get(repo_meta['branch'], [])):
                output += "Status: 400 Unhandled event\n"
                output += "Content-Type: application/json\n\n"
                output += json.dumps({'msg': 'event type %s not managed for %s' % (event, '{owner}/{name}'.format(**repo_meta)) })
                return output
            try:
                template = io.open(config["TEMPLATES_DIR"] + "/repos/{owner}/{name}/%s".format(**repo_meta) % event).read()
            except IOError:
                try:
                    template = io.open(config["TEMPLATES_DIR"] + "/generic/%s" % event).read()
                except IOError:
                    output += "Status: 500 No matching template\n"
                    output += "Content-Type: application/json\n\n"
                    output += json.dumps({'msg': 'no template defined for event %s' % event})
                    return output
            body = pystache.render(template, payload)
            subject, dummy, body = body.partition('\n')
            paragraphs = body.splitlines()
            wrapper = textwrap.TextWrapper( break_long_words=False, break_on_hyphens=False,  drop_whitespace=False)
            body = "\n".join(map(wrapper.fill, paragraphs))
            msg = MIMEText("text", "plain", _charset="utf-8")
            msg.set_payload(body, charset='utf-8')
            frum = repo.get("email", {}).get("from", config["EMAIL_FROM"])
            msgid = "<%s-%s-%s-%s>" % (event, event_id(event, payload),
                                       event_timestamp(event, payload), frum)
            (ref_event, ref_id) = refevent(event, payload)
            inreplyto = None
            if ref_event and ref_id:
                inreplyto = "<%s-%s-%s-%s>" % (ref_event, ref_id,
                                            event_timestamp(ref_event, payload),
                                            frum)

            too = repo.get("email", {}).get("to").split(",")
            headers = {}
            frum_name = ""
            readable_frum = email.header.Header(charset='utf8', header_name='From')
            if config.get("GH_OAUTH_TOKEN", False):
                headers['Authorization']="token %s" % (config["GH_OAUTH_TOKEN"])
                frum_name = requests.get(payload['sender']['url'],
                                     headers=headers
                                     ).json().get('name', payload['sender']['login'])
                readable_frum.append('%s via GitHub' % (frum_name))

            readable_frum.append('<%s>' % (frum), charset='us-ascii')
            msg['From'] = readable_frum
            msg['To'] = ",".join(too)
            msg['Subject'] = Header(subject, 'utf-8')
            msg['Message-ID'] = msgid
            if inreplyto:
                msg['In-Reply-To'] = inreplyto
            s = smtplib.SMTP(config["SMTP_HOST"])
            # from http://wordeology.com/computer/how-to-send-good-unicode-email-with-python.html
            m = StringIO()
            g = Generator(m, False)
            g.flatten(msg)
            s.sendmail(frum, too, m.getvalue())
            s.quit()
            output += "Content-Type: application/json\n\n"
            output += json.dumps({'msg': 'mail sent to %s with subject %s' % (too, subject)})
            return output
        output += "Content-Type: text/plain; charset=utf-8\n\n"
        output += 'OK'
        return output

if __name__ == "__main__":
    config = json.loads(io.open('instance/config.json').read())
    config["repos"] = "repos.json"
    validate_repos(config)
    if os.environ.has_key('SCRIPT_NAME'):
        print serveRequest(config, sys.stdin.read())

