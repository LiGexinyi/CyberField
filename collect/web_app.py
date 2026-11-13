"""搜索引擎式研究工作台：python -m collect.web_app；默认仅监听 127.0.0.1。

能力（会话式，搜完即弃，不写库）：
1. POST /api/search   模糊搜索：输入词 → 自动扩展相关词 → 多源深搜 →
                      按热度排序 → 30 条/页翻页返回；
2. GET  /api/summaries 轮询接口：返回每条结果的 LLM 总结与热评（后台生成）；
3. GET  /api/analysis  数据分析：时间热度 / 相关话题 / 相关群体（基于本次
                      搜索结果统计）；
4. 平台账号（阶段 0+1）：GET /api/accounts 各平台登录状态（7 状态机）；
   POST/GET /api/login 扫码登录（二维码回显 + 自动验证）；/api/login/cancel
   取消登录；POST /api/verify 检查状态（真实 pong 校验，网络错误→状态未知）；
   /api/logout 仅清除该平台专用档案。

LLM 总结需要环境变量 LLM_API_KEY（OpenAI 兼容，默认 DeepSeek）；
未配置时总结列显示为空，搜索本身不受影响。
"""
import argparse
import json
from dataclasses import asdict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from collect.account_manager import AccountManager
from collect.search_pipeline import SearchPipeline

WEB = Path(__file__).resolve().parent.parent / "web"
_DEFAULT_SIZE = 30


def post_to_row(p) -> dict:
    """把 Post 转成前端可用的行。"""
    row = asdict(p)
    row["keywords"] = [p.keyword] if p.keyword else []
    row["fetched_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return row


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, obj, status=200):
        content = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        path = urlsplit(self.path).path
        qs = parse_qs(urlsplit(self.path).query)
        pipe: SearchPipeline = self.server.pipeline
        if path == "/api/accounts":
            self._send_json({"accounts": self.server.account_manager.accounts()})
            return
        if path == "/api/login":
            platform = (qs.get("platform") or [""])[0]
            self._send_json(self.server.account_manager.poll_login(platform))
            return
        if path == "/api/verify":
            platform = (qs.get("platform") or [""])[0]
            self._send_json(self.server.account_manager.poll_verify(platform))
            return
        if path == "/api/analysis":
            keyword = (qs.get("keyword") or [""])[0]
            posts = pipe._cache_posts(keyword)
            if not posts:
                self._send_json({"error": "请先搜索「" + keyword + "」"})
                return
            self._send_json(pipe.build_analysis(posts))
            return
        if path == "/api/summaries":
            keyword = (qs.get("keyword") or [""])[0]
            self._send_json({"states": pipe.summary_state(keyword)})
            return
        if path in ("/", "/index.html", "/app.js", "/style.css"):
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
                             "img-src 'self' data:; "
                             "frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_error(404)

    def do_POST(self):
        path = urlsplit(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {}
        if path != "/api/search":
            am = self.server.account_manager
            platform = str(payload.get("platform") or "").strip()
            if path == "/api/login" and platform:
                job = am.start_login(platform)
                self._send_json({"ok": job.get("status") != "failed",
                                 "platform": platform,
                                 "status": job["status"],
                                 "error": job.get("error")})
                return
            if path == "/api/login/cancel" and platform:
                self._send_json(am.cancel_login(platform))
                return
            if path == "/api/verify" and platform:
                self._send_json(am.start_verify(platform))
                return
            if path == "/api/logout" and platform:
                self._send_json(am.logout(platform))
                return
            self.send_error(404)
            return
        keyword = str(payload.get("keyword") or "").strip()
        if not keyword:
            self._send_json({"rows": [], "total": 0,
                             "errors": ["关键词不能为空"]})
            return
        try:
            page = max(1, int(payload.get("page") or 1))
        except (TypeError, ValueError):
            page = 1
        try:
            size = max(10, min(100, int(payload.get("size") or _DEFAULT_SIZE)))
        except (TypeError, ValueError):
            size = _DEFAULT_SIZE
        pipe: SearchPipeline = self.server.pipeline
        cache = pipe._cache.get(keyword)
        if cache is None:  # 新词才重新搜索；换页复用缓存
            cache = pipe.run_search(keyword, size=size * 3)
            pipe.start_enrichment(keyword)
        posts = cache.get("posts") or []
        total = len(posts)
        start = (page - 1) * size
        rows = [self._row(p, pipe) for p in posts[start:start + size]]
        self._send_json({
            "keyword": keyword,
            "expanded": cache.get("expanded") or [keyword],
            "rows": rows,
            "total": total,
            "page": page,
            "pages": max(1, (total + size - 1) // size),
            "errors": cache.get("errors") or [],
        })

    def _row(self, p, pipe: SearchPipeline):
        row = post_to_row(p)
        state = pipe._summary_cache.get(p.url) or {}
        row["summary"] = state.get("summary")
        row["comments"] = (state.get("comments") or [])[:3]
        return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.pipeline = SearchPipeline()
    server.account_manager = AccountManager()
    print(f"CyberField: http://127.0.0.1:{args.port}", flush=True)
    print("LLM 总结：", "已启用（LLM_API_KEY）" if __import__(
        "collect.llm", fromlist=["available"]).available()
          else "未配置（搜索仍可用，总结留空）", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
