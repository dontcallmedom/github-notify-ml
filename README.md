index.py is a python CGI script that provides a Webhook to be used as a github hook endpoint to send mail to a set of email addresses when specific events (e.g. push, new issues, etc) happen in specific repos.

It can also be used without a hook to send a digest of activity across a set of defined repositories for a given period. In that mode, it is limited to [300 events](https://developer.github.com/v3/activity/events/#list-repository-events) in the said period for a given repo.

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
       "repoList": "https://example.org/repos.json"
     },
     {
       "topic": "All of repo4 and some of repo3", 
       "sources": [
           {
             "repos": ["githubaccount/repo3"],
             "eventFilter": {"label": ["enhancement"]}
           },
           {
             "repos": ["githubaccount/repo4"]
           }
         ]
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
* digests are identified by their key (of the form "digest:monday" (or any other day of the week), or "digest:daily" depending on the periodicity); each item in the said list describes a digest to be sent on that day to that list. A single digest is described by an object consisting of 
  * an optional "topic" (which will be included in the subject of the digest)
  * either:
    * a "repos" field with an array of repository full names (e.g. `w3c/webrtc-pc`) and/or a "repoList" field with an URL pointing a JSON area of repository fullnames (which gets combined with the list in `repos` if it is fetched successfully), and optionally an "eventFilter" field (which, as above, has `label` and `notlabel` as possible filters at the moment) that applies to all the said repos
    * a "sources" field, which describes an array of dictionaries as described above. This allows to create a single digest that combines filtered events from some repos, and unfiltered (or with different filters) events from other repos

Only events for which templates have been defined (in the `templates/generic` directory) will be notified. Each mail target can have customized templates by creating an `email@example.com` directory in `templates/mls` and having a file named after the event. Templates use Mustache-based pystache as their engines and are fed with payload data from the event. The first line of the template is used as the subject of the email.

In addition to configuring targets of notifications, an instance of this webhook needs to define a `config.json` file with the SMTP host, the address from which messages will be sent, and set a GitHub OAUTH token that can be used to retrieve information via the GitHub API.

See also [how to make use of the W3C instance of this service](https://github.com/w3c/github-notify-ml-config).

## Testing
Run the test suite with:
```sh
python test_webhook.py
```

A typical test consists of:
* a JSON file with the payload of the github event / w3c event to be tested
* a .msg file that contains the email (with headers) expected to be sent by the webhook
* a new method in `test_webhook.py` `SendEmailGithubTests` that binds the event name, with the JSON file, and the email message
