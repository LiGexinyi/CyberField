# -*- coding: utf-8 -*-
"""知乎搜索辅助脚本（CyberField 自有实现，复用 MediaCrawler 的知乎客户端）。

背景：网页搜索工作台此前只有 B站/豆瓣/微博游客态 + 小红书登录态；知乎内容
需要登录态。本脚本只做「登录态搜索列表」：启动无头浏览器读取专用档案的会话
cookie（z_c0/d_c0），复用 MediaCrawler 的 ZhiHuClient（zhihu 签名算法）调
搜索接口翻页，把搜索结果转成统一 JSON 输出，供 collect/sources/zhihu_source.py
转换为 Post。

用法（由 collect/sources/zhihu_source.py 调用，解释器为 MediaCrawler venv，
工作目录为 MediaCrawler 根目录，保证 import config / media_platform / libs
可解析）：
    python tools/zhihu_search_standalone.py --profile <browser_data/zhihu_user_data_dir> \\
        --keyword <关键词> [--limit 20]

stdout 协议：整个流程只输出一行 JSON。
    {"ok": true, "items": [...]}
    {"ok": false, "reason": "login_expired|browser_launch_failed|...", "hint": "..."}
"""
import argparse
import asyncio
import io
import json
import os
import sys
from urllib.parse import quote


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


def _w(obj) -> None:
    """输出一行 JSON 结果并立即刷出，避免管道缓冲卡住读取端。"""
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _serialize(content) -> dict:
    """把 MediaCrawler 的 ZhihuContent 转成轻量 dict（不含哈希/内部字段）。"""
    return {
        "content_id": str(getattr(content, "content_id", "") or ""),
        "content_type": str(getattr(content, "content_type", "") or ""),
        "content_url": str(getattr(content, "content_url", "") or ""),
        "title": str(getattr(content, "title", "") or ""),
        "desc": str(getattr(content, "desc", "") or ""),
        "voteup_count": getattr(content, "voteup_count", 0) or 0,
        "comment_count": getattr(content, "comment_count", 0) or 0,
        "created_time": getattr(content, "created_time", 0) or 0,
        "updated_time": getattr(content, "updated_time", 0) or 0,
        "user_nickname": str(getattr(content, "user_nickname", "") or ""),
    }


async def run(profile: str, keyword: str, limit: int, chrome: str) -> dict:
    # 脚本常驻在 MediaCrawler 目录下运行；cwd 加入 sys.path 以便导入其模块。
    sys.path.insert(0, os.getcwd())
    from playwright.async_api import async_playwright
    from media_platform.zhihu.client import ZhiHuClient
    from tools import utils

    domain = "https://www.zhihu.com"
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
    )
    async with async_playwright() as p:
        try:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=profile,
                executable_path=chrome,
                headless=True,
                viewport={"width": 1280, "height": 900},
                user_agent=user_agent,
                args=["--no-first-run", "--no-default-browser-check"],
            )
        except Exception as exc:
            return {"ok": False, "reason": "browser_launch_failed",
                    "hint": f"知乎浏览器启动失败（档案可能被占用）：{exc}"}
        try:
            stealth = os.path.join(os.getcwd(), "libs", "stealth.min.js")
            if os.path.isfile(stealth):
                await context.add_init_script(path=stealth)
            page = context.pages[0] if context.pages else await context.new_page()
            try:
                await page.goto(domain, wait_until="domcontentloaded",
                                timeout=30000)
            except Exception as exc:
                return {"ok": False, "reason": "page_load_failed",
                        "hint": f"知乎首页加载失败：{exc}"}
            await asyncio.sleep(3)
            # 知乎搜索接口需要先访问搜索页拿搜索态 cookie（首页 cookie 不够）。
            q_enc = quote(keyword)
            try:
                await page.goto(
                    domain + "/search?q=" + q_enc
                    + "&search_source=Guess&utm_content=search_hot&type=content",
                    wait_until="domcontentloaded", timeout=30000)
            except Exception as exc:
                return {"ok": False, "reason": "page_load_failed",
                        "hint": f"知乎搜索页加载失败：{exc}"}
            await asyncio.sleep(5)
            cookie_str, cookie_dict = await utils.convert_browser_context_cookies(
                context, urls=[domain])
            client = ZhiHuClient(
                proxy=None,
                headers={
                    "accept": "*/*",
                    "accept-language": "zh-CN,zh;q=0.9",
                    "cookie": cookie_str,
                    "priority": "u=1, i",
                    # httpx 按 ASCII 编码请求头：referer 里中文关键词必须
                    # 百分号编码，否则 httpx 直接抛 UnicodeEncodeError。
                    "referer": (domain + "/search?q=" + q_enc
                                + "&time_interval=a_year&type=content"),
                    "user-agent": user_agent,
                    "x-api-version": "3.0.91",
                    "x-app-za": "OS=Web",
                    "x-requested-with": "fetch",
                    "x-zse-93": "101_3_3.0",
                },
                playwright_page=page,
                cookie_dict=cookie_dict,
            )
            try:
                if not await client.pong():
                    return {"ok": False, "reason": "login_expired",
                            "hint": "知乎登录态失效，请在账号面板重新登录"}
                items = []
                page_no = 1
                while len(items) < limit and page_no <= 5:
                    res = await client.get_note_by_keyword(
                        keyword=keyword, page=page_no, page_size=20)
                    batch = res or []
                    if not batch:
                        break  # 没有更多结果
                    items.extend(_serialize(c) for c in batch)
                    if len(batch) < 20:
                        break  # 不满一页 = 取完了
                    page_no += 1
                    await asyncio.sleep(1.0)
            except Exception as exc:
                return {"ok": False, "reason": "api_error",
                        "hint": f"知乎搜索请求失败：{exc}"}
            return {"ok": True, "items": items[:limit]}
        finally:
            try:
                await context.close()
            except Exception:
                pass


def main() -> int:
    # 与登录脚本一致的 UTF-8 兜底（Windows 控制台可能是 GBK，避免乱码传回）。
    if sys.stdout and hasattr(sys.stdout, "buffer"):
        if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                          errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True,
                        help="专用浏览器档案目录 browser_data/zhihu_user_data_dir")
    parser.add_argument("--keyword", required=True, help="搜索关键词")
    parser.add_argument("--limit", type=int, default=20,
                        help="最多返回的条目数（接口单页上限 20，脚本自动翻页）")
    parser.add_argument("--chrome", default=None, help="系统 Chrome/Edge 路径")
    args = parser.parse_args()

    chrome = args.chrome or _find_browser()
    if not chrome:
        _w({"ok": False, "reason": "browser_missing",
            "hint": "未找到可用的 Chrome/Edge，请先安装浏览器"})
        return 1
    try:
        result = asyncio.run(run(args.profile, args.keyword, args.limit, chrome))
    except Exception as exc:
        result = {"ok": False, "reason": "unexpected", "hint": f"{exc}"}
    _w(result)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
