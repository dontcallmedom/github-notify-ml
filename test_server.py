# coding=utf-8
import os
from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
import threading
import responses
from index import serveRequest
import sys

config={"SMTP_HOST":"localhost",
        "EMAIL_FROM":"test@localhost",
        "TEMPLATES_DIR":"templates",
        "GH_OAUTH_TOKEN":"foo",
        "repos": "tests/repos.json"
        }


class PythonCGIHTTPRequestHandler(BaseHTTPRequestHandler):
    wbufsize = 0

    def do_GET(self):
        os.environ['REQUEST_METHOD'] = "GET"
        self.serve()

    def log_message(self, format, *args):
        pass

    @responses.activate
    def serve(self):
        data = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        output = serveRequest(config, data)
        # crude, but sufficient here
        head,body = output.split("\n\n", 1)
        headersList = head.split("\n")
        headers = {}
        for line in headersList:
            key,value = line.split(":", 1)
            headers[key] = value
        status = 200
        if headers.has_key("Status"):
            status = int(headers["Status"].strip().split(" ")[0])
            del headers["Status"]
        self.send_response(status)
        for header,value in headers.iteritems():
            self.send_header(header,value)
        self.end_headers()
        self.wfile.write(body)
        self.wfile.close()

    def do_POST(self):
        os.environ['REQUEST_METHOD'] = "POST"
        os.environ['HTTP_X_GITHUB_EVENT'] = self.headers.get("X-Github-Event")
        os.environ['REMOTE_ADDR'] = self.headers.get("Remote-Addr", "127.0.0.1")
        self.rfile.flush()
        self.serve()

class Server:
    def __init__(self):
        responses.add(responses.GET, 'https://api.github.com/meta',
                      body='{"hooks":["127.0.0.0/8"]}', content_type='application/json')
        responses.add(responses.GET, 'https://api.github.com/users/dontcallmedom',
                      body=u'{"name":"Dominique Hazaël-Massieux"}', content_type='application/json')
        self.stop = threading.Event()
        server_address=('localhost',8000)
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


if __name__ == '__main__':
    server = Server()
    server.serve()
