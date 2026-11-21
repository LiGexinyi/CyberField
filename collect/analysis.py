"""按帖子计数的时间分布和显式话题共现。"""
import re
from collections import Counter
from datetime import date
from itertools import chain
from collect import store


def combined_posts(live, keyword, include_catalog=False, include_archive=True):
    """合并当前搜索与本地库，按平台和链接去重。"""
    from types import SimpleNamespace
    archived = ()
    if include_archive:
        archived = (SimpleNamespace(**row) for row in store.query_posts(keyword=keyword, limit=None))
    seen = set()
    for post in chain(live, archived):
        key = (post.platform, post.url)
        if key not in seen and (post.record_type == "post" or include_catalog and post.record_type == "catalog_item"):
            seen.add(key)
            yield post


def build_analysis(posts, keyword=""):
    """同一帖子中的同名标签计一次；只有有效日期参与每日发帖量。"""
    days, topics = Counter(), Counter()
    total = tagged = 0
    for post in posts:
        total += 1
        try:
            day = date.fromisoformat((post.published_at or "")[:10])
            days[day.isoformat()] += 1
        except ValueError:
            pass
        text = f"{post.title or ''} {post.text or ''}"
        tags = re.findall(r"#([\w·-]{1,64})(?=#|\s|$|[^\w·-])", text)
        supplied = post.extra.get("tags") or []
        if isinstance(supplied, str):
            supplied = supplied.split(",")
        labels = {v.strip(" #").casefold() for v in [*tags, *supplied] if isinstance(v, str)}
        labels -= {"", keyword.strip().casefold()}
        if labels:
            tagged += 1
            topics.update(labels)
    return {"total": total, "dated": sum(days.values()), "tagged": tagged,
            "timeline": sorted(days.items()),
            "topics": [{"word": w, "count": n} for w, n in sorted(topics.items(), key=lambda item: (-item[1], item[0]))[:30]]}
