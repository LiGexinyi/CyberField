"""B站游客态搜索适配器。

调用 B站公开搜索接口（免登录、游客态）：
    https://api.bilibili.com/x/web-interface/search/type

支持两种内容形态，各自独立深翻页（每页约 20 条、上限 50 页）：
    video   视频（标题/简介/播放量）
    article 专栏文章（标题/摘要/阅读量/评论数）

一个关键词视频 + 专栏合计约 1800 条，是纯游客态下最大规模的数据源。
页间有小延迟降低风控概率；触发 -412 时早页重试一次、晚页降级保留已拿数据。

无需登录、无验证码，属于对公开数据的合规访问。被风控或接口变动时抛
SourceUnavailable，由调度器跳过该源，不影响其他源。
"""

import re
import time
from collect.time_utils import normalize_time

from collect.post import Post, normalize_platform
from collect.sources.base_source import BaseSource, SourceUnavailable
from collect.sources.http_client import HttpSession

# 主页：先访问拿 Cookie；搜索接口：按内容类型搜索。
_HOME_URL = "https://www.bilibili.com/"
_SEARCH_API = "https://api.bilibili.com/x/web-interface/search/type"
_VIEW_API = "https://api.bilibili.com/x/web-interface/view"  # 详情：完整简介/分P/时长
# 搜索结果标题里会带 <em class="keyword">高亮标签</em>，需要剥掉。
_TAG_RE = re.compile(r"<[^>]+>")
# 简介里的时序章节（「00:00 开场」「12:30 总结」）可当作内容概览提取。
_OUTLINE_RE = re.compile(r"^\s*\d{1,2}:\d{2}(?::\d{2})?\s+")
# 深翻页：每页约 20 条，上限 50 页 ≈ 1000 条/类型（实测深翻稳定，
# 用页间延迟控风控；触发 -412 时早页重试一次、晚页降级保留已拿数据）。
_MAX_PAGES = 50
_PAGE_DELAY = 0.3     # 页间延迟，降低 -412 风控概率
_RETRY_DELAY = 3.0    # 早页遇风控时的重试间隔
# 一次搜索覆盖的内容形态：视频 + 专栏文章。
_SEARCH_TYPES = ("video", "article")


