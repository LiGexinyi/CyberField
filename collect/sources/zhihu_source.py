"""知乎登录态搜索适配器（轻量：只取搜索列表，不抓逐条详情/评论）。

调用方式与小红书一致：以子进程跑 MediaCrawler venv 的
tools/zhihu_search_standalone.py（复用其 ZhiHuClient 签名客户端，不改外部
项目），登录态来自专用档案 browser_data/zhihu_user_data_dir。未登录 / 会话
失效时抛 SourceUnavailable（带可读原因），由调度器跳过，不影响其他源。

子进程调用、输出解析与错误文案映射见 ScriptSearchSource 基类。
"""

from collect.post import Post
from collect.sources.script_search_source import ScriptSearchSource
from collect import settings


class ZhihuApiSource(ScriptSearchSource):
    name = "zhihu_api"
    platforms = ["zhihu"]
    platform = "zhihu"
    platform_label = "知乎"
    default_script = settings.ZHIHU_SEARCH_SCRIPT
    profile_dir = "zhihu_user_data_dir"
    default_timeout = 90

    def _to_post(self, item: dict, keyword: str) -> Post:
        """把搜索项转为统一 Post。搜索项来自脚本序列化的 ZhihuContent。"""
        title = str(item.get("title") or "")
        desc = str(item.get("desc") or "")
        return Post(
            platform="zhihu",
            title=title or desc[:40],
            text=desc or title,
            url=str(item.get("content_url") or ""),
            author=str(item.get("user_nickname") or ""),
            published_at=str(item.get("created_time") or 0),
            source_adapter=self.name,
            keyword=keyword,
            extra={
                "voteup": item.get("voteup_count"),
                "comment": item.get("comment_count"),
                "content_id": item.get("content_id"),
                "content_type": item.get("content_type"),
            },
        )
