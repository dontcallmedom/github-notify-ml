from mock import patch, call
import unittest
import responses
import smtplib
import json
import requests
import io
import sys
import datetime
from index import sendDigest

# depends on mocking responses to request via https://github.com/dropbox/responses

config = {
    "SMTP_HOST": "localhost",
    "EMAIL_FROM": "test@localhost",
    "TEMPLATES_DIR": "tests/templates",
    "DIGEST_SENDER":"W3C Webmaster via GitHub API",
    "GH_OAUTH_TOKEN": "foo",
    "mls": "tests/mls.json",
    "SIGNATURE": "Sent with ♥"
}


class SpoofDatetime(datetime.datetime):
    @classmethod
    def now(cls):
        return cls(2016, 11, 16, 14, 30, 0)


class SendEmailGithubTests(unittest.TestCase):
    def setUp(self):
        datetime.datetime = SpoofDatetime
        responses.add(responses.GET, "https://api.github.com/repos/foo/bar", status=404)
        responses.add(
            responses.GET, "https://api.github.com/repos/foo/bar/events", status=404
        )
        responses.add(
            responses.GET,
            "https://api.github.com/repos/w3c/webrtc-pc",
            body=self.read_file("tests/repo1-data.json"),
            content_type="application/json",
        )
        responses.add(
            responses.GET,
            "https://api.github.com/repos/w3c/webrtc-pc/events",
            body=self.read_file("tests/repo1-events-1.json"),
            content_type="application/json",
            adding_headers={
                "link": '<https://api.github.com/repos/w3c/webrtc-pc/events/2>;rel="next"'
            },
        )
        responses.add(
            responses.GET,
            "https://api.github.com/repos/w3c/webrtc-pc/events/2",
            body=self.read_file("tests/repo1-events-2.json"),
            content_type="application/json",
        )
        responses.add(
            responses.GET,
            "https://api.github.com/repos/w3c/webrtc-pc/issues/events",
            body=self.read_file("tests/repo1-issues.json"),
            content_type="application/json",
        )
        responses.add(
            responses.GET,
            "https://api.github.com/repos/w3c/webcrypto",
            body=self.read_file("tests/repo2-data.json"),
            content_type="application/json",
        )
        responses.add(
            responses.GET,
            "https://api.github.com/repos/w3c/webcrypto/events",
            body=self.read_file("tests/repo2-events-1.json"),
            content_type="application/json",
        )
        responses.add(
            responses.GET,
            "https://w3c.github.io/validate-repos/rec-track-repos.json",
            body=self.read_file("tests/rec-repos.json"),
            content_type="application/json",
        )

    def parseReferenceMessage():
        return headers, body

    @staticmethod
    def read_file(filename):
        with io.open(filename) as filehandle:
            contents = filehandle.read()
        return contents

    @responses.activate
    @patch("smtplib.SMTP")
    def test_weekly_digest(self, mock_smtp):
        self.do_digest(
            "Wednesday",
            [
                {"dom@localhost": "tests/digest-weekly-allrepos.msg"},
                {"dom@localhost": "tests/digest-weekly.msg"},
                {"dom@localhost": "tests/digest-weekly-filtered.msg", "html": True},
                {"dom@localhost": "tests/digest-weekly-repofiltered.msg"},
            ],
            mock_smtp,
        )
        self.assertEqual(len(responses.calls), 6)


    @responses.activate
    @patch("smtplib.SMTP")
    def test_quarterly_summary(self, mock_smtp):
        self.do_digest(
            "quarterly", [{"dom@localhost": "tests/summary-quarterly.msg"}], mock_smtp
        )
        self.assertEqual(len(responses.calls), 2)

    def do_digest(self, period, refs, mock_smtp):
        import email

        instance = mock_smtp.return_value
        sendDigest(config, period)
        self.assertEqual(instance.sendmail.call_count, len(refs))
        counter = 0
        import pprint

        for (name, args, kwargs) in instance.sendmail.mock_calls:
            self.assertEqual(args[0], "test@localhost")
            self.assertIn(args[1][0], refs[counter])
            sent_email = email.message_from_string(args[2])
            sent_parts = []
            ref_parts = []
            ref_parts.append(self.read_file(refs[counter][args[1][0]]))
            if sent_email.is_multipart():
                sent_parts.append(
                    {
                        "headers": sent_email.get_payload(0)
                        .as_string()
                        .split("\n\n")[0],
                        "body": sent_email.get_payload(0)
                        .get_payload(decode=True)
                        .decode("utf-8"),
                    }
                )
                sent_parts.append(
                    {
                        "headers": sent_email.get_payload(1)
                        .as_string()
                        .split("\n\n")[0],
                        "body": sent_email.get_payload(1)
                        .get_payload(decode=True)
                        .decode("utf-8"),
                    }
                )
                if refs[counter].get("html", False):
                    ref_parts.append(
                        self.read_file(refs[counter][args[1][0]] + ".html")
                    )
            else:
                sent_parts.append(
                    {
                        "headers": args[2].split("\n\n")[0],
                        "body": sent_email.get_payload(decode=True).decode("utf-8"),
                    }
                )
            self.maxDiff = None
            for sent_part, ref_part in zip(sent_parts, ref_parts):
                # TODO: use partition
                ref_headers = ref_part.split("\n\n")[0]
                self.assertMultiLineEqual(sent_part["headers"], ref_headers)
                ref_body = "\n".join(ref_part.split("\n\n")[1:])
                self.assertMultiLineEqual(sent_part["body"], ref_body)
            counter = counter + 1

if __name__ == "__main__":
    unittest.main()
