"""小红书登录态搜索适配器（轻量：只取搜索列表，不抓逐条详情/评论）。

调用方式与 login/verify 一致：以子进程跑 MediaCrawler venv 的
tools/xhs_search_standalone.py（复用其 xhshow 签名客户端，不改外部项目），
登录态来自专用档案 browser_data/xhs_user_data_dir。未登录 / 会话失效时抛
SourceUnavailable（带可读原因），由调度器跳过，不影响 B站/豆瓣/微博。

子进程调用、输出解析与错误文案映射见 ScriptSearchSource 基类。
"""

from collect.post import Post
from collect.sources.script_search_source import ScriptSearchSource
from collect import settings


class XhsApiSource(ScriptSearchSource):
    name = "xhs_api"
    platforms = ["xiaohongshu"]
    platform = "xiaohongshu"
    platform_label = "小红书"
    default_script = settings.XHS_SEARCH_SCRIPT
    profile_dir = "xhs_user_data_dir"
    default_timeout = 60

    def _to_post(self, item: dict, keyword: str) -> Post:
        """把搜索项转为统一 Post。搜索项结构可能带 note_card 包装，两者都兼容；
        列表卡片标题在 display_title 且没有 desc 正文——正文缺省时回退用标题，
        避免被清洗器当空文本删除。"""
        card = item.get("note_card") or item
        nid = str(card.get("id") or card.get("note_id") or item.get("id") or "")
        token = str(card.get("xsec_token") or item.get("xsec_token") or "")
        src = str(card.get("xsec_source") or item.get("xsec_source") or "pc_search")
        inter = card.get("interact_info") or item.get("interact_info") or {}
        title = (card.get("display_title") or card.get("title")
                 or card.get("desc") or "")
        text = str(card.get("desc") or title or "")
        url = (f"https://www.xiaohongshu.com/explore/{nid}"
               f"?xsec_token={token}&xsec_source={src}")
        return Post(
            platform="xiaohongshu",
            title=str(title),
            text=text,
            url=url,
            author=str((card.get("user") or {}).get("nickname") or ""),
            published_at="",
            source_adapter=self.name,
            keyword=keyword,
            extra={
                "liked": inter.get("liked_count"),
                "collected": inter.get("collected_count"),
                "comment": inter.get("comment_count"),
                "shared": inter.get("shared_count"),
                "note_id": nid,
                "xsec_token": token,
                "type": card.get("type"),
            },
        )
