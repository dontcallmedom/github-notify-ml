# coding=utf-8
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import responses
from index import serveRequest
import sys

config = {
    "SMTP_HOST": "localhost",
    "EMAIL_FROM": "test@localhost",
    "TEMPLATES_DIR": "tests/templates",
    "GH_OAUTH_TOKEN": "foo",
    "mls": "tests/mls.json",
}


class PythonCGIHTTPRequestHandler(BaseHTTPRequestHandler):
    wbufsize = 0

    def do_GET(self):
        os.environ["REQUEST_METHOD"] = "GET"
        self.serve()

    def log_message(self, format, *args):
        pass

    @responses.activate
    def serve(self):
        data = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        output = serveRequest(config, data)
        # crude, but sufficient here
        head, body = output.split("\n\n", 1)
        headersList = head.split("\n")
        headers = {}
        for line in headersList:
            key, value = line.split(":", 1)
            headers[key] = value
        status = 200
        if "Status" in headers:
            status = int(headers["Status"].strip().split(" ")[0])
            del headers["Status"]
        self.send_response(status)
        for header, value in headers.items():
            self.send_header(header, value)
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def do_POST(self):
        os.environ["REQUEST_METHOD"] = "POST"
        if "X-Github-Event" in self.headers:
            os.environ["HTTP_X_GITHUB_EVENT"] = self.headers["X-Github-Event"]
        else:
            os.environ.pop("HTTP_X_GITHUB_EVENT", None)
        if "X-W3C-Webhook" in self.headers:
            os.environ["HTTP_X_W3C_WEBHOOK"] = self.headers["X-W3C-Webhook"]
        else:
            os.environ.pop("HTTP_X_W3C_WEBHOOK", None)
        os.environ["REMOTE_ADDR"] = self.headers.get("Remote-Addr", "127.0.0.1")
        self.rfile.flush()
        self.serve()


class Server:
    def __init__(self):
        responses.add(
            responses.GET,
            "https://api.github.com/meta",
            body='{"hooks":["127.0.0.0/8"]}',
            content_type="application/json",
        )
        responses.add(
            responses.GET,
            "https://api.github.com/users/dontcallmedom",
            body='{"name":"Dominique Hazaël-Massieux"}',
            content_type="application/json",
        )
        responses.add(
            responses.GET,
            "https://api.github.com/users/anssiko",
            body='{"name":"Anssi Kostiainen"}',
            content_type="application/json",
        )
        responses.add(
            responses.GET,
            "https://api.github.com/users/stefhak",
            body='{"name":"Stefan Hakansson"}',
            content_type="application/json",
        )
        responses.add(
            responses.GET,
            "https://api.github.com/users/tobie",
            body='{"name":"Tobie Langel"}',
            content_type="application/json",
        )
        responses.add(
            responses.GET,
            "https://api.github.com/users/alvestrand",
            body='{"name":"Harald Alvestrand"}',
            content_type="application/json",
        )
        responses.add(
            responses.GET,
            "https://api.github.com/repos/w3c/mediacapture-main/pulls/150",
            body='{"id":31564006}',
            content_type="application/json",
        )
        responses.add(
            responses.GET,
            "https://api.github.com/users/Codertocat",
            body='{"name":"Codertocat"}',
            content_type="application/json",
        )

        self.stop = threading.Event()
        server_address = ("localhost", 8000)
        handler = PythonCGIHTTPRequestHandler
        self.httpd = HTTPServer(server_address, handler)

    def start(self):
        self.mythread = threading.Thread(target=self.serve)
        self.mythread.start()

    def serve(self):
        self.httpd.handle_request()
        return

    def terminate(self):
        self.stop.set()
        self.httpd.socket.close()
        self.mythread.join()


if __name__ == "__main__":
    server = Server()
    server.serve()
