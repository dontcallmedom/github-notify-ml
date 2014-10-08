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
from flask import Flask, request, abort
import pystache

app = Flask(__name__)

# TODO: move to some general config
DEFAULT_FROM="sysbot+gh@w3.org"
HOST="0.0.0.0"
SMTP_HOST="localhost"
LOG_FILE="log"

def validate_repos():
    # TODO: Check that all configured repos have events with matching templates?
    # that they all have an email.to field?
    pass

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


        if request.headers.get('X-GitHub-Event') == "ping":
            return json.dumps({'msg': 'Hi!'})

        repos = json.loads(io.open('repos.json', 'r').read())

        payload = json.loads(request.data)
        repo_meta = {
	    'name': payload['repository']['name'],
	    'owner': payload['repository']['owner']['name'],
	    }
	match = re.match(r"refs/heads/(?P<branch>.*)", payload['ref'])
	if match:
	    repo_meta['branch'] = match.groupdict()['branch']
        repo = repos.get('{owner}/{name}'.format(**repo_meta), None)
        if repo and repo.get('email', None):
            event = request.headers.get('X-GitHub-Event', None)
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
            msg = MIMEText(body)
            frum = repo.get("email", {}).get("from", DEFAULT_FROM)
            too = repo.get("email", {}).get("to")
            msg['From'] = frum
            msg['To'] = too
            msg['Subject'] = subject

            s = smtplib.SMTP(SMTP_HOST)
            s.sendmail(frum, [too], msg.as_string())
            s.quit()
            return json.dumps({'msg': 'mail sent to %s with subject %s' % (too, subject)})
        return 'OK'

if __name__ == "__main__":
    validate_repos()
    try:
        port_number = int(sys.argv[1])
    except:
        port_number = 80
    is_dev = os.environ.get('ENV', None) == 'dev'
    if os.environ.get('USE_PROXYFIX', None) == 'true':
	from werkzeug.contrib.fixers import ProxyFix
	app.wsgi_app = ProxyFix(app.wsgi_app)
    import logging
    from logging.handlers import RotatingFileHandler
    handler = RotatingFileHandler(LOG_FILE, maxBytes=10000, backupCount=1)
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)
    app.run(host='0.0.0.0', port=port_number, debug=is_dev)
