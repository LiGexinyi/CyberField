# -*- coding: utf-8 -*-
"""知乎登录辅助脚本（CyberField 自有实现，不依赖 MediaCrawler 内部登录流程）。

背景：MediaCrawler 的知乎扫码登录在部分页面 30 秒内读不到二维码 canvas 会
整体崩溃退出，导致网页工作台永远拿不到二维码。本脚本用系统 Chrome + 专用
档案直连知乎扫码页，并支持“窗口内扫码”兜底，失败原因逐行回传。

用法（由 collect/account_manager.py 调用，解释器为 MediaCrawler venv）：
    python tools/zhihu_login_standalone.py --profile <browser_data/zhihu_user_data_dir>

stdout 协议（与 login_standalone.py 兼容，供 account_manager._login_reader 解析）：
    QR:<base64>        二维码（前端展示）
    QR_MISSING:<原因>   未能截取页面二维码（浏览器窗口保留，可窗口内扫码）
    LOG:<文本>         过程日志（仅诊断，不展示敏感内容）
    FATAL:<原因>       致命错误或扫码超时，直接退出（退出码 1）
    LOGGED_IN          登录成功（z_c0 已写入专用档案），退出码 0

行为：
1. 用本机系统 Chrome 启动“专用档案”持久上下文（headless=False，独立窗口，
   与日常浏览器隔离；cookie 写回 browser_data/zhihu_user_data_dir）；
2. 打开 passport.zhihu.com/login 直出扫码页；读不到二维码时回退打开
   www.zhihu.com 并尝试点开登录弹窗；
3. 多选择器等待二维码 canvas 并截屏输出 QR:；
4. 轮询 z_c0 cookie 判断登录成功；期间用户也可直接在打开的浏览器窗口内扫码；
5. 成功输出 LOGGED_IN 后关闭浏览器，退出码 0。
"""
import argparse
import base64
import io
import os
import sys
import time

# 与登录脚本一致的 UTF-8 兜底（Windows 控制台可能是 GBK，避免乱码传回）。
if sys.stdout and hasattr(sys.stdout, "buffer"):
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                      errors="replace")

# 知乎扫码页二维码 canvas 常见类名/特征，逐个尝试。
QR_SELECTORS = (
    "canvas.Qrcode-qrcode",
    "canvas[alt='二维码']",
    "div.Qrcode-container canvas",
    "canvas[class*='Qrcode']",
    "canvas[id*='qrcode']",
    "canvas[class*='qrcode']",
)

_INDEX_URL = "https://www.zhihu.com/"
# passport.zhihu.com 已下线（DNS 不再解析）；知乎现在的二维码登录页是 /signin，
# 登出态下访问 www.zhihu.com 也会自动跳到该页。
_LOGIN_URL = "https://www.zhihu.com/signin"


def _w(message: str) -> None:
    """向 stdout 输出一行协议消息并立即刷出，避免管道缓冲卡住读取端。"""
    sys.stdout.write(message + "\n")
    sys.stdout.flush()


def _find_browser():
    """定位本机可用的 Chrome / Edge（专用档案不受日常浏览器影响）。"""
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def _find_qr(page):
    """多选择器寻找二维码 canvas 并截屏为 base64；找不到返回 None。"""
    for selector in QR_SELECTORS:
        try:
            loc = page.locator(selector)
            loc.first.wait_for(state="visible", timeout=8000)
            if loc.count() > 0:
                b64 = base64.b64encode(loc.first.screenshot()).decode("ascii")
                if b64:
                    return b64
        except Exception:
            continue
    return None


def _try_open_login_modal(page) -> bool:
    """知乎首页未自动弹登录窗时，点击可见的登录入口打开弹窗。"""
    for selector in ("text=登录", "button:has-text('登录')",
                     "a:has-text('登录')"):
        try:
            loc = page.locator(selector)
            loc.first.wait_for(state="visible", timeout=4000)
            loc.first.click()
            return True
        except Exception:
            continue
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True,
                        help="专用浏览器档案目录 browser_data/zhihu_user_data_dir")
    parser.add_argument("--chrome", default=None, help="系统 Chrome/Edge 路径")
    parser.add_argument("--headless", action="store_true",
                        help="无头模式（自动化验证用；正常登录保持可见窗口供兜底扫码）")
    parser.add_argument("--timeout", type=int, default=600,
                        help="等待扫码的最长秒数")
    args = parser.parse_args()

    chrome = args.chrome or _find_browser()
    if not chrome:
        _w("FATAL:未找到可用的 Chrome/Edge，请先安装浏览器")
        return 1
    _w("LOG:使用浏览器 " + chrome)

    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            try:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=args.profile,
                    executable_path=chrome,
                    headless=args.headless,
                    viewport={"width": 1280, "height": 900},
                    accept_downloads=False,
                    args=["--no-first-run", "--no-default-browser-check"],
                )
            except Exception as exc:
                _w(f"FATAL:浏览器启动失败（档案可能被占用，请关闭残留的登录窗口后重试） {exc}")
                return 1
            try:
                page = context.pages[0] if context.pages else context.new_page()
                # 0) 已登录快速路径：档案 cookie 里已有 z_c0，无需再扫码。
                if any(c.get("name") == "z_c0" for c in context.cookies()):
                    _w("LOGGED_IN")
                    return 0
                b64 = None
                # 1) 直连扫码页（www.zhihu.com/signin 为知乎现用的二维码登录页）。
                try:
                    page.goto(_LOGIN_URL, wait_until="domcontentloaded",
                              timeout=45000)
                except Exception as exc:
                    _w(f"LOG:扫码页打开失败 {exc}，回退到知乎首页")
                b64 = _find_qr(page)
                # 2) 回退：首页 + 手动点开登录弹窗。
                if not b64:
                    try:
                        page.goto(_INDEX_URL, wait_until="domcontentloaded",
                                  timeout=45000)
                    except Exception as exc:
                        _w(f"LOG:知乎首页打开失败 {exc}")
                    _try_open_login_modal(page)
                    time.sleep(1.0)
                    b64 = _find_qr(page)
                if b64:
                    _w("QR:" + b64)
                else:
                    _w("QR_MISSING:未能自动截取二维码，请在已打开的浏览器窗口内扫码登录")
                # 3) 轮询 z_c0，确认登录完成；窗口内扫码同样走此判定。
                deadline = time.monotonic() + args.timeout
                while time.monotonic() < deadline:
                    if any(c.get("name") == "z_c0" for c in context.cookies()):
                        time.sleep(3)   # 留时间让知乎落盘其余会话 cookie
                        _w("LOGGED_IN")
                        return 0
                    time.sleep(2)
                _w("FATAL:等待扫码超时，未检测到登录态")
                return 1
            finally:
                try:
                    context.close()
                except Exception:
                    pass
    except Exception as exc:
        _w(f"FATAL:知乎登录流程异常 {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
