import http.client
import json
import os
import socket
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from aios.config import Config
from aios.gateway import GatewayServer
from aios.hardware import recommended_threads

TOKEN = "a" * 32


class Backend(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class GatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.backend = ThreadingHTTPServer(("127.0.0.1", 0), Backend)
        config = Config(TOKEN, backend=f"http://127.0.0.1:{cls.backend.server_port}")
        cls.gateway = GatewayServer(("127.0.0.1", 0), config)
        for server in (cls.backend, cls.gateway):
            threading.Thread(target=server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        for server in (cls.gateway, cls.backend):
            server.shutdown()
            server.server_close()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.gateway.server_port, timeout=3)
        try:
            conn.request(method, path, body, headers or {})
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()

    def test_health(self):
        self.assertEqual(self.request("GET", "/health")[0], 200)

    def test_authentication_and_route_restriction(self):
        self.assertEqual(self.request("GET", "/v1/models")[0], 401)
        headers = {"Authorization": "Bearer " + TOKEN}
        self.assertEqual(self.request("GET", "/admin", headers=headers)[0], 404)

    def test_proxy(self):
        body = json.dumps({"messages": []})
        status, result = self.request("POST", "/v1/chat/completions", body,
                                      {"Authorization": "Bearer " + TOKEN})
        self.assertEqual((status, result), (200, body.encode()))

    def test_limit(self):
        headers = {"Authorization": "Bearer " + TOKEN, "Content-Length": str(3 * 1024 * 1024)}
        self.assertEqual(self.request("POST", "/v1/completions", headers=headers)[0], 413)

    def test_backend_unavailable(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        server = GatewayServer(("127.0.0.1", 0), Config(TOKEN, backend=f"http://127.0.0.1:{port}"))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        try:
            conn.request("GET", "/v1/models", headers={"Authorization": "Bearer " + TOKEN})
            response = conn.getresponse()
            self.assertEqual(response.status, 502)
            self.assertIn(b"backend unavailable", response.read())
        finally:
            conn.close()
            server.shutdown()
            server.server_close()


class ConfigTests(unittest.TestCase):
    def test_token_required(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ValueError):
            Config.from_env()

    def test_backend_must_be_loopback_origin(self):
        for backend in ("http://example.com:8081", "http://127.0.0.1:8081/path", "https://127.0.0.1:8081"):
            with self.subTest(backend=backend), patch.dict(os.environ, {"AIOS_API_TOKEN": TOKEN, "AIOS_BACKEND": backend}, clear=True):
                with self.assertRaises(ValueError):
                    Config.from_env()

    def test_cpu_count_positive(self):
        self.assertGreaterEqual(recommended_threads(), 1)
