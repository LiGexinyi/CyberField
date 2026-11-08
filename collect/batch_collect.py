"""批量采集工具：多关键词 × 多源 → 清洗 → 可选入库，一次跑出大样本。

用法（项目根目录）：
    # 不入库（浏览器模式，用完即弃）
    python -m collect.batch_collect --keywords "奶龙,奶龙梗,变异奶龙" --limit 500

    # 入库（清洗后写入 collect.db）
    python -m collect.batch_collect --keywords "奶龙,奶龙梗" --limit 800 --save

    # 关键词较多时用文件（每行一个）
    python -m collect.batch_collect --keywords-file data/keywords.txt --limit 500 --save

参数：
    --keywords        关键词列表，逗号/分号/空格分隔
    --keywords-file   关键词文件（每行一个，与 --keywords 二选一）
    --platforms       平台码，逗号分隔（默认 bili,douban,wb）
    --sources         适配器名，逗号分隔（默认游客态三源）
    --limit           每词每平台上限（B站深翻页单词可达 ~1000）
    --save            入库；不带则只采集不入库
"""

import argparse
import re
import sys
import time

from collect import orchestrator

# 平台码 → 默认适配器的对应关系（批量默认只走游客态免登录源）。
_PLATFORM_SOURCES = {
    "bili": "bilibili_api",
    "douban": "douban_api",
    "wb": "weibo_api",
}


def split_keywords(text: str) -> list[str]:
    """按逗号/分号/空白拆分关键词列表。"""
    return [p.strip() for p in re.split(r"[,;，；\s]+", text) if p.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keywords", help="关键词，逗号/分号/空格分隔")
    parser.add_argument("--keywords-file", help="关键词文件（每行一个）")
    parser.add_argument("--platforms", default="bili,douban,wb")
    parser.add_argument("--sources", default=None,
                        help="适配器名，逗号分隔；默认按平台码自动匹配")
    parser.add_argument("--limit", type=int, default=500,
                        help="每词每平台最多条数")
    parser.add_argument("--save", action="store_true",
                        help="入库；不带则只采集不入库（浏览器模式）")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="关键词之间间隔秒数（默认 1s，防平台风控）")
    args = parser.parse_args()

    keywords = split_keywords(args.keywords or "")
    if args.keywords_file:
        with open(args.keywords_file, encoding="utf-8") as f:
            keywords += split_keywords(f.read())
    keywords = list(dict.fromkeys(keywords))  # 去重保序
    if not keywords:
        print("错误：没有关键词。用 --keywords 或 --keywords-file 提供。")
        sys.exit(1)

    platforms = tuple(split_keywords(args.platforms))
    if args.sources:
        sources = tuple(split_keywords(args.sources))
    else:
        sources = tuple(_PLATFORM_SOURCES[p] for p in platforms
                        if p in _PLATFORM_SOURCES)
    if not sources:
        print("错误：没有可用的适配器（platforms 不在 bili/douban/wb 时需显式 --sources）。")
        sys.exit(1)

    mode = "入库" if args.save else "浏览器模式（不入库）"
    print(f"批量采集：{len(keywords)} 个关键词 × 平台 {platforms} × 源 {sources}，"
          f"limit={args.limit}，{mode}\n")

    grand_total = 0
    grand_inserted = 0
    for i, kw in enumerate(keywords, 1):
        print(f"[{i}/{len(keywords)}] 采集「{kw}」…", flush=True)
        t0 = time.time()
        try:
            posts, errors, summary = orchestrator.collect(
                kw, platforms=platforms, limit=args.limit,
                source_names=sources, save=args.save)
        except Exception as exc:
            print(f"    ✗ 失败：{exc}")
            continue
        secs = time.time() - t0
        print(f"    → {len(posts)} 条（耗时 {secs:.0f}s；"
              f"入库 {summary.get('inserted', 0)} / 跳过 {summary.get('skipped', 0)} / "
              f"删空 {summary.get('empty_removed', 0)} / 去重 {summary.get('dup_removed', 0)}）")
        for e in errors:
            print(f"    ⚠ {e}")
        grand_total += len(posts)
        grand_inserted += summary.get("inserted", 0)
        if i < len(keywords) and args.delay:
            time.sleep(args.delay)

    print(f"\n=== 完成：{len(keywords)} 个关键词，累计采集 {grand_total} 条，"
          f"入库 {grand_inserted} 条 ===")
    if not args.save:
        print("本次为浏览器模式，未入库。需要入库请加 --save。")


if __name__ == "__main__":
    main()
