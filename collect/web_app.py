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
import os
import webbrowser
from threading import BoundedSemaphore
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


class PublicServer(ThreadingHTTPServer):
    """访客进程的 HTTP 连接数有上限，适合放在平台 HTTPS 网关后。"""
    public = True

    def __init__(self, address, handler):
        self._connections = BoundedSemaphore(32)
        super().__init__(address, handler)

    def process_request(self, request, client_address):
        """连接额度用尽时返回 503，避免无限创建线程。"""
        if not self._connections.acquire(blocking=False):
            try:
                request.settimeout(1)
                request.sendall(b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._connections.release()
            raise

    def process_request_thread(self, request, client_address):
        """连接结束时归还额度，包括客户端断线的情况。"""
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._connections.release()


class Handler(BaseHTTPRequestHandler):
    @property
    def public(self):
        """区分访客版和默认的单机版。"""
        return getattr(self.server, "public", False)

    def _send_json(self, obj, status=200):
        content = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError):
            # 客户端已断开：响应无法送达，保持服务进程安静即可。
            pass

    def setup(self):
        """限制单个连接读写时长，避免慢速/半开连接长期占用线程。"""
        super().setup()
        self.connection.settimeout(30)

    def log_message(self, format, *args):
        """本地工作台默认不输出访问日志，避免正常轮询刷满控制台。"""
        pass

    def do_GET(self):
        """GET 统一兜底：未预期异常返回 JSON 500，而不是裸断连接。"""
        try:
            self._handle_GET()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            try:
                self._send_json({"error": "服务器内部错误"}, status=500)
            except Exception:
                pass

    def _handle_GET(self):
        parts = urlsplit(self.path)
        path = parts.path
        qs = parse_qs(parts.query)
        pipe: SearchPipeline = self.server.pipeline
        if path == "/healthz":
            self._send_json({"ok": True})
            return
        if self.public and path in ("/api/accounts", "/api/login", "/api/verify"):
            self._send_json({"error": "访客版只搜索公开结果"}, status=404)
            return
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
            self._send_json(pipe.analysis_for(keyword, with_text=qs.get("text") == ["1"]))
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
                if self.public and name == "index.html":
                    content = content.replace(b"<body>", b'<body data-mode="public">', 1)
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
        """POST 统一兜底：先匹配路由再读请求体，未知路径返回 404。"""
        try:
            self._handle_POST()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            try:
                self._send_json({"error": "服务器内部错误"}, status=500)
            except Exception:
                pass

    def _handle_POST(self):
        path = urlsplit(self.path).path
        if path not in (
                "/api/search", "/api/search/start", "/api/search/continue", "/api/topic-interpretation",
                "/api/login", "/api/login/cancel", "/api/verify", "/api/logout"):
            self.send_error(404)
            return
        if self.public and path in ("/api/topic-interpretation", "/api/login",
                                    "/api/login/cancel", "/api/verify", "/api/logout"):
            self._send_json({"error": "该功能可在本机版使用"}, status=404)
            return
        payload = self._read_json_object()
        if payload is None:
            return  # 校验失败，错误响应已发送
        if path == "/api/topic-interpretation":
            from collect.topic_ai import interpret
            try:
                self._send_json(interpret(payload, self.server.pipeline.get_posts))
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=400)
            except Exception:
                self._send_json({"error": "模型服务未能完成请求，请检查网络并重试"}, status=502)
            return
        if path not in ("/api/search", "/api/search/start", "/api/search/continue"):
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
            status = pipe.start_search(keyword, size * 3, progressive=self.public or payload.get("progressive") is True)
            if status == "busy":
                self._send_json({"error": "正在处理其他搜索，请稍后重试"}, status=429)
                return
            self._send_json({"ok": True, "task": keyword, "status": status})
            return
        if path == "/api/search/continue":
            related_word = payload.get("related_word", "")
            if not isinstance(related_word, str) or len(related_word.strip()) > _MAX_KEYWORD:
                self._send_json({"error": "补搜词格式错误或过长"}, status=400)
                return
            status = pipe.continue_search(keyword, related_word.strip())
            errors = {"idle": ("这次搜索已不在工作台中，请先重新搜索", 409),
                      "failed": ("搜索服务暂不可用", 503),
                      "busy": ("正在处理其他搜索，请稍后重试", 429)}
            if status in errors:
                message, code = errors[status]
                self._send_json({"error": message}, status=code)
            else:
                self._send_json({"ok": True, "task": keyword, "status": status})
            return
        platforms = payload.get("platforms")
        if platforms is not None and (not isinstance(platforms, list) or not all(isinstance(v, str) for v in platforms)):
            self._send_json({"error": "平台筛选格式错误"}, status=400)
            return
        result = pipe.search_page(keyword, page=page, size=size, platforms=platforms,
                                  snapshot=self.public or payload.get("snapshot") is True)
        posts = result.pop("posts")
        result["rows"] = [self._row(p) for p in posts]
        self._send_json(result)

    def _validated_search(self, payload):
        """校验搜索参数；失败时发送明确错误响应并返回 None，成功返回三元组。"""
        keyword = payload.get("keyword")
        if keyword is not None and not isinstance(keyword, str):
            self._send_json({"error": "关键词必须是字符串"}, status=400)
            return None
        keyword = (keyword or "").strip()
        if not keyword:
            self._send_json({"error": "关键词不能为空"}, status=400)
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

    def _row(self, p):
        row = post_to_row(p)
        row.update(self.server.pipeline.result_details(p.url))
        return row


def close_services(server):
    """依次关闭后台服务，任何一步异常也保证其他服务获得清理机会。"""
    try:
        server.pipeline.close(timeout=2.0)
    finally:
        try:
            manager = server.account_manager
            if manager is not None:
                manager.close(timeout=2.0)
        finally:
            server.server_close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int)
    parser.add_argument("--open-browser", action="store_true", help="启动后在默认浏览器中打开工作台")
    parser.add_argument("--bind", default="127.0.0.1", help="访客版监听地址")
    parser.add_argument("--public", action="store_true", help="只开放访客搜索和本轮结果统计")
    args = parser.parse_args()
    if args.bind != "127.0.0.1" and not args.public:
        parser.error("非回环监听需要 --public")
    port = args.port
    if port is None:
        try:
            port = int(os.getenv("BAT_PORT_http") or "8765") if args.public else 8765
        except ValueError:
            parser.error("BAT_PORT_http 必须为数字")
    server_type = PublicServer if args.public else ThreadingHTTPServer
    server = server_type((args.bind, port), Handler)
    server.daemon_threads = True  # 停止服务时不因请求处理线程无限等待
    server.pipeline = SearchPipeline(public=args.public)
    server.account_manager = None if args.public else AccountManager()
    url = f"http://{args.bind}:{server.server_port}/"
    print(f"CyberField: {url}", flush=True)
    if args.open_browser:
        try:
            webbrowser.open(url)
        except OSError:
            print("请手动打开上方地址", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        close_services(server)


if __name__ == "__main__":
    main()
