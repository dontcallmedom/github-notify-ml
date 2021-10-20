#!/usr/bin/env python3
# started from
# https://github.com/razius/flask-github-webhook/blob/master/index.py
import io
import os
import re
import sys
import json
import re
import subprocess
import requests
import requests_cache
import ipaddress
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr
from email.generator import Generator
import email.charset
from io import StringIO
from functools import reduce

email.charset.add_charset("utf-8", email.charset.QP, email.charset.QP, "utf-8")

# avoid re-requesting the same content in a given run
requests_cache.install_cache(backend='memory')

class InvalidConfiguration(Exception):
    pass


def validate_repos(config):
    # TODO: Check that all configured repos have events with matching templates?
    # that they all have an email.to field?
    mls = get_mls(config)
    import os.path

    for (ml, repos) in mls.items():
        for (repo, data) in repos.items():
            for e in data.get("events", []):
                generic_template = config["TEMPLATES_DIR"] + "/generic/" + e
                ml_template = config["TEMPLATES_DIR"] + "/mls/" + ml + "/" + e
                specific_template = (
                    config["TEMPLATES_DIR"] + "/mls/" + ml + "/" + repo + "/" + e
                )
                if not (
                    os.path.isfile(generic_template)
                    or os.path.isfile(ml_template)
                    or os.path.isfile(specific_template)
                ):
                    raise InvalidConfiguration(
                        "No template matching event %s defined in %s in %s (looked at %s and %s)"
                        % (e, config["mls"], repo, generic_template, specific_template)
                    )


def get_mls(config):
    with io.open(config["mls"], "r") as filehandle:
        mls = filehandle.read()
    return json.loads(mls)


def event_id(event, payload):
    if event.split(".")[0] == "issues":
        return payload["issue"]["id"]
    elif event.split(".")[0] == "issue_comment":
        return payload["comment"]["id"]
    elif event == "push":
        return payload["head_commit"]["id"]
    elif event.split(".")[0] == "pull_request":
        return payload["pull_request"]["id"]
    elif event.split(".")[0] == "repository":
        return payload["repository"]["id"]


def event_timestamp(event, payload):
    def timestamp(date):
        from dateutil import parser
        import calendar

        try:
            return calendar.timegm(parser.parse(date).utctimetuple())
        except:
            return date

    ts = None
    if event == "push":
        ts = payload["repository"]["pushed_at"]
    elif event == "issue_comment.created":
        ts = payload["comment"]["created_at"]
    elif event == "repository.created":
        ts = payload["repository"]["created_at"]
    elif event.split(".")[0] in ["issues", "pull_request"]:
        action = event.split(".")[1]
        key = (
            "pull_request"
            if event.split(".")[0] == "pull_request" and "pull_request" in payload
            else "issue"
        )
        if action == "opened":
            ts = payload[key]["created_at"]
        elif action == "closed":
            ts = payload[key]["closed_at"]
        elif action == "reopened" or action == "synchronize" or action == "labeled":
            ts = payload[key]["updated_at"]
    if ts:
        return timestamp(ts)


def refevent(event, payload, target, oauth_token):
    if target == "issue" and event in [
        "issues.reopened",
        "issues.closed",
        "issue_comment.created",
    ]:
        return ("issues.opened", payload["issue"]["id"])
    elif target == "pull_request" and event in [
        "pull_request.closed",
        "pull_request.reopened",
        "pull_request.synchronized",
        "pull_request_review_comment.created",
    ]:
        return ("pull_request.opened", payload["pull_request"]["id"])
    elif target == "pull_request" and event == "issue_comment.created":
        if oauth_token:
            headers = {}
            headers["Authorization"] = "token %s" % (oauth_token)
            pr_id = requests.get(
                payload["issue"]["pull_request"]["url"], headers=headers
            ).json()["id"]
            if pr_id:
                return ("pull_request.opened", pr_id)
    return (None, None)


def getRepoData(repo, token):
    url = "https://api.github.com/repos/%s" % repo
    headers = {}
    headers["Authorization"] = "token %s" % token
    githubListReq = requests.get(url, headers=headers)
    if githubListReq.status_code == 404:
        return [{"error": "Repo %s yields 404 error" % repo}]
    return githubListReq.json()


