"""搜索引擎式研究工作台：python -m collect.web_app；默认仅监听 127.0.0.1。

能力（会话式，搜完即弃，不写库）：
1. POST /api/search/start 启动搜索任务，立即返回 done/running/failed；
   GET  /api/search/progress 轮询真实进度（当前步骤/已找到条数）；
   POST /api/search  任务完成后取分页（同步语义保留，兼容旧调用方）；
2. GET  /api/summaries 轮询接口：返回每条结果的 LLM 总结与热评（后台生成）；
3. GET  /api/analysis  数据分析：时间热度 / 高频短语 / 平台与作者（基于本次
                       搜索结果统计，口径见 analysis 模块注释）；
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

from collect import settings
from collect.account_manager import AccountManager, PLATFORM_INFO
from collect.search_pipeline import SearchPipeline

WEB = settings.WEB_DIR
_DEFAULT_SIZE = settings.DEFAULT_PAGE_SIZE
_ACCOUNT_PLATFORMS = {i["platform"] for i in PLATFORM_INFO if i["login_supported"]}
_MAX_BODY = 64 * 1024            # 请求体大小上限（64KB），防止内存被恶意撑爆
_MAX_KEYWORD = 100               # 搜索关键词长度上限


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
            if platform not in _ACCOUNT_PLATFORMS:
                self._send_json({"error": "不支持的平台或登录操作"}, status=400)
                return
            self._send_json(self.server.account_manager.poll_login(platform))
            return
        if path == "/api/verify":
            platform = (qs.get("platform") or [""])[0]
            if platform not in _ACCOUNT_PLATFORMS:
                self._send_json({"error": "不支持的平台或登录操作"}, status=400)
                return
            self._send_json(self.server.account_manager.poll_verify(platform))
            return
        if path == "/api/analysis":
            keyword = (qs.get("keyword") or [""])[0]
            self._send_json(pipe.analysis_for(keyword))
            return
        if path == "/api/summaries":
            keyword = (qs.get("keyword") or [""])[0]
            self._send_json({"states": pipe.summary_state(keyword)})
            return
        if path == "/api/search/progress":
            task = (qs.get("task") or [""])[0]
            if not task:
                self._send_json({"error": "缺少 task"}, status=400)
                return
            self._send_json(pipe.search_progress(task))
            return
        if path in ("/", "/index.html", "/app.js", "/dom.js", "/order.mjs", "/analysis.js", "/accounts.js", "/style.css"):
            name = "index.html" if path == "/" else path[1:]
            try:
                content = (WEB / name).read_bytes()
            except OSError:
                self.send_error(404)
                return
            mime = {".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript",
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

    def _read_json_object(self):
        """读取并校验请求体：必须是大小受限的 JSON 对象，否则返回错误响应。

        返回解析后的 dict；校验失败时已发送明确错误响应并返回 None，
        调用方直接结束请求即可，不允许静默吞掉坏输入。
        """
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._send_json({"error": "Content-Length 无效"}, status=400)
            return None
        if length <= 0:
            return {}
        if length > _MAX_BODY:
            self._send_json({"error": "请求体过大"}, status=413)
            return None
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json({"error": "请求体不是有效 JSON"}, status=400)
            return None
        if not isinstance(payload, dict):
            # 数组 / null / 数字等都不是合法的对象请求体。
            self._send_json({"error": "请求体必须是 JSON 对象"}, status=400)
            return None
        return payload

    def do_POST(self):
        path = urlsplit(self.path).path
        payload = self._read_json_object()
        if payload is None:
            return  # 校验失败，错误响应已发送
        if path not in ("/api/search", "/api/search/start"):
            am = self.server.account_manager
            platform = payload.get("platform")
            if platform is not None and not isinstance(platform, str):
                self._send_json({"error": "platform 必须是字符串"}, status=400)
                return
            platform = (platform or "").strip()
            if path in ("/api/login", "/api/login/cancel", "/api/verify", "/api/logout") and platform not in _ACCOUNT_PLATFORMS:
                self._send_json({"error": "不支持的平台或登录操作"}, status=400)
                return
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
        pipe: SearchPipeline = self.server.pipeline
        validated = self._validated_search(payload)
        if validated is None:
            return  # 校验失败，错误响应已发送
        keyword, page, size = validated
        if path == "/api/search/start":
            status = pipe.start_search(keyword, size * 3)
            self._send_json({"ok": True, "task": keyword, "status": status})
            return
        result = pipe.search_page(keyword, page=page, size=size)
        posts = result.pop("posts")
        result["rows"] = [self._row(p, pipe) for p in posts]
        self._send_json(result)

    def _validated_search(self, payload):
        """校验搜索参数；失败时发送明确错误响应并返回 None，成功返回三元组。"""
        keyword = payload.get("keyword")
        if keyword is not None and not isinstance(keyword, str):
            self._send_json({"error": "关键词必须是字符串"}, status=400)
            return None
        keyword = (keyword or "").strip()
        if not keyword:
            self._send_json({"rows": [], "total": 0,
                             "errors": ["关键词不能为空"]})
            return None
        if len(keyword) > _MAX_KEYWORD:
            self._send_json({"error": "关键词过长"}, status=400)
            return None
        page = payload.get("page", 1)
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            self._send_json({"error": "page 必须是正整数"}, status=400)
            return None
        size = payload.get("size", _DEFAULT_SIZE)
        if isinstance(size, bool) or not isinstance(size, int) or not (10 <= size <= 100):
            self._send_json({"error": "size 必须在 10 到 100 之间"}, status=400)
            return None
        return keyword, page, size

    def _row(self, p, pipe: SearchPipeline):
        row = post_to_row(p)
        row.update(pipe.result_details(p.url))
        return row


def close_services(server):
    """依次关闭后台服务，任何一步异常也保证其他服务获得清理机会。"""
    try:
        server.pipeline.close(timeout=2.0)
    finally:
        try:
            server.account_manager.close(timeout=2.0)
        finally:
            server.server_close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.daemon_threads = True  # 停止服务时不因请求处理线程无限等待
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
        close_services(server)


if __name__ == "__main__":
    main()
