"""Serves the voice demo and a neural text-to-speech endpoint.
Run:  .venv/bin/python server.py   ->  http://localhost:5180
"""
import asyncio, functools, http.server, json, os, urllib.parse
import edge_tts

PORT = int(os.environ.get("PORT", 5180))
VOICES = ["en-IN-NeerjaNeural", "en-IN-PrabhatNeural", "hi-IN-SwaraNeural", "hi-IN-MadhurNeural", "en-US-AvaMultilingualNeural"]
CACHE, CACHE_MAX = {}, 200


async def synth(text, voice, rate):
    out = bytearray()
    async for ch in edge_tts.Communicate(text, voice, rate=rate).stream():
        if ch["type"] == "audio":
            out += ch["data"]
    return bytes(out)


class H(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/voices":
            return self._send(200, "application/json", json.dumps(VOICES).encode())
        if u.path != "/tts":
            return super().do_GET()
        q = urllib.parse.parse_qs(u.query)
        text = (q.get("text") or [""])[0].strip()[:1200]
        voice = (q.get("voice") or [VOICES[0]])[0]
        rate = (q.get("rate") or ["+5%"])[0]
        if not text or voice not in VOICES:
            return self._send(400, "text/plain", b"bad request")
        key = (text, voice, rate)
        try:
            if key not in CACHE:
                if len(CACHE) >= CACHE_MAX:
                    CACHE.pop(next(iter(CACHE)))
                CACHE[key] = asyncio.run(synth(text, voice, rate))
            self._send(200, "audio/mpeg", CACHE[key])
        except Exception as e:  # network down etc. -> client falls back to the browser voice
            self._send(502, "text/plain", str(e).encode())

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    d = os.path.dirname(os.path.abspath(__file__))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), functools.partial(H, directory=d))
    print(f"XEST voice on http://localhost:{PORT}")
    srv.serve_forever()