def navigateGithubList(url, token, until, cumul=[]):
    headers = {}
    headers["Authorization"] = "token %s" % token
    githubListReq = requests.get(url, headers=headers)
    if githubListReq.status_code == 404:
        return [
            {
                "error": "Repo %s yields 404 error"
                % url.split("https://api.github.com/repos/")[1]
            }
        ]
    pageList = githubListReq.json()

    def posterior(item):
        return until.strftime("%Y-%m-%dT%H:%M:%SZ") <= item["created_at"]

    cumul = cumul + list(filter(posterior, pageList))
    if (
        len(pageList)
        and posterior(pageList[-1])
        and "url" in githubListReq.links.get("next", {})
    ):
        return navigateGithubList(
            githubListReq.links["next"]["url"], token, until, cumul
        )
    else:
        return cumul


def listGithubEvents(repo, token, until):
    baseUrl = "https://api.github.com/repos/%s/" % repo
    events = {}
    events["repo"] = navigateGithubList(baseUrl + "events", token, until)
    # events["issues"] = navigateGithubList(baseUrl + "issues/events", token, until)
    return events


def andify(l):
    return [{"name": x, "last": i == len(l) - 1} for i, x in enumerate(sorted(l))]


def extractDigestInfo(events, eventFilter=None):
    def listify(l):
        return {"count": len(l), "list": l}

    data = {}
    isIssue = lambda x: x.get("type") == "IssuesEvent"
    isPR = lambda x: x.get("type") == "PullRequestEvent"
    isComment = lambda x: x.get("type") == "IssueCommentEvent"
    isNew = lambda x: x.get("payload", {}).get("action") == "opened"
    isCreated = lambda x: x.get("payload", {}).get("action") == "created"
    isClosed = lambda x: x.get("payload", {}).get("action") == "closed"
    isMerged = lambda x: x.get("payload", {}).get("pull_request", {}).get("merged")

    filtered_events = [add_label_text_colors(e) for e in events["repo"]]
    errors = [x for x in events["repo"] if x.get("error")]
    if eventFilter:
        filtered_events = [
            x
            for x in events["repo"]
            if filter_labeled_issue(eventFilter, x.get("payload", {}))
        ]

    newissues = list(filter(isNew, list(filter(isIssue, filtered_events))))
    closedissues = list(filter(isClosed, list(filter(isIssue, filtered_events))))
    newpr = list(filter(isNew, list(filter(isPR, filtered_events))))
    mergedpr = list(
        filter(isMerged, list(filter(isClosed, list(filter(isPR, filtered_events)))))
    )

    issuecomments = list(filter(isCreated, list(filter(isComment, filtered_events))))
    commentedissues = {}
    for comment in issuecomments:
        number = comment["payload"]["issue"]["number"]
        if number not in commentedissues:
            issue = {}
            issue["number"] = number
            issue["title"] = comment["payload"]["issue"]["title"]
            issue["url"] = comment["payload"]["issue"]["html_url"]
            issue["commentscount"] = 0
            issue["commentors"] = set()
            issue["ispr"] = "pull_request" in comment["payload"]["issue"]
            issue["labels"] = comment["payload"]["issue"]["labels"]
            commentedissues[number] = issue
        commentedissues[number]["commentscount"] += 1
        commentedissues[number]["commentors"].add(comment["actor"]["display_login"])
    for number, issue in commentedissues.items():
        commentedissues[number]["commentors"] = andify(
            commentedissues[number]["commentors"]
        )
    data["errors"] = listify(errors)
    data["newissues"] = listify(newissues)
    data["closedissues"] = listify(closedissues)
    data["commentedissues"] = listify(
        sorted(
            [x for x in list(commentedissues.values()) if not x["ispr"]],
            key=lambda issue: -issue["number"],
        )
    )
    data["issuecommentscount"] = reduce(
        lambda a, b: a + b["commentscount"], data["commentedissues"]["list"], 0
    )
    data["newpr"] = listify(newpr)
    data["mergedpr"] = listify(mergedpr)
    data["commentedpr"] = listify(
        sorted(
            [x for x in list(commentedissues.values()) if x["ispr"]],
            key=lambda issue: -issue["number"],
        )
    )
    data["prcommentscount"] = reduce(
        lambda a, b: a + b["commentscount"], data["commentedpr"]["list"], 0
    )
    data["activeissue"] = (
        len(newissues) > 0 or len(closedissues) > 0 or data["issuecommentscount"] > 0
    )
    data["activepr"] = (
        data["prcommentscount"] > 0 or len(newpr) > 0 or len(mergedpr) > 0
    )
    return data

