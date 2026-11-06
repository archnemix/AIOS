import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from iso_benchmark.client import Client


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert request["stream"] and request["cache_prompt"] is False
        events = [{"content": "hello", "stop": False},
                  {"stop": True, "truncated": False, "timings": {
                      "prompt_n": 5, "predicted_n": 32,
                      "prompt_per_second": 100, "predicted_per_second": 10}}]
        body = b"".join(b"data: " + json.dumps(event).encode() + b"\n\n" for event in events)
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class ClientTests(unittest.TestCase):
    def test_stream_extracts_timings(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            sample = Client(server.server_port, "key").stream_completion("hello")
            self.assertEqual(sample["output_tokens"], 32)
            self.assertEqual(sample["output_tokens_per_second"], 10)
            self.assertGreaterEqual(sample["wall_seconds"], sample["ttft_seconds"])
        finally:
            server.shutdown()
            server.server_close()
