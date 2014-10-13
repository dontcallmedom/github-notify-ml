from mock import patch, call
import unittest
import smtplib
from index import app
from flask import request
import json
import responses
import io

# depends on mocking responses to request via https://github.com/dropbox/responses

class SendEmailGithubTests(unittest.TestCase):
    def setUp(self):
        app.config['repos']='tests/repos.json'
        self.app = app.test_client()
        responses.add(responses.GET, 'https://api.github.com/meta',
                      body='{"hooks":["127.0.0.0/8"]}', content_type='application/json')


    def test_ignore_get(self):
        rv = self.app.get('/')
        assert ' Nothing to see here, move along ...' == rv.data

    @responses.activate
    def test_ip_check_ok(self):
        rv = self.app.post('/', headers=[('X-GitHub-Event', 'ping')], environ_base={'REMOTE_ADDR': '127.0.0.1'})
        data = json.loads(rv.data)
        assert data["msg"] == "Hi!"
        assert rv.status_code == 200

    @responses.activate
    def test_ip_check_403(self):
        rv = self.app.post('/', headers=[('X-GitHub-Event', 'ping')], environ_base={'REMOTE_ADDR': '128.0.0.1'})
        assert rv.status_code == 403


    def do_operation(self, operation, jsonf, msgf, mock_smtp):
        data = io.open(jsonf).read()
        rv = self.app.post('/', headers=[('X-GitHub-Event', operation)], environ_base={'REMOTE_ADDR': '127.0.0.1'}, data=data)
        instance = mock_smtp.return_value
        assert rv.status_code == 200
        self.assertEqual(instance.sendmail.call_count, 1)
        import sys
        msg = io.open(msgf).read()
        self.assertEqual(
                instance.sendmail.mock_calls,
                [call("test@localhost", ["dom@localhost"], msg)]
            )

    @patch("smtplib.SMTP")
    @responses.activate
    def test_push_notif(self, mock_smtp):
        self.do_operation("push", "tests/push-notif.json", "tests/push-notif.msg", mock_smtp)

    @patch("smtplib.SMTP")
    @responses.activate
    def test_issue_notif(self, mock_smtp):
        self.do_operation("issues", "tests/issue-notif.json", "tests/issue-notif.msg", mock_smtp)



if __name__ == '__main__':
    unittest.main()