# this preserves order which list(set()) wouldn't
def uniq(seq):
    seen = set()
    seen_add = seen.add
    return [x for x in seq if not (x in seen or seen_add(x))]

def getRepoList(source):
    repos = []
    if ("repos" in source):
        repos = source["repos"]
    if ("repoList" in source):
        try:
            repolist = requests.get(source["repoList"]).json()
            # ensure unicity
            repos = uniq(repos + repolist)
        except:
            pass
            # TODO: report error somehow?
    return repos

def sendDigest(config, period="daily"):
    from datetime import datetime, timedelta

    days = [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ]
    if period.lower() in days:
        until = datetime.now() - timedelta(7)
        duration = "weekly"
    elif period.lower() == "quarterly":
        until = datetime.now() - timedelta(92)
        duration = "quarterly"
    else:
        until = datetime.now() - timedelta(1)
        duration = period
    mls = get_mls(config)
    token = config.get("GH_OAUTH_TOKEN", False)
    digests = {}
    for (ml, target) in mls.items():
        if (
            "digest:%s" % period.lower() in target
            or "summary:%s" % period.lower() in target
        ):
            digests[ml] = target.get(
                "digest:%s" % period.lower(), target.get("summary:%s" % period.lower())
            )
            # we accept both list of digests or single digest in the configuration
            if not isinstance(digests[ml], list):
                digests[ml] = [digests[ml]]
            # Marking digests that are summary
            # since we need them to show content even if there was no recent
            # activity
            if "summary:%s" % period.lower() in target:
                digests[ml] = [dict(d, summary=True) for d in digests[ml]]
    for (ml, digest) in digests.items():
        for d in digest:
            events = {"repos": []}
            repos = []
            events["date"] = datetime.now().strftime("%A %B %d, %Y")

            events["activeissuerepos"] = []
            events["activeprrepos"] = []
            events["repostatus"] = []
            events["period"] = duration.capitalize()

            # a digest can have either an event filter that applies to all its repos
            # or a event filter specific to subset of repos
            # cf https://github.com/dontcallmedom/github-notify-ml/issues/43
            # For the latter case, we enable an optional array "sources"
            # which lists repos/eventFilter dictionaries
            # TODO make repoList work with sources too
            sources = d.get(
                "sources",
                [
                    {
                        "repos": getRepoList(d),
                        "eventFilter": d.get("eventFilter", None),
                    }
                ],
            )
            eventFilters = {}
            for s in sources:
                repos += s["repos"]
                events["repos"] += [
                    {
                        "name": r,
                        "shortname": r.split("/")[1],
                        "url": "https://github.com/" + r,
                        "last": i == len(repos) - 1,
                    }
                    for i, r in enumerate(s["repos"])
                ]
                for r in s["repos"]:
                    eventFilters[r] = s.get("eventFilter", None)
            for repo in repos:
                data = extractDigestInfo(
                    listGithubEvents(repo, token, until), eventFilters[repo]
                )
                data["repo"] = getRepoData(repo, token)
                data["name"] = repo
                if data["errors"]:
                    events["errors"] = data["errors"]
                if "summary" in d:
                    events["repostatus"].append(data)
                else:
                    if data["activeissue"]:
                        events["activeissuerepos"].append(data)
                    if data["activepr"]:
                        events["activeprrepos"].append(data)
                events["filtered"] = d.get("eventFilter", None)
                events["filteredlabels"] = (
                    len(d.get("eventFilter", {}).get("label", [])) > 0
                )
                events["filteredantilabels"] = (
                    len(d.get("eventFilter", {}).get("notlabel", [])) > 0
                )
                events["labels"] = andify(d.get("eventFilter", {}).get("label", []))
                events["antilabels"] = andify(
                    d.get("eventFilter", {}).get("notlabel", [])
                )
                events["topic"] = d.get("topic", None)
            events["activeissues"] = len(events["activeissuerepos"])
            events["activeprs"] = len(events["activeprrepos"])
            events["summary"] = len(events["repostatus"])
            if (
                events["activeissues"] > 0
                or events["activeprs"] > 0
                or events["summary"] > 0
            ):
                templates, error = loadTemplates(
                    "digest", config["TEMPLATES_DIR"], "/mls/" + ml + "/", duration
                )
                if not len(templates):
                    raise InvalidConfiguration(
                        "No template for %s digest targeted at %s" % (duration, ml)
                    )
                from_addr = config.get("email", {}).get("from", config["EMAIL_FROM"])
                parts, subject = mailFromTemplate(templates, events, config.get("SIGNATURE"))
                to = ml.split(",")
                sendMail(
                    config,
                    parts,
                    from_addr,
                    config["DIGEST_SENDER"],
                    to,
                    subject,
                )


