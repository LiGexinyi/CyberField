"""采集数据的清洗模块（浏览器模式核心）。

对齐旧 clean_posts.py 的清洗规则，但作用于统一 Post 列表（内存级），
不碰文件、不依赖 pandas，纯标准库。典型流程：
    采集原始 posts → clean_posts() → 呈现给用户 / 决定是否入库

规则：
    1. 删除空文本（strip 后为空）；豆瓣等源可能产生空 text，一并剔除；
    2. 按 (platform, url) 去重，保留首次出现（与调度器去重互补，
       这里的 url 已统一构造过，进一步保证唯一）；
    3. 按 published_at 升序排序（空时间排最后），便于展示时间线。

返回 (cleaned, stats)：cleaned 为清洗后的 Post 列表；
stats 含 total / empty_removed / dup_removed / final。
"""

from collect.post import Post


def clean_posts(posts: list[Post]) -> tuple[list[Post], dict]:
    """清洗采集到的帖子列表（内存操作，不落盘）。

    参数：
        posts : 采集器返回的 Post 列表（可能含空文本 / 跨页重复）
    返回：
        (cleaned, stats)
        cleaned : 清洗后的 Post 列表
        stats   : {"total", "empty_removed", "dup_removed", "final"}
    """
    total = len(posts)

    # ---- 第 1 步：删除空文本 ----
    kept = [p for p in posts if (p.text or "").strip()]
    empty_removed = total - len(kept)

    # ---- 第 2 步：按 (platform, url) 去重，保留首次出现 ----
    seen: set[tuple[str, str]] = set()
    uniq: list[Post] = []
    for p in kept:
        key = (p.platform, p.url) if p.url else id(p)
        if key not in seen:
            seen.add(key)
            uniq.append(p)
    dup_removed = len(kept) - len(uniq)

    # ---- 第 3 步：按发布时间升序排序（空时间排最后） ----
    def _sort_key(p: Post):
        t = (p.published_at or "").strip()
        return (t == "", t)

    cleaned = sorted(uniq, key=_sort_key)

    stats = {
        "total": total,
        "empty_removed": empty_removed,
        "dup_removed": dup_removed,
        "final": len(cleaned),
    }
    return cleaned, stats
