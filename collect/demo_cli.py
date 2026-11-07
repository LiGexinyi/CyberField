"""CyberField 多源采集 Demo —— 终端交互式浏览试用（无图形界面）。

用法（在主项目根目录）：
    python -m collect.demo_cli
    # 或
    python collect/demo_cli.py

菜单：
    [1] 采集新关键词   调用 MediaCrawler 真实搜索（首次需扫码登录）
    [2] 浏览本地库     查看已采集帖子（可按关键词/平台过滤）
    [3] 统计概览       平台分布 / 关键词分布 / 作者 TOP / 时间范围
    [4] 导出 CSV/JSON  导出本地库全部记录
    [5] 退出
    也可以直接输入一个关键词，等价于执行 [1]。

说明：本次 Demo 接入的第一个源是 MediaCrawler（外部开源工具），
将来新增源只需在 collect/sources/ 注册新适配器，本入口不变。
"""

import json
import sys
from pathlib import Path

# 允许两种启动方式：python -m collect.demo_cli 与 python collect/demo_cli.py
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

sys.stdout.reconfigure(encoding="utf-8")

from collect import orchestrator, store                      # noqa: E402
from collect.post import platform_label                      # noqa: E402

BANNER = r"""
 _  _ ___   _ _    _____ _           _   _
| || | __| | | |__| __  | |__  ___ _| |_| |
| __ | _|  | | / /| __ -| '_ \/ -_) | | . |
|_||_|_|   |_|_\_\|_____|_.__/\___|_\_|___|
  多源采集 Demo · 终端试用版（首个源：MediaCrawler）
"""

MENU = """
  [1] 采集新关键词    [2] 浏览本地库    [3] 统计概览
  [4] 导出 CSV/JSON   [5] 退出
  直接输入关键词 = 执行采集。输入 ? 查看帮助。"""


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


def _print_table(rows: list[dict], limit: int = 30):
    """打印帖子列表：平台 | 作者 | 时间 | 标题 | 链接。"""
    if not rows:
        print("  （无记录）")
        return
    show = rows[:limit]
    print(f"  {len(rows)} 条记录，显示前 {min(limit, len(rows))} 条：")
    for r in show:
        title = _fmt_el(r.get("title") or "(无标题)", 30)
        author = _fmt_el(r.get("author") or "-", 12)
        time = _fmt_el(r.get("published_at") or "-", 19)
        url = _fmt_el(r.get("url") or "", 46)
        print(f"    [{platform_label(r.get('platform') or r['platform'])}] "
              f"{author} | {time}")
        print(f"      {title}")
        print(f"      {url}")
    if len(rows) > limit:
        print(f"  …其余 {len(rows) - limit} 条未显示（浏览命令可缩小过滤范围）")


def cmd_collect():
    keyword = input("  请输入关键词：").strip()
    if not keyword:
        return
    platforms = input("  平台（默认 xhs；逗号分隔可多平台，如 xhs,bili）：").strip() or "xhs"
    limit_s = input("  每平台条数（默认 20）：").strip()
    limit = int(limit_s) if limit_s.isdigit() else 20
    plist = [p.strip() for p in platforms.split(",") if p.strip()]

    print(f"\n  正在调用 MediaCrawler 搜索「{keyword}」（平台 {plist}，每平台 {limit} 条）…")
    print("  ⚠ 首次使用会弹出 Chrome 窗口，请扫码登录；后续自动复用登录态。\n")
    posts, errors, summary = orchestrator.collect(keyword, platforms=tuple(plist), limit=limit)
    if errors:
        print("  部分源不可用（已自动跳过，不影响其他源）：")
        for e in errors:
            print(f"    ✗ {e}")
    print(f"\n  采集完成：命中 {len(posts)} 条")
    if summary:
        print(f"  入库：新增 {summary['inserted']} 条，跳过重复 {summary['skipped']} 条")
    _print_table([p.__dict__ for p in posts])


def cmd_browse():
    kw = input("  过滤关键词（回车跳过）：").strip() or None
    pl = input("  过滤平台（回车跳过，如 xiaohongshu/bilibili）：").strip() or None
    limit_s = input("  显示条数（默认 30）：").strip()
    limit = int(limit_s) if limit_s.isdigit() else 30
    rows = store.query_posts(keyword=kw, platform=pl, limit=200)
    _print_table(rows, limit=limit)


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
    if rows:
        import csv
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
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
        choice = input("  > ").strip()
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
            print("  直接输入关键词 = 执行采集 [1]；菜单项如上。")
        elif choice:
            # 直接输入关键词 → 等价于采集
            keyword = choice
            platforms = "xhs"
            print(f"\n  正在调用 MediaCrawler 搜索「{keyword}」（默认平台 {platforms}）…")
            posts, errors, summary = orchestrator.collect(keyword, platforms=(platforms,))
            if errors:
                for e in errors:
                    print(f"    ✗ {e}")
            print(f"  命中 {len(posts)} 条；入库新增 "
                  f"{summary['inserted'] if summary else 0} 条，"
                  f"重复 {summary['skipped'] if summary else 0} 条")
            _print_table([p.__dict__ for p in posts])
        print()


if __name__ == "__main__":
    main()