def serveRequest(config, postbody):
    request_method = os.environ.get("REQUEST_METHOD", "GET")
    if request_method == "GET":
        output = "Content-Type: text/plain; charset=utf-8\n\n"
        output += " Nothing to see here, move along ..."
        return output
    if request_method != "POST":
        return
    if "HTTP_X_GITHUB_EVENT" in os.environ:
        return githubRequest(config, postbody)
    elif "HTTP_X_W3C_WEBHOOK" in os.environ:
        return w3cRequest(config, postbody)


def w3cRequest(config, postbody):
    mls = get_mls(config)

    payload = json.loads(postbody)
    event = payload["event"]

    def trimTrailingSlash(s):
        import re

        return re.sub(r"/$", "", s)

    trs = {}
    tr_prefix = "http://www.w3.org/TR/"
    for (ml, mltr) in mls.items():
        for (url, conf) in mltr.items():
            if url[0 : len(tr_prefix)] == tr_prefix:
                url = trimTrailingSlash(url)
                conf["email"] = {"to": ml}
                if event in conf["events"]:
                    if "url" not in trs:
                        trs[url] = []
                    trs[url].append(conf)
    target = trimTrailingSlash(payload["specversion"]["shortlink"])
    sentMail = []
    errors = []
    for conf in trs.get(target, []):
        to = conf["email"].get("to").split(",")
        templates, error = loadTemplates(
            event, config["TEMPLATES_DIR"], "/mls/" + ml + "/"
        )
        if not len(templates):
            errors.append(error)
            continue
        from_addr = conf.get("email", {}).get("from", config["EMAIL_FROM"])
        parts, subject = mailFromTemplate(templates, payload["specversion"], config.get("SIGNATURE"))
        sentMail.append(
            sendMail(config, parts, from_addr, "W3C Webmaster via W3C API", to, subject)
        )
    return reportSentMail(sentMail, errors)


def filter_labeled_event(eventFilter, event):
    labels = eventFilter.get("label", None)
    if labels and not type(labels) == list:
        labels = [labels]
    # not dealing with "notlabel" since it's not clear it makes
    # sense for "labeled" events
    event_label = event.get("label", {})
    if event_label.get("name") in labels:
        return event


def filter_labeled_issue(eventFilter, issue):
    labels = eventFilter.get("label", None)
    # backwards compat, since initially this took a single string
    # see https://github.com/dontcallmedom/github-notify-ml/issues/22
    if labels and not type(labels) == list:
        labels = [labels]
    antilabels = eventFilter.get("notlabel", None)
    issue_labels = issue.get("issue", issue.get("pull_request", {})).get("labels", [])
    labelFilter = lambda x: x.get("name") in labels
    antilabelFilter = lambda x: x.get("name") in antilabels
    has_label = True
    has_not_antilabel = True
    if labels:
        has_label = len(list(filter(labelFilter, issue_labels))) > 0
    if antilabels:
        has_not_antilabel = len(list(filter(antilabelFilter, issue_labels))) == 0
    if has_label and has_not_antilabel:
        return issue


def add_label_text_colors(event):
    labels = (
        event.get("payload", {})
        .get("issue", event.get("pull_request", event))
        .get("labels", [])
    )
    for label in labels:
        bg_color = label["color"]
        bg_rgb = int(bg_color, 16)
        bg_r = (bg_rgb >> 16) & 0xFF
        bg_g = (bg_rgb >> 8) & 0xFF
        bg_b = (bg_rgb >> 0) & 0xFF
        luma = 0.2126 * bg_r + 0.7152 * bg_g + 0.0722 * bg_b  # ITU-R BT.709
        if luma < 128:
            label["text_color"] = "ffffff"
        else:
            label["text_color"] = "000000"
    return event