class BilibiliApiSource(BaseSource):
    name = "bilibili_api"
    platforms = ["bilibili"]

    def __init__(self, detail_limit: int = 0, **kwargs):
        # 每个实例独立 Cookie 会话（模拟一次浏览器访问）。
        self._session = HttpSession()
        # detail_limit > 0 时对前 N 条视频抓详情接口，补完整简介/时序章节概览；
        # 0 = 不抓（保持深翻页批量速度）。逐条详情较慢，批量建议 20~50。
        self.detail_limit = max(int(detail_limit or 0), 0)

    def search(self, keyword: str, platform: str | None = None,
               limit: int = 20) -> list[Post]:
        """搜索关键词，返回 B站视频+专栏帖子列表（必要时深翻页凑够 limit）。

        每种内容形态分别翻页（上限 _MAX_PAGES），合并后按 limit 截断；
        limit 很大时 video 与 article 各分约一半额度，单关键词合计约 1800 条。
        """
        # 只服务 B站平台；调度器传了别的平台码时静默返回空。
        if normalize_platform(platform or "bilibili") != "bilibili":
            return []
        target = max(int(limit), 1)
        per_type = max(1, target // len(_SEARCH_TYPES))
        posts: list[Post] = []
        try:
            # 第一步：访问主页拿游客 Cookie，否则搜索接口返回 -412 风控。
            self._session.get(_HOME_URL)
            for st in _SEARCH_TYPES:
                got = self._search_pages(keyword, st, per_type)
                posts.extend(got)
                if len(posts) >= target:
                    break
            if self.detail_limit:
                posts = self._enrich_details(posts[:self.detail_limit])
        except Exception as exc:
            raise SourceUnavailable(f"B站接口请求失败：{exc}") from exc
        return posts[:target]

    # ---------------------------------------------------------------- 内部实现
    def _search_pages(self, keyword: str, search_type: str,
                      limit: int) -> list[Post]:
        """按内容类型深翻页，返回该类型的 Post 列表（≤ limit）。"""
        posts: list[Post] = []
        page = 1
        while len(posts) < limit and page <= _MAX_PAGES:
            try:
                data = self._session.get_json(
                    _SEARCH_API,
                    params={"search_type": search_type, "keyword": keyword,
                            "page": page},
                    referer=_HOME_URL,
                )
            except Exception as exc:
                if posts:
                    break  # 已有一部分结果，降级返回
                raise SourceUnavailable(f"B站接口请求失败：{exc}") from exc
            if data.get("code") != 0:
                # 风控(-412)或接口异常：早页重试一次，晚页保留已拿数据。
                if posts or page > 5:
                    break
                time.sleep(_RETRY_DELAY)
                data = self._session.get_json(
                    _SEARCH_API,
                    params={"search_type": search_type, "keyword": keyword,
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
                    posts.append(self._to_post(r, keyword, search_type))
            if not results:
                break  # 没更多结果了
            page += 1
            if len(posts) < limit and page <= _MAX_PAGES:
                time.sleep(_PAGE_DELAY)
        return posts

    def _enrich_details(self, posts: list[Post]) -> list[Post]:
        """对视频抓详情接口：补完整简介(desc_full)、简介里的时序章节(outline)、
        时长/分区/完整互动数。单条失败跳过，不影响整体。"""
        enriched: list[Post] = []
        for p in posts:
            bvid = (p.extra or {}).get("bvid")
            if not bvid:
                enriched.append(p)
                continue
            try:
                view = self._session.get_json(
                    _VIEW_API, params={"bvid": bvid}, referer=_HOME_URL)
                d = view.get("data") or {}
                extra = dict(p.extra or {})
                desc_full = (d.get("desc") or "").strip()
                if desc_full:
                    extra["desc_full"] = desc_full
                    outline = [ln.strip() for ln in desc_full.splitlines()
                               if _OUTLINE_RE.match(ln.strip())]
                    if outline:
                        extra["outline"] = outline[:12]
                if d.get("duration"):
                    extra["duration"] = d.get("duration")
                if d.get("tname"):
                    extra["tname"] = d.get("tname")
                # 用详情接口的完整互动数补上搜索页可能缺失的字段。
                stat = d.get("stat") or {}
                for api_key, extra_key in (("view", "play"), ("danmaku", "danmaku"),
                                           ("favorite", "favorites"), ("like", "like"),
                                           ("reply", "reply")):
                    if stat.get(api_key) is not None and not extra.get(extra_key):
                        extra[extra_key] = stat[api_key]
                p.extra = extra
            except Exception:
                pass  # 单条详情失败不影响整体
            enriched.append(p)
        return enriched

    def _to_post(self, r: dict, keyword: str, search_type: str) -> Post:
        """把一条搜索结果转成统一 Post（video 与 article 字段不同）。"""
        # 去掉 <em> 高亮标签，标题/简介才是干净文本。
        title = _TAG_RE.sub("", r.get("title") or "").strip()
        desc = _TAG_RE.sub("", r.get("desc") or "").strip()
        if search_type == "article":
            cid = r.get("id")
            url = f"https://www.bilibili.com/read/cv{cid}" if cid else ""
            # pubdate 是时间戳；pub_time 是文本日期，都能被统一转换。
            raw_time = r.get("pubdate") or r.get("pub_time") or ""
            return Post(
                platform="bilibili",
                title=title,
                text=desc or title,
                url=url,
                author=r.get("author") or "",
                published_at=normalize_time(raw_time),
                source_adapter=self.name,
                keyword=keyword,
                extra={
                    "article_id": cid,
                    "view": r.get("view"),           # 阅读量
                    "like": r.get("like"),           # 点赞
                    "reply": r.get("reply"),         # 评论数
                    "category": r.get("category_name"),
                },
            )
        # video：pubdate 是 Unix 秒级时间戳，转成统一时间格式。
        pubdate = r.get("pubdate")
        published = normalize_time(pubdate) if pubdate else ""
        return Post(
            platform="bilibili",
            title=title,
            text=desc or title,
            url=r.get("arcurl") or "",
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
