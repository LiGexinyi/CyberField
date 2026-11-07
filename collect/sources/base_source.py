"""数据源抽象接口（BaseSource）。

所有源适配器必须继承 BaseSource 并实现 search()。
上层（orchestrator / demo）只依赖本接口，不感知具体源。
"""

from abc import ABC, abstractmethod

from collect.post import Post


class SourceUnavailable(Exception):
    """源不可用（未登录 / 被风控 / 工具损坏 / 已下架）。

    调度器捕获此异常后跳过该源，继续用其他源，保证"一个挂了不影响另一个"。
    """


class BaseSource(ABC):
    """数据源适配器接口。

    子类需声明：
        name       适配器名（写入 source_adapter 字段，用于追溯）
        platforms  该源支持的规范化平台名列表
    """

    name: str = "base"
    platforms: list[str] = []

    @abstractmethod
    def search(self, keyword: str, platform: str | None = None,
               limit: int = 20) -> list[Post]:
        """搜索关键词，返回统一 Post 列表。

        失败时抛 SourceUnavailable（带可读原因），不要静默返回空。
        平台不支持时返回空列表即可。
        """

    def health_check(self) -> bool:
        """源是否可用（工具存在、登录态有效等）。默认 True，子类按需重写。"""
        return True
