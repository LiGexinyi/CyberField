"""统一帖子数据契约（Post）与平台名规范化。

这是整个多源框架的核心约定：任何适配器产出的数据都必须转成 Post，
上层（调度、入库、统计、展示）只依赖这个结构，不关心具体源内部格式。
"""

from dataclasses import dataclass, field


# MediaCrawler 平台码 → 规范化平台名（后续新源也沿用同一套规范名）。
PLATFORM_NAME_MAP = {
    "xhs": "xiaohongshu",
    "bili": "bilibili",
    "wb": "weibo",
    "zhihu": "zhihu",
    "dy": "douyin",
    "ks": "kuaishou",
    "tieba": "tieba",
}

# 规范化平台名 → 人类可读中文名（用于展示）。
PLATFORM_LABELS = {
    "xiaohongshu": "小红书",
    "bilibili": "B站",
    "weibo": "微博",
    "zhihu": "知乎",
    "douyin": "抖音",
    "kuaishou": "快手",
    "tieba": "贴吧",
    "douban": "豆瓣",
}


def normalize_platform(raw: str) -> str:
    """把各源的平台码统一成规范化平台名，未知原样返回。"""
    return PLATFORM_NAME_MAP.get(raw, raw)


def platform_label(name: str) -> str:
    """规范化平台名 → 中文标签，未知返回原名。"""
    return PLATFORM_LABELS.get(name, name)


@dataclass
class Post:
    """统一帖子记录。

    字段说明：
        platform      规范化平台名（xiaohongshu / bilibili / weibo / zhihu ...）
        title         帖子标题
        text          帖子正文 / 摘要
        url           原链接（溯源与去重依据）
        author        作者昵称（源数据，未经自动脱敏）
        published_at  发布时间（尽量规范为 YYYY-MM-DD HH:MM:SS）
        source_adapter 数据来自哪个适配器（追溯来源）
        keyword       由哪个搜索关键词采到
        extra         平台附加数据（互动数等，统计时可选使用）
    """

    platform: str
    title: str
    text: str
    url: str
    author: str
    published_at: str
    source_adapter: str
    keyword: str = ""
    extra: dict = field(default_factory=dict)

    record_type: str = "post"

    def __post_init__(self):
        """统一时间并保留原始时间，避免不同源混排。"""
        from collect.time_utils import normalize_time
        self.extra = dict(self.extra or {})
        if self.published_at:
            self.extra.setdefault("published_at_raw", self.published_at)
        self.published_at = normalize_time(self.published_at)
        self.platform = normalize_platform(self.platform)
