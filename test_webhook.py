from mock import patch, call
import unittest
import smtplib
import json
import requests
import io
import quopri
from test_server import Server

# depends on mocking responses to request via https://github.com/dropbox/responses



class SendEmailGithubTests(unittest.TestCase):

    def setUp(self):
        self.t = Server()
        self.t.start()

    def test_ignore_get(self):
        rv = requests.get('http://localhost:8000/')
        assert ' Nothing to see here, move along ...' == rv.text

    def test_ip_check_ok(self):
        rv = requests.post('http://localhost:8000/', headers={'X-GitHub-Event': 'ping', 'Remote-Addr': '127.0.0.1'})
        data = rv.json()
        assert data["msg"] == "Hi!"
        assert rv.status_code == 200

    def test_ip_check_403(self):
        rv = requests.post('http://localhost:8000/', headers={'X-GitHub-Event':'ping', 'Remote-Addr': '128.0.0.1'})
        assert rv.status_code == 403


    def do_operation(self, operation, jsonf, msgf, mock_smtp):
        data = io.open(jsonf).read()
        rv = requests.post('http://localhost:8000/', headers={'X-GitHub-Event': operation}, data=data)
        instance = mock_smtp.return_value
        assert rv.status_code == 200
        self.assertEqual(instance.sendmail.call_count, 1)
        msg = io.open(msgf).read()
        name, args, kwargs = instance.sendmail.mock_calls[0]
        self.assertEqual(args[0], u"test@localhost")
        self.assertEqual(args[1], [u"dom@localhost"])
        self.maxDiff = None
        import email
        import sys
        sent_email = email.message_from_string(args[2])
        sent_headers = args[2].split("\n\n")[0]
        sent_body = sent_email.get_payload(decode=True)
        ref_headers = msg.split("\n\n")[0]
        ref_body = "\n".join(msg.split("\n\n")[1:])
        self.assertMultiLineEqual(sent_headers, ref_headers)
        self.assertMultiLineEqual(sent_body, ref_body)

    @patch("smtplib.SMTP")
    def test_push_notif(self, mock_smtp):
        self.do_operation("push", "tests/push-notif.json", "tests/push-notif.msg", mock_smtp)

    @patch("smtplib.SMTP")
    def test_issue_notif(self, mock_smtp):
        self.do_operation("issues", "tests/issue-notif.json", "tests/issue-notif.msg", mock_smtp)

    @patch("smtplib.SMTP")
    def test_issue_comment_notif(self, mock_smtp):
        self.do_operation("issue_comment", "tests/issue-comment-notif.json", "tests/issue-comment-notif.msg", mock_smtp)

    @patch("smtplib.SMTP")
    def test_pull_notif(self, mock_smtp):
        self.do_operation("pull_request", "tests/pull-notif.json", "tests/pull-notif.msg", mock_smtp)


    @patch("smtplib.SMTP")
    def test_unavailable_template(self, mock_smtp):
        data = io.open("tests/push-notif.json").read()
        rv = requests.post('http://localhost:8000/', headers={'X-GitHub-Event': "foobar"}, data=data)
        instance = mock_smtp.return_value
        import sys
        sys.stderr.write(str(rv.status_code))
        assert rv.status_code == 500
        self.assertEqual(instance.sendmail.call_count, 0)

    def tearDown(self):
        self.t.terminate()

if __name__ == '__main__':
    unittest.main()
