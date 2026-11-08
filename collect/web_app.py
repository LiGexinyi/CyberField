"""本地研究工作台：python -m collect.web_app；默认仅监听 127.0.0.1。

能力：
1. 实时搜索（GET/POST 白名单）：POST /api/search 调用 B站+豆瓣+微博游客态
   适配器真实搜索，结果仅缓存在内存，不写库；
2. 手动入库：POST /api/import 把最近一次搜索结果写入本地库（确认才存）；
3. 本地库浏览：GET /api/posts 只读导出；静态页面白名单。

搜索结果是临时数据，本次关闭即失效；入库必须由前端「手动入库」触发。
"""
import argparse
import json
from dataclasses import asdict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from collect import orchestrator, store

WEB = Path(__file__).resolve().parent.parent / "web"

# 实时搜索默认使用游客态免登录源（B站 + 豆瓣 + 微博），不触发 MediaCrawler。
_DEFAULT_PLATFORMS = ("bili", "douban", "wb")
_DEFAULT_SOURCES = ("bilibili_api", "douban_api", "weibo_api")


def post_to_row(p) -> dict:
    """把采集返回的 Post 转成与 store.export_rows 同形状的行，前端可直接复用。"""
    row = asdict(p)
    row["keywords"] = [p.keyword] if p.keyword else []
    row["observations"] = []           # 搜索结果尚无快照
    row["fetched_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return row


class Handler(BaseHTTPRequestHandler):
    """只提供白名单静态文件、只读 API 与受控的搜索/入库接口。"""
    def _send_json(self, obj, status=200):
        """统一 JSON 响应。"""
        content = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        """响应页面或本地库快照，缺失数据库显示空状态。"""
        path = urlsplit(self.path).path
        if path == "/api/posts":
            try:
                self._send_json({"rows": store.export_rows(self.server.db_path)})
            except Exception:
                self.send_error(500, "Cannot read local database")
            return
        elif path in ("/", "/index.html", "/app.js", "/style.css"):
            name = "index.html" if path == "/" else path[1:]
            try:
                content = (WEB / name).read_bytes()
            except OSError:
                self.send_error(404)
                return
            mime = {".html": "text/html", ".js": "text/javascript",
                    ".css": "text/css"}[Path(name).suffix] + "; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                             "script-src 'self'; connect-src 'self'; "
                             "frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_error(404)

    def do_POST(self):
        """实时搜索 / 手动入库：搜索只缓存不写库，入库需显式调用。"""
        path = urlsplit(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {}
        if path == "/api/search":
            keyword = str(payload.get("keyword") or "").strip()
            if not keyword:
                self._send_json({"rows": [], "errors": ["关键词不能为空"],
                                 "summary": None})
                return
            try:
                limit = max(1, int(payload.get("limit") or 20))
            except (TypeError, ValueError):
                limit = 20
            try:
                posts, errors, summary = orchestrator.collect(
                    keyword, platforms=_DEFAULT_PLATFORMS,
                    limit=limit, source_names=_DEFAULT_SOURCES, save=False)
            except ValueError as exc:
                self._send_json({"rows": [], "errors": [str(exc)], "summary": None})
                return
            self.server.last_results = {"keyword": keyword, "posts": posts}
            self._send_json({"rows": [post_to_row(p) for p in posts],
                             "errors": errors, "summary": summary})
        elif path == "/api/import":
            last = getattr(self.server, "last_results", None) or {}
            posts = last.get("posts") or []
            if not posts:
                self._send_json({"inserted": 0, "skipped": 0,
                                 "message": "没有可入库的结果：请先实时搜索一次。"})
                return
            saved = store.save_posts(posts)
            self.server.last_results = None  # 入库后清空缓存，避免重复入库
            self._send_json({**saved,
                             "message": f"已入库 {saved['inserted']} 条，"
                                        f"跳过重复 {saved['skipped']} 条"})
        else:
            self.send_error(404)


def main():
    """解析端口和数据库路径，启动只读本地服务。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", type=Path, default=store.DEFAULT_DB)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.db_path = args.db
    server.last_results = None            # 最近一次搜索结果缓存（不落盘）
    print(f"CyberField: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
