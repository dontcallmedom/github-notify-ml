from mock import patch, call
import email
import unittest
import smtplib
import json
import requests
import io
import sys
from test_server import Server

# depends on mocking responses to request via https://github.com/dropbox/responses


class SendEmailGithubTests(unittest.TestCase):
    def setUp(self):
        self.t = Server()
        self.t.start()

    @staticmethod
    def read_file(filename):
        with io.open(filename) as filehandle:
            contents = filehandle.read()
        return contents

    def test_ignore_get(self):
        rv = requests.get("http://localhost:8000/")
        assert " Nothing to see here, move along ..." == rv.text

    def test_ip_check_ok(self):
        rv = requests.post(
            "http://localhost:8000/",
            headers={"X-GitHub-Event": "ping", "Remote-Addr": "127.0.0.1"},
        )
        data = rv.json()
        assert data["msg"] == "Hi!"
        assert rv.status_code == 200

    def test_ip_check_403(self):
        rv = requests.post(
            "http://localhost:8000/",
            headers={"X-GitHub-Event": "ping", "Remote-Addr": "128.0.0.1"},
        )
        assert rv.status_code == 403

    @patch("smtplib.SMTP")
    def test_w3c_tr_published(self, mock_smtp):
        data = self.read_file("tests/trpublished-notif.json")
        rv = requests.post(
            "http://localhost:8000/",
            headers={"X-W3C-Webhook": "https://example.org"},
            data=data,
        )
        refs = {"dom@localhost": "tests/trpublished-notif.msg"}
        instance = mock_smtp.return_value
        self.assert_operation_results(rv, instance, refs)

    def do_gh_operation(self, operation, jsonf, refs, mock_smtp):
        with io.open(jsonf) as filehandle:
            data = filehandle.read()
        rv = requests.post(
            "http://localhost:8000/", headers={"X-GitHub-Event": operation}, data=data
        )
        instance = mock_smtp.return_value
        self.assert_operation_results(rv, instance, refs)

    def assert_operation_results(self, rv, instance, refs):
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(instance.sendmail.call_count, len(refs))
        i = 0
        for (name, args, kwargs) in instance.sendmail.mock_calls:
            self.assertEqual(args[0], "test@localhost")
            self.assertIn(args[1][0], refs)
            msg = self.read_file(refs[args[1][0]])
            self.maxDiff = None
            import email

            sent_email = email.message_from_string(args[2], policy=email.policy.default)
            sent_headers = args[2].split("\n\n")[0]
            sent_body = sent_email.get_content()
            ref_headers = msg.split("\n\n")[0]
            ref_body = "\n".join(msg.split("\n\n")[1:])
            self.assertMultiLineEqual(sent_headers, ref_headers)
            self.assertMultiLineEqual(sent_body, ref_body)

    @patch("smtplib.SMTP")
    def test_repo_created_notif(self, mock_smtp):
        self.do_gh_operation(
            "repository",
            "tests/repo-created.json",
            {"dom@localhost": "tests/repo-created.msg"},
            mock_smtp,
        )

    @patch("smtplib.SMTP")
    def test_repo_transferred_notif(self, mock_smtp):
        self.do_gh_operation(
            "repository",
            "tests/repo-transferred.json",
            {"dom@localhost": "tests/repo-transferred.msg"},
            mock_smtp,
        )

    @patch("smtplib.SMTP")
    def test_repo_deleted_notif(self, mock_smtp):
        self.do_gh_operation(
            "repository",
            "tests/repo-deleted.json",
            {"dom@localhost": "tests/repo-deleted.msg"},
            mock_smtp,
        )

    @patch("smtplib.SMTP")
    def test_push_notif(self, mock_smtp):
        self.do_gh_operation(
            "push",
            "tests/push-notif.json",
            {"dom@localhost": "tests/push-notif.msg"},
            mock_smtp,
        )

    @patch("smtplib.SMTP")
    def test_issue_notif(self, mock_smtp):
        self.do_gh_operation(
            "issues",
            "tests/issue-notif.json",
            {
                "dom@localhost": "tests/issue-notif.msg",
                "log@localhost": "tests/issue-notif-log.msg",
            },
            mock_smtp,
        )

    @patch("smtplib.SMTP")
    def test_issue_comment_notif(self, mock_smtp):
        self.do_gh_operation(
            "issue_comment",
            "tests/issue-comment-notif.json",
            {"dom@localhost": "tests/issue-comment-notif.msg"},
            mock_smtp,
        )

    @patch("smtplib.SMTP")
    def test_pull_request_comment_notif(self, mock_smtp):
        self.do_gh_operation(
            "issue_comment",
            "tests/pull_request-comment-notif.json",
            {"dom@localhost": "tests/pull_request-comment-notif.msg"},
            mock_smtp,
        )

    @patch("smtplib.SMTP")
    def test_pull_notif(self, mock_smtp):
        self.do_gh_operation(
            "pull_request",
            "tests/pull-notif.json",
            {"dom@localhost": "tests/pull-notif.msg"},
            mock_smtp,
        )

    @patch("smtplib.SMTP")
    def test_pull_closed_notif(self, mock_smtp):
        self.do_gh_operation(
            "pull_request",
            "tests/pull-merged.json",
            {"dom@localhost": "tests/pull-merged.msg"},
            mock_smtp,
        )

    @patch("smtplib.SMTP")
    def test_pull_labeled_notif(self, mock_smtp):
        self.do_gh_operation(
            "pull_request",
            "tests/pull-labeled.json",
            {"dom@localhost": "tests/pull-labeled.msg"},
            mock_smtp,
        )

    @patch("smtplib.SMTP")
    def test_unavailable_template(self, mock_smtp):
        data = self.read_file("tests/push-notif.json")
        rv = requests.post(
            "http://localhost:8000/", headers={"X-GitHub-Event": "foobar"}, data=data
        )
        instance = mock_smtp.return_value
        self.assertEqual(rv.status_code, 500)
        self.assertEqual(instance.sendmail.call_count, 0)

    def tearDown(self):
        self.t.terminate()


if __name__ == "__main__":
    unittest.main()
