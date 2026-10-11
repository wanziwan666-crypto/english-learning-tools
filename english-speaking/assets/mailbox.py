#!/usr/bin/env python3
"""雅思口语网页 <-> AI 对话 的本地信箱。

网页 POST 作答到 /submit；AI 把批改经 POST /grade 写回——追加 feedbacks 和
删已处理 submissions 都在服务器进程内串行完成，agent 不直接改 mailbox.json
（否则与服务器并发整读整写会互相覆盖，丢提交/丢批改）；网页轮询 /feedback 拉取。
同时静态托管同目录练习页（GET / 或 /NN-*.html）：练习页走同源 http 打开——
Chrome 对 file:// 源不记忆麦克风授权（每次录音都弹窗），对 127.0.0.1 记一次
即永久生效；Host 为 localhost 时 302 到 127.0.0.1，统一源避免 localStorage
与授权分裂。仅监听 127.0.0.1，无鉴权（本机自用）；Origin 校验放行 curl（无
Origin）、file:// 打开的练习页（Origin: null）与同源 http 页面，浏览器里
其他网页一律 403。

启动：python3 mailbox.py   （端口 8765；日常由 launchd 托管）
"""
import json
import os
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlsplit, parse_qs

BASE = os.path.dirname(os.path.abspath(__file__))
BOX = os.path.join(BASE, "mailbox.json")
PORT = 8765


def read_box():
    try:
        with open(BOX, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"submissions": [], "feedbacks": []}


def write_box(box):
    tmp = BOX + ".tmp"  # 原子落盘：写一半崩溃也不会损坏 mailbox.json
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(box, f, ensure_ascii=False, indent=1)
    os.replace(tmp, BOX)


class Handler(BaseHTTPRequestHandler):
    def _send(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _origin_ok(self):
        # curl / 同源 GET 导航不带 Origin；file:// 页面发 "null"；同源 http 页面发本机源——
        # 都放行；其余（浏览器里别的网页）拒绝
        o = self.headers.get("Origin")
        return o is None or o == "null" or o in ("http://127.0.0.1:%d" % PORT,
                                                 "http://localhost:%d" % PORT)

    def _serve_static(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        name = urlsplit(self.path).path.lstrip("/") or "index.html"
        if host == "localhost":  # 统一到 127.0.0.1，localStorage/麦克风授权只记一份
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:%d/%s" % (PORT, name))
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        # 只放行本目录下扁平的 *.html（练习页 + index），杜绝路径穿越
        if not (name.endswith(".html") and "/" not in name and not name.startswith(".")):
            return self._send({"error": "not found"}, 404)
        try:
            with open(os.path.join(BASE, name), "rb") as f:
                body = f.read()
        except OSError:
            return self._send({"error": "not found"}, 404)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")  # agent 会就地重生成页面，别让浏览器拿旧版
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        if not self._origin_ok():
            return self._send({"error": "forbidden"}, 403)
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if not self._origin_ok():
            return self._send({"error": "forbidden"}, 403)
        if self.path.startswith("/ping"):
            self._send({"ok": True, "ts": time.time()})
        elif self.path.startswith("/feedback"):
            try:
                after = float(parse_qs(urlsplit(self.path).query).get("ts", ["0"])[0])
            except ValueError:
                after = 0.0
            self._send([fb for fb in read_box()["feedbacks"] if fb.get("ts", 0) > after])
        else:
            self._serve_static()

    def do_POST(self):
        if not self._origin_ok():
            return self._send({"error": "forbidden"}, 403)
        n = int(self.headers.get("Content-Length") or 0)
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send({"error": "bad json"}, 400)
        box = read_box()
        if self.path.startswith("/grade"):
            done = set(data.get("ts_done") or [])
            box["submissions"] = [s for s in box.get("submissions", []) if s.get("ts") not in done]
            for fb in data.get("feedbacks") or []:
                box.setdefault("feedbacks", []).append(
                    {"ts": time.time(), "lesson": fb.get("lesson"), "qi": fb.get("qi"), "text": fb.get("text")}
                )
            write_box(box)
            self._send({"ok": True, "feedbacks": len(box["feedbacks"]), "submissions": len(box["submissions"])})
        elif self.path.startswith("/submit"):
            box.setdefault("submissions", []).append({"ts": time.time(), **data})
            write_box(box)
            self._send({"ok": True})
        else:
            self._send({"error": "not found"}, 404)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print("mailbox listening on http://127.0.0.1:%d (box: %s)" % (PORT, BOX))
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
