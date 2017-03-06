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

config={"SMTP_HOST":"localhost",
        "EMAIL_FROM":"test@localhost",
        "TEMPLATES_DIR":"tests/templates",
        "GH_OAUTH_TOKEN":"foo",
        "mls": "tests/mls.json"
        }

class SpoofDatetime(datetime.datetime):
    @classmethod
    def now(cls):
        return cls(2016,11,16,14,30,0)

class SendEmailGithubTests(unittest.TestCase):
    def setUp(self):
        datetime.datetime = SpoofDatetime
        responses.add(responses.GET, 'https://api.github.com/repos/w3c/webrtc-pc/events',
                      body=io.open('tests/repo1-events-1.json').read(), content_type='application/json', adding_headers={'link':'<https://api.github.com/repos/w3c/webrtc-pc/events/2>;rel="next"'})
        responses.add(responses.GET, 'https://api.github.com/repos/w3c/webrtc-pc/events/2',
                      body=io.open('tests/repo1-events-2.json').read(), content_type='application/json')
        responses.add(responses.GET, 'https://api.github.com/repos/w3c/webrtc-pc/issues/events',
                      body=io.open('tests/repo1-issues.json').read(), content_type='application/json')

    @responses.activate
    @patch("smtplib.SMTP")
    def test_weekly_digest(self, mock_smtp):
        instance = mock_smtp.return_value
        refs = [{"dom@localhost":"tests/digest-weekly.msg"}, {"dom@localhost":"tests/digest-weekly-filtered.msg"}]
        sendDigest(config, "Wednesday")
        self.assertEqual(instance.sendmail.call_count, len(refs))
        counter = 0
        for (name, args, kwargs) in instance.sendmail.mock_calls:
            self.assertEqual(args[0], u"test@localhost")
            self.assertIn(args[1][0], refs[counter])
            msg = io.open(refs[counter][args[1][0]]).read()

            self.maxDiff = None
            import email
            sent_email = email.message_from_string(args[2])
            sent_headers = args[2].split("\n\n")[0]
            sent_body = sent_email.get_payload(decode=True).decode('utf-8')
            ref_headers = msg.split("\n\n")[0]
            ref_body = "\n".join(msg.split("\n\n")[1:])
            self.assertMultiLineEqual(sent_headers, ref_headers)
            self.assertMultiLineEqual(sent_body, ref_body)
            counter = counter + 1

if __name__ == '__main__':
    unittest.main()
