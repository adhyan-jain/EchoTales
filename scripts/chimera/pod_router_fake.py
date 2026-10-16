"""Stub for `vllm serve` used only to test pod_router.py locally (ROUTER_FAKE=1). Usage: pod_router_fake.py <name> <port>.
Starts after a short delay, answers /health and /v1/chat/completions with a fixed JSON answer that names the served model."""
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

name, port = sys.argv[1], int(sys.argv[2])
time.sleep(2)  # emulates model load


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        self._send(200, {"ok": True})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        self.rfile.read(n)
        self._send(200, {"choices": [{"message": {"content": json.dumps({"answer": "UNDETERMINED", "served_by": name})}}],
                         "usage": {"prompt_tokens": 1, "completion_tokens": 1}})


HTTPServer(("127.0.0.1", port), H).serve_forever()
