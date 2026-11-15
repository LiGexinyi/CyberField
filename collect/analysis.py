"""样本统计纯函数：输入Post列表，返回现有图表使用的字典。

保留现有日期、短语、作者分组口径，不把结构重构混同于分析算法升级。
口径说明（阶段5核对）：topics 是正文正则短语的出现频次，不是主题模型；
groups 是「平台 × 作者」的计数，不是真实群体识别。后端 API 键保持不变，
前端展示名已改为「高频短语 / 平台与作者」，避免误导。
"""
import re
from collections import Counter
from collect.post import PLATFORM_LABELS


def build_analysis(posts) -> dict:
    """时间热度 / 相关话题 / 相关群体 / 平台构成。"""
    timeline = Counter()
    topics = Counter()
    groups = Counter()
    platforms = Counter()
    for p in posts:
        if p.published_at:
            timeline[p.published_at[:10]] += 1
        platforms[p.platform] += 1
        text = f"{p.title or ''} {p.text or ''}"
        for w in re.findall(r"[\u4e00-\u9fff]{2,6}|[a-zA-Z]{3,}", text):
            topics[w] += 1
        author = p.author or "未知作者"
        groups[(p.platform, author)] += 1
    return {
        "timeline": sorted(timeline.items()),
        "topics": [{"word": w, "count": n}
                   for w, n in topics.most_common(24) if n > 1],
        "groups": [{"label": f"{PLATFORM_LABELS.get(pl, pl)} · {author}",
                    "count": n}
                   for (pl, author), n in groups.most_common(20)],
        "platforms": [{"platform": pl, "count": n}
                      for pl, n in platforms.most_common()],
    }