def githubRequest(config, postbody):
    remote_addr = os.environ.get("HTTP_X_FORWARDED_FOR", os.environ.get("REMOTE_ADDR"))

    # Store the IP address blocks that github uses for hook requests.
    headers = {}
    if "GH_OAUTH_TOKEN" in config:
        headers["Authorization"] = "token %s" % (config["GH_OAUTH_TOKEN"])
    hook_blocks = requests.get("https://api.github.com/meta", headers=headers).json()[
        "hooks"
    ]
    output = ""

    # Check if the request is from github.com
    for block in hook_blocks:
        ip = ipaddress.ip_address("%s" % remote_addr)
        if ipaddress.ip_address(ip) in ipaddress.ip_network(block):
            break  # the remote_addr is within the network range of github
    else:
        output += "Status: 403 Unrecognized IP\n"
        output += "Content-Type: application/json\n\n"
        output += json.dumps({"msg": "Unrecognized IP address", "ip": remote_addr})
        return output

    event = os.environ.get("HTTP_X_GITHUB_EVENT", None)
    if event == "ping":
        output += "Content-Type: application/json\n\n"
        output += json.dumps({"msg": "Hi!"})
        return output
    mls = get_mls(config)
    for (ml, mlrepos) in mls.items():
        for (reponame, repoconf) in mlrepos.items():
            # don't fail on digests which takes a list rather than a dict
            if type(repoconf) != list:
                repoconf["email"] = {"to": ml}
    payload = json.loads(postbody)
    repo_meta = {"name": payload["repository"].get("name")}
    repo_meta["owner"] = payload["repository"]["owner"].get(
        "name", payload["repository"]["owner"].get("login")
    )
    match = re.match(r"refs/heads/(?P<branch>.*)", payload.get("ref", ""))
    if match:
        repo_meta["branch"] = match.groupdict()["branch"]

    formatedRepoName = "{owner}/{name}".format(**repo_meta)

    def repoMatch(reponame):
        if reponame.startswith("regexp:"):
            regexp = reponame[len("regexp:") :]
            try:
                return re.match(regexp, formatedRepoName) != None
            except:
                return False
        else:
            return reponame == formatedRepoName

    sentMail = []
    errors = []

    if "action" in payload:
        event = event + "." + payload["action"]

    # Harmonizing how the source of a repo transfer is represtend across orgs /users
    if event == "repository.transferred":
        payload["from"] = list(payload["changes"]["owner"]["from"].values())[0]["login"]

    for ml, repos in mls.items():
        for reponame in filter(repoMatch, list(repos.keys())):
            tr_prefix = "http://www.w3.org/TR/"
            digest_prefix = "digest:"
            if reponame[0 : len(tr_prefix)] == tr_prefix:
                continue
            if reponame[0 : len(digest_prefix)] == digest_prefix:
                continue
            repo = repos[reponame]

            if event not in repo["events"] and (
                "branch" not in repo_meta
                or event not in repo.get("branches", {}).get(repo_meta["branch"], [])
            ):
                continue
            if "eventFilter" in repo:
                relevant_payload = False
                if payload.get("action") == "labeled":
                    relevant_payload = filter_labeled_event(
                        repo["eventFilter"], payload
                    )
                else:
                    relevant_payload = filter_labeled_issue(
                        repo["eventFilter"], payload
                    )
                if not relevant_payload:
                    continue

            templates, error = loadTemplates(
                event, config["TEMPLATES_DIR"], "/mls/" + ml + "/", formatedRepoName
            )
            if not len(templates):
                errors.append(error)
                continue
            parts, subject = mailFromTemplate(templates, payload, config.get("SIGNATURE"))
            frum = repo.get("email", {}).get("from", config["EMAIL_FROM"])
            msgid = "<%s-%s-%s-%s>" % (
                event,
                event_id(event, payload),
                event_timestamp(event, payload),
                frum,
            )
            target = (
                "pull_request"
                if "pull_request" in payload
                or "pull_request" in payload.get("issue", {})
                else "issue"
            )
            (ref_event, ref_id) = refevent(
                event, payload, target, config.get("GH_OAUTH_TOKEN", False)
            )
            inreplyto = None
            if ref_event and ref_id:
                inreplyto = "<%s-%s-%s-%s>" % (
                    ref_event,
                    ref_id,
                    event_timestamp(ref_event, payload),
                    frum,
                )

            too = repo.get("email", {}).get("to").split(",")
            headers = {}
            frum_name = ""

            if "GH_OAUTH_TOKEN" in config:
                headers["Authorization"] = "token %s" % (config["GH_OAUTH_TOKEN"])
                frum_name = requests.get(
                    payload["sender"]["url"], headers=headers
                ).json()["name"]
                if frum_name == None:
                    frum_name = payload["sender"]["login"]
                frum_name = "%s via GitHub" % (frum_name)
            sentMail.append(
                sendMail(config, parts, frum, frum_name, too, subject, msgid, inreplyto)
            )
    return reportSentMail(sentMail, errors)


