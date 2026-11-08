"""CyberField 多源采集 Demo —— 终端交互式浏览试用（无图形界面）。

用法（在主项目根目录）：
    python -m collect.demo_cli
    # 或
    python collect/demo_cli.py

菜单：
    [1] 采集新关键词   调用各适配器真实搜索（可多平台、多源；询问是否入库）
    [2] 浏览本地库     查看已采集帖子（可按关键词/平台过滤）
    [3] 统计概览       平台分布 / 关键词分布 / 作者 TOP / 时间范围
    [4] 导出 CSV/JSON  导出本地库全部记录
    [5] 退出
    也可以直接输入一个关键词：浏览器模式采集（清洗后展示、不入库，用完即弃）。

说明：已接入的源——
    mediacrawler  外部工具 MediaCrawler（小红书/B站/微博/知乎等，需扫码登录）
    bilibili_api  B站游客态公开搜索接口（免登录）
    douban_api    豆瓣移动端公开搜索接口（免登录）
    weibo_api     微博游客态公开搜索接口（访客激活，免登录）
将来新增源只需在 collect/sources/ 注册新适配器，本入口不变。
"""

import json
import sys
from pathlib import Path

# 允许两种启动方式：python -m collect.demo_cli 与 python collect/demo_cli.py
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if __name__ == "__main__" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from collect import orchestrator, store                      # noqa: E402
from collect.post import platform_label                      # noqa: E402

BANNER = r"""
 _  _ ___   _ _    _____ _           _   _
| || | __| | | |__| __  | |__  ___ _| |_| |
| __ | _|  | | / /| __ -| '_ \/ -_) | | . |
|_||_|_|   |_|_\_\|_____|_.__/\___|_\_|___|
  多源采集 Demo · 终端试用版（源：MediaCrawler / B站 / 豆瓣 / 微博游客态）
"""

MENU = """
  [1] 采集新关键词    [2] 浏览本地库    [3] 统计概览
  [4] 导出 CSV/JSON   [5] 退出
  直接输入关键词 = 执行采集。输入 ? 查看帮助。"""


def _clean(s: str) -> str:
    """清理用户输入：去 BOM / 零宽字符，再 trim（防止粘贴文本带隐形字符）。"""
    return s.strip().lstrip("\ufeff").strip()


def _fmt_el(s: str, width: int) -> str:
    """按显示宽度截断字符串（中文按 2 个显示宽度计）。"""
    s = s.replace("\n", " ").replace("\r", " ").strip()
    w = 0
    out = []
    for ch in s:
        w += 2 if ord(ch) > 127 else 1
        if w > width - 1:
            out.append("…")
            break
        out.append(ch)
    return "".join(out)


