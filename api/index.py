"""
api/index.py — Five Resonance API 라우터 (Vercel entrypoint)
/api/innate       → innate 분석
/api/compatibility → 궁합 분석
"""
from http.server import BaseHTTPRequestHandler
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from innate import handler as InnateHandler
from compatibility import handler as CompatHandler


class handler(BaseHTTPRequestHandler):

    def do_POST(self):
        if self.path.rstrip('/') == '/api/innate':
            self._delegate(InnateHandler)
        elif self.path.rstrip('/') == '/api/compatibility':
            self._delegate(CompatHandler)
        else:
            self._json(404, {"error": f"Unknown path: {self.path}"})

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def _delegate(self, HandlerClass):
        """요청을 해당 핸들러로 위임"""
        length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(length)

        import io
        inst = HandlerClass.__new__(HandlerClass)
        inst.headers = self.headers
        inst.rfile = io.BytesIO(body_bytes)
        inst.wfile = self.wfile
        inst.send_response = self.send_response
        inst.send_header = self.send_header
        inst.end_headers = self.end_headers
        inst.path = self.path
        inst.do_POST()

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass
