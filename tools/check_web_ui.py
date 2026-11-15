"""前端离线浏览器验收：需要可选Playwright环境，不发真实平台请求。

从项目根运行python -B tools/check_web_ui.py；浏览器路径可用--chrome覆盖。
仅启动临时本机服务和独立无头浏览器，API全部由模拟响应替代。
"""
import argparse
import json
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collect.web_app import Handler


class QuietHandler(Handler):
    """仅在测试中关闭访问日志。"""
    def log_message(self, format, *args):
        """保持验收输出简洁。"""
        pass


def main():
    """验证模块加载、搜索、分页、总结、分析和账号面板。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--chrome", default=r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    args = parser.parse_args()
    from playwright.sync_api import sync_playwright, expect
    server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
    server.pipeline = SimpleNamespace()
    server.account_manager = SimpleNamespace()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    calls, errors = [], []
    mode = {"summary": "running"}
    progress_polls = {"count": 0}
    accounts = [
        {"platform": "xhs", "label": "小红书", "state": "no_profile", "state_label": "未登录", "login_supported": True},
        {"platform": "bili", "label": "B站", "state": "logged_in", "state_label": "已登录", "nickname": "模拟用户", "login_supported": True},
        {"platform": "wb", "label": "微博", "state": "expired", "state_label": "已过期", "login_supported": True},
        {"platform": "douban", "label": "豆瓣", "state": "no_profile", "login_supported": False, "note": "暂不支持登录"},
    ]

    def api(route):
        """所有API请求在浏览器侧拦截，后端真实账号服务不会被调用。"""
        request = route.request
        path = urlsplit(request.url).path
        body = request.post_data_json if request.method == "POST" else {}
        calls.append((request.method, path, body))
        status = 200
        if path == "/api/accounts":
            payload = {"accounts": accounts}
        elif path == "/api/search/start":
            word = body.get("keyword")
            # prog 词走“任务在途 → 轮询进度 → 完成”路径；其余词结果已就绪。
            payload = {"ok": True, "task": word,
                       "status": "running" if word == "prog" else "done"}
        elif path == "/api/search/progress":
            word = (parse_qs(urlsplit(request.url).query).get("task") or [""])[0]
            if word == "prog":
                progress_polls["count"] += 1
                if progress_polls["count"] < 3:
                    payload = {"task": word, "status": "running",
                               "step": f"正在搜索「{word}」…", "collected": 5}
                else:
                    payload = {"task": word, "status": "done", "total": 2}
            else:
                payload = {"task": word, "status": "done", "total": 0}
        elif path == "/api/search":
            word, number = body.get("keyword"), body.get("page", 1)
            if word == "error":
                status, payload = 500, {"error": "mock failure"}
            else:
                row = {"platform": "bilibili", "title": f"资料-{word}", "text": "sample", "url": f"https://example.invalid/{number}", "author": "模拟作者", "published_at": "2026-11-13 12:00:00", "summary": None, "summary_status": "running", "comments": [], "extra": {"play": 10}}
                payload = {"keyword": word, "rows": [] if word == "empty" else [row], "total": 0 if word == "empty" else 2, "page": number, "pages": 1 if word == "empty" else 2, "expanded": [word], "errors": []}
        elif path == "/api/summaries":
            done = mode["summary"] != "running"
            payload = {"states": [{"url": f"https://example.invalid/{i}", "done": done, "status": mode["summary"], "summary": "模拟摘要" if mode["summary"] == "completed" else None, "comments": [], "error": None} for i in (1, 2)]}
        elif path == "/api/analysis":
            payload = {"timeline": [["2026-11-13", 2]], "topics": [{"word": "模拟话题", "count": 2}], "groups": [{"label": "模拟作者", "count": 2}]}
        elif path == "/api/login":
            payload = {"status": "starting"} if request.method == "POST" else {"status": "qr_ready", "qr": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aN1sAAAAASUVORK5CYII="}
        elif path == "/api/login/cancel":
            payload = {"ok": True, "cancelled": True}
        elif path == "/api/verify":
            payload = {"ok": True} if request.method == "POST" else {"state": "logged_in", "state_label": "已登录"}
        elif path == "/api/logout":
            accounts[1].update(state="no_profile", state_label="未登录", nickname=None)
            payload = {"ok": True}
        else:
            raise AssertionError("Unexpected API " + path)
        route.fulfill(status=status, content_type="application/json", body=json.dumps(payload, ensure_ascii=False))

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=args.chrome, headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("dialog", lambda dialog: dialog.accept())
            # 乱序模拟：在页面内延迟 slow 词的真实请求，让两个搜索真正并发、
            # 且 slow 的响应晚到。阻塞路由处理器会让请求串行化，达不到目的。
            page.add_init_script("""
                const orig = window.fetch;
                window.fetch = function(input, init){
                  try{
                    const u = input instanceof Request ? new URL(input.url) : new URL(String(input), location.origin);
                    if(u.pathname === '/api/search'){
                      const body = init && init.body ? JSON.parse(init.body) : {};
                      if(body.keyword === 'slow'){
                        return new Promise((resolve, reject) => {
                          setTimeout(() => orig.call(window, input, init).then(resolve, reject), 1200);
                        });
                      }
                    }
                  }catch(e){}
                  return orig.apply(window, arguments);
                };
            """)
            page.route("**/api/**", api)
            page.goto(f"http://127.0.0.1:{server.server_port}", wait_until="networkidle")
            page.locator("#q").fill("topic")
            page.locator("#q").press("Enter")
            expect(page.locator(".record")).to_have_count(1)
            expect(page.locator(".summary")).to_contain_text("总结生成中")
            expect(page.locator(".row-foot a")).to_have_attribute("href", "https://example.invalid/1")
            mode["summary"] = "completed"
            expect(page.locator(".summary")).to_have_text("模拟摘要", timeout=6000)
            page.get_by_role("button", name="下一页 →", exact=True).click()
            expect(page.locator(".page-num")).to_have_text("第 2 / 2 页")
            expect(page.locator(".row-foot a")).to_have_attribute("href", "https://example.invalid/2")
            page.locator("#tab-analysis").click()
            expect(page.locator(".bar")).to_have_count(1)
            page.locator('input[value="topics"]').check()
            expect(page.locator(".wordcloud")).to_contain_text("模拟话题")
            page.locator('input[value="groups"]').check()
            expect(page.locator("#chart")).to_contain_text("模拟作者")
            page.locator("#user-btn").click()
            expect(page.locator(".acct-card")).to_have_count(4)
            page.locator('[data-plat="xhs"]').get_by_role("button", name="登录", exact=True).click()
            expect(page.locator("#qr-holder img")).to_have_count(1, timeout=6000)
            page.locator("#qr-cancel").click()
            expect(page.locator("#login-modal")).to_be_hidden(timeout=3000)
            # 等待轮询响应完成，不用固定sleep猜测定时器何时执行。
            with page.expect_response("**/api/verify?platform=wb", timeout=6000):
                page.locator('[data-plat="wb"]').get_by_role("button", name="检查状态", exact=True).click()
            assert any(method == "GET" and path == "/api/verify" for method, path, _ in calls)
            page.locator('[data-plat="bili"]').get_by_role("button", name="退出", exact=True).click()
            expect(page.locator('[data-plat="bili"] .badge')).to_have_text("未登录")
            page.locator("#acct-close").click()
            page.locator("#q").fill("empty")
            page.locator("#go").click()
            expect(page.locator("#list")).to_contain_text("没有匹配结果")
            page.locator("#q").fill("error")
            page.locator("#go").click()
            expect(page.locator("#meta")).to_contain_text("搜索失败")
            # 进度验收：prog 词任务在途时展示真实步骤与条数，完成后出结果。
            page.locator("#q").fill("prog")
            page.locator("#go").click()
            expect(page.locator("#search-progress-text")).to_contain_text("正在搜索", timeout=3000)
            expect(page.locator(".record h3").first).to_have_text("资料-prog", timeout=8000)
            expect(page.locator("#search-progress")).to_be_hidden(timeout=3000)
            # 乱序验收：先搜 slow（模拟响应延迟 1.2s），马上搜 fast（立即返回）。
            # 页面必须始终显示 fast，迟到的 slow 响应不得覆盖最新结果。
            page.locator("#q").fill("slow")
            page.locator("#go").click()
            page.locator("#q").fill("fast")
            page.locator("#go").click()
            expect(page.locator(".record h3").first).to_have_text("资料-fast")
            page.wait_for_timeout(1800)  # 等迟到的 slow 响应返回
            expect(page.locator(".record h3").first).to_have_text("资料-fast")
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert not errors, errors
            browser.close()
        print("PASS: ES modules, search+progress, pagination, summary polling, analysis views, account panel, QR/cancel, verify, logout, empty/error feedback, mobile width; no JS errors.")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


if __name__ == "__main__":
    main()
