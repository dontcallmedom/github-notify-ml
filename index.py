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
from email.mime.nonmultipart import MIMENonMultipart
import email.charset
from flask import Flask, request, abort
import pystache

app = Flask(__name__)

cs=email.charset.Charset('utf-8')
cs.body_encoding = email.charset.QP

# TODO: move to some general config
DEFAULT_FROM="sysbot+gh@w3.org"
HOST="0.0.0.0"
SMTP_HOST="localhost"
LOG_FILE="log"

def validate_repos():
    # TODO: Check that all configured repos have events with matching templates?
    # that they all have an email.to field?
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

def refevent(event, payload):
    if event in ["issues.reopened", "issues.closed", "issue_comment.created"]:
        return ("issues.opened", payload["issue"]["id"])
    elif event in ["pull_request.closed", "pull_request.reopened",
                   "pull_request.synchronized",
                   "pull_request_review_comment.created"]:
        return ("pull_request.opened", payload["pull_request"]["id"])
    return (None,None)


@app.route("/", methods=['GET', 'POST'])
def index():
    # Store the IP address blocks that github uses for hook requests.
    hook_blocks = requests.get('https://api.github.com/meta').json()['hooks']

    if request.method == 'GET':
        return ' Nothing to see here, move along ...'

    elif request.method == 'POST':
        # Check if the POST request if from github.com
        for block in hook_blocks:
            ip = ipaddress.ip_address(u'%s' % request.remote_addr)
            if ipaddress.ip_address(ip) in ipaddress.ip_network(block):
                break #the remote_addr is within the network range of github
        else:
            abort(403)

        event = request.headers.get('X-GitHub-Event', None)
        if event == "ping":
            return json.dumps({'msg': 'Hi!'})

        repos = json.loads(io.open(app.config['repos'], 'r').read())
        payload = json.loads(request.data)
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
            if event not in repo['events'] and event not in repo['branches'].get(repo_meta['branch'], []):
                return json.dumps({'msg': 'event type %s not managed for %s' % (event, '{owner}/{name}'.format(**repo_meta)) })
            try:
                template = io.open("templates/repos/{owner}/{name}/%s".format(**repo_meta) % event).read()
            except IOError:
                try:
                    template = io.open("templates/generic/%s" % event).read()
                except IOError:
                    return json.dumps({'msg': 'no template defined for event %s' % event})
            body = pystache.render(template, payload)
            subject, dummy, body = body.partition('\n')
            msg = MIMENonMultipart("text", "plain", charset="utf-8")
            msg.set_payload(body, charset=cs)
            frum = repo.get("email", {}).get("from", DEFAULT_FROM)
            msgid = "<%s-%s-%s>" % (event, event_id(event, payload), frum)
            (ref_event, ref_id) = refevent(event, payload)
            inreplyto = None
            if ref_event and ref_id:
                inreplyto = "<%s-%s-%s>" % (ref_event, ref_id, frum)

            too = repo.get("email", {}).get("to")

            frum_name = requests.get(payload['sender']['url']).json()['name']

            msg['From'] = u"%s via GitHub <%s>" % (frum_name, frum)
            msg['To'] = too
            msg['Subject'] = subject
            msg['Message-ID'] = msgid
            if inreplyto:
                msg['In-Reply-To'] = inreplyto
            s = smtplib.SMTP(SMTP_HOST)
            s.sendmail(frum, [too], msg.as_string())
            s.quit()
            return json.dumps({'msg': 'mail sent to %s with subject %s' % (too, subject)})
        return 'OK'

if __name__ == "__main__":
    validate_repos()
    import logging
    from logging.handlers import RotatingFileHandler
    handler = RotatingFileHandler(LOG_FILE, maxBytes=10000, backupCount=1)
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)
    try:
        port_number = int(sys.argv[1])
    except:
        port_number = 80
    is_dev = os.environ.get('ENV', None) == 'dev'
    if os.environ.get('USE_PROXYFIX', None) == 'true':
	from werkzeug.contrib.fixers import ProxyFix
	app.wsgi_app = ProxyFix(app.wsgi_app)

    app.config["repos"] = "repos.json"
    app.run(host='0.0.0.0', port=port_number, debug=is_dev)
