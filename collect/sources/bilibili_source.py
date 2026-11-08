"""B站游客态搜索适配器。

直接调用 B站公开搜索接口（免登录、游客态）：
    https://api.bilibili.com/x/web-interface/search/type?search_type=video&keyword=xxx

流程：先访问 www.bilibili.com 主页拿 buvid3 等 Cookie（游客身份标识），
再带 Referer 请求搜索接口，返回的视频列表规范化为统一 Post。

无需安装任何额外依赖（纯标准库 HTTP），无登录、无验证码，
属于对公开数据的合规访问。被风控或接口变动时抛 SourceUnavailable，
由调度器跳过该源，不影响其他源。
"""

import re
from collect.time_utils import normalize_time

from collect.post import Post, normalize_platform
from collect.sources.base_source import BaseSource, SourceUnavailable
from collect.sources.http_client import HttpSession

# 主页：先访问拿 Cookie；搜索接口：视频搜索。
_HOME_URL = "https://www.bilibili.com/"
_SEARCH_API = "https://api.bilibili.com/x/web-interface/search/type"
# 搜索结果标题里会带 <em class="keyword">高亮标签</em>，需要剥掉。
_TAG_RE = re.compile(r"<[^>]+>")
# 翻页上限：每页约 20 条，最多 8 页 ≈ 160 条（防风控与接口滥用）。
_MAX_PAGES = 8


class BilibiliApiSource(BaseSource):
    name = "bilibili_api"
    platforms = ["bilibili"]

    def __init__(self, **kwargs):
        # 每个实例独立 Cookie 会话（模拟一次浏览器访问）。
        self._session = HttpSession()

    def search(self, keyword: str, platform: str | None = None,
               limit: int = 20) -> list[Post]:
        """搜索关键词，返回 B站视频帖子列表（必要时翻页凑够 limit）。

        B站搜索接口每页固定约 20 条，limit 超过一页时自动翻页，
        直到凑满 limit 或翻完可用页为止（上限 8 页，防风控）。
        """
        # 只服务 B站平台；调度器传了别的平台码时静默返回空。
        if normalize_platform(platform or "bilibili") != "bilibili":
            return []
        target = max(int(limit), 1)
        try:
            # 第一步：访问主页拿游客 Cookie，否则搜索接口返回 -412 风控。
            self._session.get(_HOME_URL)
            posts: list[Post] = []
            page = 1
            while len(posts) < target and page <= _MAX_PAGES:
                data = self._session.get_json(
                    _SEARCH_API,
                    params={"search_type": "video", "keyword": keyword,
                            "page": page},
                    referer=_HOME_URL,
                )
                if data.get("code") != 0:
                    raise SourceUnavailable(
                        f"B站接口返回 code={data.get('code')} "
                        f"msg={data.get('message')}")
                results = (data.get("data") or {}).get("result") or []
                for r in results:
                    if isinstance(r, dict):
                        posts.append(self._to_post(r, keyword))
                if not results:
                    break  # 没更多结果了
                page += 1
        except Exception as exc:
            raise SourceUnavailable(f"B站接口请求失败：{exc}") from exc
        return posts[:target]

    # ---------------------------------------------------------------- 内部实现
    def _to_post(self, r: dict, keyword: str) -> Post:
        """把 B站搜索结果的一条记录转成统一 Post。"""
        # 去掉 <em> 高亮标签，标题/简介才是干净文本。
        title = _TAG_RE.sub("", r.get("title") or "").strip()
        desc = _TAG_RE.sub("", r.get("description") or "").strip()
        url = r.get("arcurl") or ""
        # pubdate 是 Unix 秒级时间戳，转成统一时间格式。
        pubdate = r.get("pubdate")
        published = ""
        if pubdate:
            published = normalize_time(pubdate)
        return Post(
            platform="bilibili",
            title=title,
            text=desc or title,
            url=url,
            author=r.get("author") or "",
            published_at=published,
            source_adapter=self.name,
            keyword=keyword,
            extra={
                "bvid": r.get("bvid"),
                "play": r.get("play"),              # 播放量
                "video_review": r.get("video_review"),  # 弹幕数
                "favorites": r.get("favorites"),    # 收藏数
            },
        )
