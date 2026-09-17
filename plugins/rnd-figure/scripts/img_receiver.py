# -*- coding: utf-8 -*-
"""브라우저 안의 blob: 이미지를 파일로 받는 아주 작은 수신 서버.

    python $CLAUDE_PLUGIN_ROOT/scripts/img_receiver.py --out workspace/<과제>/figures --port 8790

왜 필요한가
    Gemini가 만든 이미지는 `blob:https://gemini.google.com/...` 로 붙는다.
    blob URL은 그 페이지 안에서만 유효해서 밖에서 fetch 할 수 없고, 바이트를
    대화 문맥으로 끌어오면 1MB짜리 base64가 그대로 토큰이 된다.
    그래서 페이지가 스스로 blob을 읽어 이 서버로 POST 하게 한다.

페이지 쪽에서 실행할 코드(javascript_tool):
    const img = document.querySelector('img[src^="blob:"]');
    const buf = await (await fetch(img.currentSrc)).arrayBuffer();
    await fetch('http://127.0.0.1:8790/save?name=fig01.png',
                {method:'POST', mode:'no-cors', body: buf});

`mode:'no-cors'` 라 응답은 못 읽지만 본문은 서버에 도착한다.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

OUT_DIR = "."
SAFE = re.compile(r"[^A-Za-z0-9가-힣._-]")


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self):
        name = "image.png"
        if "?" in self.path:
            for kv in self.path.split("?", 1)[1].split("&"):
                if kv.startswith("name="):
                    from urllib.parse import unquote
                    name = unquote(kv[5:])
        name = SAFE.sub("_", os.path.basename(name)) or "image.png"
        n = int(self.headers.get("Content-Length") or 0)
        data = self.rfile.read(n) if n else b""
        path = os.path.join(OUT_DIR, name)
        os.makedirs(OUT_DIR, exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        # 콘솔에 남겨야 호출부가 성공을 확인할 수 있다
        print(f"SAVED {len(data)} bytes -> {path}", flush=True)
        self.send_response(200)
        self._cors()
        self.end_headers()

    def log_message(self, *a):        # 기본 액세스 로그는 시끄럽다
        pass


def main():
    global OUT_DIR
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--port", type=int, default=8790)
    a = ap.parse_args()
    OUT_DIR = os.path.abspath(a.out)
    os.makedirs(OUT_DIR, exist_ok=True)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(f"수신 대기 127.0.0.1:{a.port} → {OUT_DIR}", flush=True)
    HTTPServer(("127.0.0.1", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