def reportSentMail(sentMail, errors):
    if sentMail:
        output = "Content-Type: application/json\n\n"
        output += json.dumps({"sent": sentMail, "errors": errors})
        return output
    elif len(errors):
        output = "Status: 500 Error processing the request\n"
        output += "Content-Type: application/json\n\n"
        output += json.dumps({"errors": errors})
        return output
    else:
        output = "Content-Type: application/json\n\n"
        output += '"nothing done"'
        return output


def loadTemplates(name, rootpath, specificpath, optionalpath=""):
    templates = []

    def loadFile(extension=""):
        error = None
        template = None
        try:
            with io.open(
                rootpath + specificpath + optionalpath + "/%s%s" % (name, extension)
            ) as filehandle:
                template = filehandle.read()
        except IOError:
            try:
                with io.open(
                    rootpath + specificpath + "/%s%s" % (name, extension)
                ) as filehandle:
                    template = filehandle.read()
            except IOError:
                try:
                    with io.open(
                        rootpath + "/generic/%s%s" % (name, extension)
                    ) as filehandle:
                        template = filehandle.read()
                except IOError:
                    error = {"msg": "no template defined for event %s" % name}
        return template, error

    template, error = loadFile()
    if template:
        templates.append(template)
        htmltemplate, error = loadFile(".html")
        if htmltemplate:
            templates.append(htmltemplate)
    return templates, error


def mailFromTemplate(templates, payload, signature):
    import pystache

    parts = []
    formats = ["plain", "html"]
    payload["signature"] = signature
    for template, subtype in zip(templates, formats):
        body = pystache.render(template, payload)
        if subtype == "plain":
            subject, dummy, body = body.partition("\n")
            if signature:
                body = body + "\n\n-- \n%s\n" % signature
        parts.append({"body": body, "subtype": subtype})
    return parts, subject


def sendMail(
    config, parts, from_addr, from_name, to_addr, subject, msgid=None, inreplyto=None
):
    if len(parts) == 1:
        msg = MIMEText(parts[0]["body"], _charset="utf-8")
        msg.set_param("format", "flowed")
    else:
        msg = MIMEMultipart("alternative")
        for part in parts:
            alt = MIMEText(part["body"], part["subtype"], _charset="utf-8")
            if part["subtype"] == "plain":
                alt.set_param("format", "flowed")
            msg.attach(alt)
    msg["From"] = formataddr((from_name, from_addr))
    msg["To"] = ",".join(to_addr)
    msg["Subject"] = Header(subject)
    if msgid:
        msg["Message-ID"] = msgid
    if inreplyto:
        msg["In-Reply-To"] = inreplyto

    # from http://wordeology.com/computer/how-to-send-good-unicode-email-with-python.html
    m = StringIO()
    g = Generator(m, False)
    g.flatten(msg)
    if "SMTP_SSL" in config:
        server = smtplib.SMTP_SSL(config["SMTP_HOST"])
    else:
        server = smtplib.SMTP(config["SMTP_HOST"])
    if "SMTP_USERNAME" in config:
        server.login(config["SMTP_USERNAME"], config["SMTP_PASSWORD"])
    server.sendmail(from_addr, to_addr, m.getvalue())
    sentMail = {"to": to_addr, "subject": subject}
    server.quit()
    return sentMail


def getConfig():
    config = json.loads(io.open("instance/config.json").read())
    for K in [
        "GH_OAUTH_TOKEN",
        "SMTP_SSL",
        "SMTP_HOST",
        "EMAIL_FROM",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
    ]:
        if K in os.environ:
            config[K] = os.environ[K]
    return config


if __name__ == "__main__":
    config = getConfig()
    if "SCRIPT_NAME" in os.environ:
        print(serveRequest(config, sys.stdin.read()))
    else:
        period = sys.argv[1] if len(sys.argv) > 1 else None
        sendDigest(config, period)
