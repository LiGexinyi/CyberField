# -*- coding: utf-8 -*-
"""小红书搜索辅助脚本（CyberField 自有实现，复用 MediaCrawler 的 xhs 客户端）。

背景：网页搜索工作台此前只有 B站/豆瓣/微博游客态；小红书需要登录态且
MediaCrawler 全流程（浏览器 + 逐条详情 + 评论）对单次网页搜索过重。
本脚本只做「登录态搜索列表」：启动无头浏览器读取专用档案的会话 cookie，
复用 MediaCrawler 的 XiaoHongShuClient（xhshow 纯算法签名）调一次搜索接口，
把搜索结果原样 JSON 输出，供 collect/sources/xhs_source.py 转换为 Post。

用法（由 collect/sources/xhs_source.py 调用，解释器为 MediaCrawler venv，
工作目录为 MediaCrawler 根目录，保证 import config / media_platform 可解析）：
    python tools/xhs_search_standalone.py --profile <browser_data/xhs_user_data_dir> \\
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


async def run(profile: str, keyword: str, limit: int, chrome: str) -> dict:
    # 脚本常驻在 MediaCrawler 目录下运行；cwd 加入 sys.path 以便导入其模块。
    sys.path.insert(0, os.getcwd())
    from playwright.async_api import async_playwright
    from media_platform.xhs.client import XiaoHongShuClient
    from media_platform.xhs.field import SearchSortType
    from tools import utils

    domain = "https://www.xiaohongshu.com"
    # 与 MediaCrawler create_xhs_client 保持一致：搜索接口对请求头风控敏感，
    # 缺 sec-* / priority 等头会被当作机器人，返回空结果。
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
                    "hint": f"小红书浏览器启动失败（档案可能被占用）：{exc}"}
        try:
            # 与 MediaCrawler 一致：注入 stealth 反检测脚本，否则搜索接口
            # 会把请求当机器人过滤，返回空结果。
            stealth = os.path.join(os.getcwd(), "libs", "stealth.min.js")
            if os.path.isfile(stealth):
                await context.add_init_script(path=stealth)
            page = context.pages[0] if context.pages else await context.new_page()
            try:
                await page.goto(domain, wait_until="domcontentloaded", timeout=30000)
            except Exception as exc:
                return {"ok": False, "reason": "page_load_failed",
                        "hint": f"小红书页面加载失败：{exc}"}
            # 等 SPA 跑起来并刷新会话 cookie（web_session 等），否则搜索接口
            # 会因旧会话被过滤，返回成功但零结果。
            await asyncio.sleep(3)
            cookie_str, cookie_dict = await utils.convert_browser_context_cookies(
                context, urls=[domain])
            client = XiaoHongShuClient(
                proxy=None,
                headers={
                    "accept": "application/json, text/plain, */*",
                    "accept-language": "zh-CN,zh;q=0.9",
                    "cache-control": "no-cache",
                    "content-type": "application/json;charset=UTF-8",
                    "origin": domain,
                    "pragma": "no-cache",
                    "priority": "u=1, i",
                    "referer": domain + "/",
                    "sec-ch-ua": '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"Windows"',
                    "sec-fetch-dest": "empty",
                    "sec-fetch-mode": "cors",
                    "sec-fetch-site": "same-site",
                    "user-agent": user_agent,
                    "Cookie": cookie_str,
                },
                playwright_page=page,
                cookie_dict=cookie_dict,
            )
            try:
                if not await client.pong():
                    return {"ok": False, "reason": "login_expired",
                            "hint": "小红书登录态失效，请在账号面板重新登录"}
            except Exception as exc:
                return {"ok": False, "reason": "api_error",
                        "hint": f"小红书会话校验失败：{exc}"}
            items = []
            page_no = 1
            while len(items) < limit and page_no <= 3:
                # 小红书接口对连续请求极敏感（翻页过快会触发 461 验证码），
                # 页间多停一会儿；翻页失败只保留已拿到的主词页，不整体失败。
                try:
                    res = await client.get_note_by_keyword(
                        keyword=keyword, page=page_no,
                        page_size=20,  # 小红书搜索接口页大小固定为 20，其他值会静默返回空
                        sort=SearchSortType.GENERAL,
                    )
                except Exception as exc:
                    if page_no == 1:
                        return {"ok": False, "reason": "api_error",
                                "hint": f"小红书搜索请求失败：{exc}"}
                    break
                batch = res.get("items", []) or []
                if isinstance(batch, dict):
                    batch = list(batch.values())
                batch = [it for it in batch
                         if (it.get("model_type") or "")
                         not in ("rec_query", "hot_query")]
                if not batch:
                    break  # 没有更多结果
                items.extend(batch)
                if len(batch) < 20:
                    break  # 不满一页 = 取完了
                page_no += 1
                await asyncio.sleep(3.0)
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
                        help="专用浏览器档案目录 browser_data/xhs_user_data_dir")
    parser.add_argument("--keyword", required=True, help="搜索关键词")
    parser.add_argument("--limit", type=int, default=20,
                        help="最多返回的笔记条数（接口单页上限 20）")
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
