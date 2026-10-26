#!/usr/bin/env python3
# Send a one-off test email using the same config and SMTP code as the digest.
#
# Usage (from the repo root, so instance/config.json resolves):
#   set -a; source instance/.env; set +a
#   python send-test-email.py you@example.com
import logging
import sys

from index import getConfig, sendMail

if len(sys.argv) != 2:
    sys.exit(f"usage: {sys.argv[0]} RECIPIENT")

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.DEBUG)

config = getConfig()
result = sendMail(
    config,
    [{"body": "Hi, this is a test email from github-notify-ml.\n", "subtype": "plain"}],
    config["EMAIL_FROM"],
    "github-notify-ml test",
    [sys.argv[1]],
    "github-notify-ml test email",
)
sys.exit(0 if result else 1)