def _print_table(rows: list[dict], limit: int = 30, pageable: bool = False):
    """打印帖子列表：平台 | 作者 | 时间 | 标题 | 链接。

    limit  每页条数（默认 30）。
    pageable 为 True 时，超出 limit 进入交互分页：
        回车 = 下一页；q = 返回；数字 = 跳到第 N 条。
    为 False 时保持旧行为：只打印前 limit 条并提示未显示条数。
    """
    if type(limit) is not int or limit <= 0:
        raise ValueError("每页条数必须为正整数")
    if not rows:
        print("  （无记录）")
        return
    total = len(rows)
    page = 0
    while True:
        start = page * limit
        end = min(start + limit, total)
        print(f"  {total} 条记录，显示第 {start + 1}~{end} 条：")
        for r in rows[start:end]:
            title = _fmt_el(r.get("title") or "(无标题)", 30)
            author = _fmt_el(r.get("author") or "-", 12)
            time = _fmt_el(r.get("published_at") or "-", 19)
            url = r.get("url") or ""
            print(f"    [{platform_label(r.get('platform') or '')}] "
                  f"{author} | {time}")
            print(f"      {title}")
            print(f"      {url}")
        if end >= total:
            return
        if not pageable:
            print(f"  …其余 {total - end} 条未显示（浏览命令可缩小过滤范围）")
            return
        cmd = _clean(input(
            f"  （已显示 {end}/{total}）回车=下一页，q=返回，数字=跳到第 N 条："))
        if cmd.lower() in ("q", "quit", "exit"):
            return
        if cmd.isdigit():
            n = max(1, int(cmd))
            page = min((n - 1) // limit, (total - 1) // limit)
            continue
        page += 1


def _run_collect(keyword: str, plist: tuple, src_list: tuple,
                 limit: int = 20, save: bool = False):
    """执行采集 + 清洗 + 展示，返回 posts（供分页展示）。

    浏览器模式（save=False）：搜索结果清洗后直接呈现，不入库、用完即弃；
    入库模式（save=True）：清洗后写入 collect.db。
    """
    posts, errors, summary = orchestrator.collect(
        keyword, platforms=plist, limit=limit,
        source_names=src_list, save=save)
    if errors:
        print("  部分源不可用（已自动跳过，不影响其他源）：")
        for e in errors:
            print(f"    ✗ {e}")
    print(f"\n  采集完成：命中 {len(posts)} 条")
    if summary:
        print(f"  清洗：删空文本 {summary['empty_removed']} 条，"
              f"去重 {summary['dup_removed']} 条")
    if save:
        print(f"  已入库：新增 {summary['inserted']} 条，"
              f"跳过重复 {summary['skipped']} 条")
    else:
        print("  浏览器模式：本次结果未入库，关闭即失效")
    return posts


def cmd_collect():
    keyword = _clean(input("  请输入关键词："))
    if not keyword:
        return
    platforms = input(
        "  平台（默认 xhs,bili,douban,wb；逗号分隔多平台。\n"
        "    MediaCrawler 码：xhs/bili/wb/zhihu/dy/ks/tieba（需扫码登录）\n"
        "    游客态免登录：bilibili / douban / weibo）："
    ).strip() or "xhs,bili,douban,wb"
    src_line = input(
        "  源（默认游客态 bilibili_api,douban_api,weibo_api；逗号分隔多源，\n"
        "    如 mediacrawler,bilibili_api,douban_api,weibo_api）："
    ).strip() or "bilibili_api,douban_api,weibo_api"
    limit_s = input("  每平台条数（默认 20，B站支持翻页到更多）：").strip()
    limit = max(1, int(limit_s)) if limit_s.isdecimal() else 20
    save_s = input("  入库？(y=写入本地库 / 回车=浏览器模式不存)：").strip().lower()
    save = save_s in ("y", "yes", "是")
    plist = [p.strip() for p in platforms.split(",") if p.strip()]
    src_list = [s.strip() for s in src_line.split(",") if s.strip()]

    print(f"\n  正在用源 {src_list} 搜索「{keyword}」（平台 {plist}，每平台 {limit} 条）…")
    print("  ⚠ mediacrawler 平台首次使用会弹出 Chrome 窗口扫码登录；B站/豆瓣游客态无需登录。\n")
    posts = _run_collect(keyword, tuple(plist), tuple(src_list), limit, save)
    _print_table([p.__dict__ for p in posts], pageable=True)


def cmd_browse():
    kw = input("  过滤关键词（回车跳过）：").strip() or None
    pl = input("  过滤平台（回车跳过，如 xiaohongshu/bilibili）：").strip() or None
    limit_s = input("  显示条数（默认 30）：").strip()
    limit = max(1, int(limit_s)) if limit_s.isdecimal() else 30
    rows = store.query_posts(keyword=kw, platform=pl, limit=None)
    _print_table(rows, limit=limit, pageable=True)


def cmd_stats():
    s = store.stats()
    print(f"\n  本地库总条数：{s['total']}")
    print("  ── 平台分布 ──")
    for item in s["by_platform"]:
        print(f"    {platform_label(item['platform'])}：{item['count']} 条")
    print("  ── 关键词分布 ──")
    for item in s["by_keyword"]:
        print(f"    「{item['keyword']}」：{item['count']} 条")
    print("  ── 作者 TOP 10（按条数） ──")
    if s["top_authors"]:
        for i, item in enumerate(s["top_authors"], 1):
            print(f"    {i}. {item['author']}：{item['count']} 条")
    else:
        print("    （暂无作者数据）")
    if s["published_range"]["min"]:
        print("  ── 发布时间范围 ──")
        print(f"    {s['published_range']['min']}  ~  {s['published_range']['max']}")


def cmd_export():
    rows = store.export_rows()
    out_dir = Path(__file__).resolve().parent.parent / "data" / "export"
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "collected_posts.csv"
    json_path = out_dir / "collected_posts.json"
    import csv
    columns = list(rows[0]) if rows else ["keyword", "platform", "title", "text", "url", "author", "published_at", "source_adapter", "fetched_at"]
    # 空结果也覆盖 CSV，防止用户误读上次导出的旧数据。
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print(f"\n  已导出 {len(rows)} 条记录：")
    print(f"    CSV : {csv_path}")
    print(f"    JSON: {json_path}")


def main():
    print(BANNER)
    while True:
        print(MENU)
        choice = _clean(input("  > "))
        if choice == "1":
            cmd_collect()
        elif choice == "2":
            cmd_browse()
        elif choice == "3":
            cmd_stats()
        elif choice == "4":
            cmd_export()
        elif choice == "5" or choice.lower() in ("q", "quit", "exit"):
            print("  再见 👋")
            break
        elif choice == "?":
            print("  直接输入关键词 = 浏览器模式采集（清洗后展示、不入库）；\n"
                  "  菜单项如上，[1] 采集可询问是否入库。")
        elif choice:
            # 直接输入关键词 → 浏览器模式：B站+豆瓣+微博游客态，清洗后展示，不入库。
            keyword = _clean(choice)
            plist = ("bili", "douban", "wb")
            print(f"\n  正在调用 B站+豆瓣+微博 搜索「{keyword}」（游客态，免登录，浏览器模式）…")
            posts = _run_collect(keyword, plist,
                                 ("bilibili_api", "douban_api", "weibo_api"))
            _print_table([p.__dict__ for p in posts], pageable=True)
        print()


if __name__ == "__main__":
    main()
