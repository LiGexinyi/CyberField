"""数据源适配器注册表。新增源时：
1. 在本目录新建一个 *_source.py 实现 BaseSource；
2. 在下方 AVAILABLE_SOURCES 里登记，即可被 demo 使用，旧源不受影响。
"""

from collect.sources.base_source import BaseSource, SourceUnavailable
from collect.sources.mediacrawler_source import MediaCrawlerSource

# 已登记的适配器（name -> 工厂）。以后加 zhihu_mcp / weibo_mcp 等就在这里追加。
AVAILABLE_SOURCES: dict[str, type[BaseSource]] = {
    MediaCrawlerSource.name: MediaCrawlerSource,
}


def create_source(name: str, **kwargs) -> BaseSource:
    """按名称创建适配器实例，未知名称抛 KeyError。"""
    return AVAILABLE_SOURCES[name](**kwargs)
