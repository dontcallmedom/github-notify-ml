index.py is a python CGI script that provides a Webhook to be used as a github hook endpoint to send mail to a set of email addresses when specific events (e.g. push, new issues, etc) happen in specific repos.

It can also be used as a [W3C hook](https://w3c.github.io/w3c-api/webhooks) endpoint to send mail when TR documents get published.

The set of mailing lists, repos / TR documents and events is configured in a JSON file, named `mls.json` that lives in the same directory as the webhook, with the following structure:
```json
{
 "email@example.com": {
   "githubaccount/repo": {
      "events": ["issues.opened", "issues.closed", "issue_comment.created", "pull_request.opened", "pull_request.labeled"],
      "eventFilter": {"label":["important"]},
      "branches": {
        "master": ["push"]
      }
   }
  },
 "email2@example.com": {
   "http://www.w3.org/TR/wake-lock": {
       "events": ["tr.published"]
    }
  },
 "email3@example.com": {
   "digest:tuesday": [
     {
       "repos": ["githubaccount/repo", "githubaccount/repo2"]
     },
     {
       "repos": ["githubaccount/repo3"],
       "eventFilter": {"label": ["enhancement"]}
     }
   ]
  }
}
```

In other words:
* each email address to which notifications are to be sent is a top level object
* in email objects, each repos / TR draft / digest is an object
* in repo objects, there are 3 potential fields:
  * `events` is an array of Github events applicable to the repo as a whole; only events in that array will be notified
  * `eventFilter` is an optional set of filters that are applied to the events above; at the moment, `label` and `notlabel` filters are defined, which means that only events that are associated with one of the said labels (defined as an array) will be notified (resp. only events that aren't associated with any of the labels)
  * `branches` allows to describe events that are applicable at the branch level rather than the whole repo (e.g. "push")
* TR draft objects only take an `events` field, with `"tr.published"` currently the only supported event.
* digest object can be either of "digest:monday" (or any other day of the week), or "digest:daily"; they take a list of dictionaries with a  "repos" field with an array of repository full names (e.g. `w3c/webrtc-pc`), and optionally an "eventFilter" field (which, as above, has `label` and `notlabel` as possible filters at the moment)

Only events for which templates have been defined (in the `templates/generic` directory) will be notified. Each mail target can have customized templates by creating an `email@example.com` directory in `templates/mls` and having a file named after the event. Templates use Mustache-based pystache as their engines and are fed with payload data from the event. The first line of the template is used as the subject of the email.

In addition to configuring targets of notifications, an instance of this webhook needs to define a `config.json` file with the SMTP host, the address from which messages will be sent, and set a GitHub OAUTH token that can be used to retrieve information via the GitHub API.

## W3C instance
W3C operates an instance of this service for WGs (and some CGs) repositories; if you want to make use of this service, please send pull requests on <a href="https://github.com/w3c/github-notify-ml-config">w3c/github-notify-ml-config</a> with amendments to the <code>mls.json</code> file for the mailing list(s) and repo(s) you’re interested in. 

You will also need to add a webhook to https://services.w3.org/github-notify-ml/ in the target repository's settings. To do this:
* in the repo for which notifications are being set, go to `Settings > Add webhook`
* add https://services.w3.org/github-notify-ml/ where it says `Payload URL`
* leave `Content-type` as application/json
* ignore the box `Secret`
* set radio to `Send me everything`
* leave `Active` checked
* and press `Add Webhook`

If you want to use a different text in the notifications, you can also provide pull requests that bring special per mailing list templates as described above.

## Testing
Run the test suite with:
```sh
python test_webhook.py
```

A typical test consists of:
* a JSON file with the payload of the github event / w3c event to be tested
* a .msg file that contains the email (with headers) expected to be sent by the webhook
* a new method in `test_webhook.py` `SendEmailGithubTests` that binds the event name, with the JSON file, and the email message
