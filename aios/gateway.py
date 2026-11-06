"""Authenticated, deliberately narrow HTTP gateway for llama-server."""

import hmac
import http.client
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


class GatewayServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, config):
        super().__init__(address, GatewayHandler)
        self.config = config


class GatewayHandler(BaseHTTPRequestHandler):
    server_version = "AIOS"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        # Avoid logging prompts, credentials, or request paths.
        return

    def reply(self, status, message):
        body = json.dumps({"error": message}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            body = b'{"status":"ok"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.proxy("GET")

    def do_POST(self):
        self.proxy("POST")

    def proxy(self, method):
        # Closing prevents unread request bodies from becoming another request.
        self.close_connection = True
        self._headers_sent_for_proxy = False
        expected = "Bearer " + self.server.config.token
        supplied = self.headers.get("Authorization", "")
        if not hmac.compare_digest(supplied.encode(), expected.encode()):
            self.reply(401, "unauthorized")
            return
        allowed = {("GET", "/v1/models"), ("POST", "/v1/chat/completions"),
                   ("POST", "/v1/completions"), ("POST", "/v1/embeddings")}
        if (method, self.path) not in allowed:
            self.reply(404, "not found")
            return
        if self.headers.get("Transfer-Encoding"):
            self.reply(400, "transfer encoding is not supported")
            return
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) > 1 or (method == "POST" and not lengths):
            self.reply(400, "one content length is required")
            return
        try:
            raw_length = lengths[0] if lengths else "0"
            if not raw_length.isascii() or not raw_length.isdigit():
                raise ValueError
            length = int(raw_length)
            if length > self.server.config.max_body_bytes:
                self.reply(413, "request too large")
                return
            self.connection.settimeout(30)
            body = self.rfile.read(length)
            if len(body) != length:
                return
        except (ValueError, TimeoutError):
            self.reply(400, "invalid request body")
            return
        target = urlsplit(self.server.config.backend)
        connection = http.client.HTTPConnection(target.hostname, target.port, timeout=self.server.config.timeout)
        try:
            connection.request(method, self.path, body=body, headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            self.send_response(response.status)
            self.send_header("Content-Type", response.getheader("Content-Type", "application/json"))
            self.send_header("Cache-Control", "no-store")
            # Close-delimited responses support both ordinary and streaming outputs.
            self.send_header("Connection", "close")
            self.end_headers()
            while True:
                chunk = response.read1(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except (OSError, http.client.HTTPException):
            # Once headers are sent, an error can only terminate the stream.
            if not self._headers_sent_for_proxy:
                self.reply(502, "backend unavailable")
        finally:
            connection.close()

    def send_response(self, code, message=None):
        super().send_response(code, message)
        self._headers_sent_for_proxy = True

    _headers_sent_for_proxy = False
