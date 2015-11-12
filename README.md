index.py is a python CGI script that provides a Webhook to be used as a github hook endpoint to send mail to a set of email addresses when specific events (e.g. push, new issues, etc) happen in specific repos.

The set of mailing lists, repos and events is configured in a JSON file, named `mls.json` that lives in the same directory as the webhook, with the following structure:
```json
{
 'email@example.com': {
   "githubaccount/repo": {
      "events": ["issues.opened", "issues.closed", "issue_comment.created", "pull_request.opened", "pull_request.labeled"],
      "eventFilter": {"label":"important"}
      "branches: {
        "master": ["push"]
      }
   }
  },
 'email2@example.com': {

  }
}
```

In other words:
* each email address to which notifications are to be sent is a top level object
* in email objects, each repos from which events need to be notified is an object
* in repo objects, there are 3 potential fields:
** `events` is an array of Github events applicable to the repo as a whole; only events in that array will be notified
** `eventFilter` is an optional set of filters that are applied to the events above; at the moment, only a `label` filter is defined, which means that only events that are associated with the said label will be notified
** `branches` allows to describe events that are applicable at the branch level rather than the whole repo (e.g. "push")

Only events for which templates have been defined (in the `templates/generic` directory) will be notified. Each mail target can have customized templates by creating an `email@example.com` directory in `templates/mls` and having a file named after the event. Templates use Mustache-based pystache as their engines and are fed with payload data from the event. The first line of the template is used as the subject of the email.

## W3C instance
W3C operates an instance of this service for WGs (and some CGs) repositories; if you want to make use of this service, please contact dom@w3.org with the following information:
* mailing list to which notifications should be sent
* name of the repo(s)
* events that should be notified among:
** creation of issue
** closure of issue
** creation of pull request
** new comment on an issue
** new push to a branch (and if so, which branch(es))

If you want to use specific text in the notifications, please provide a template as described above.