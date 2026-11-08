"""豆瓣游客态搜索适配器。

豆瓣官方 API 已停止对个人开放，本适配器改用豆瓣移动端公开搜索接口
（游客态、免登录）：
    https://m.douban.com/rexxar/api/v2/search/movie?q=关键词&count=20&start=0

返回的是影视条目，不是用户帖子。上映年份、字幕及推测导演只保存到 extra。
作者与帖子发布时间留空，record_type 为 catalog_item。

接口用 start 偏移分页（每页 20 条），翻页需在页间小延迟，防触发风控。

被风控或接口变动时抛 SourceUnavailable，由调度器跳过该源。
"""

import re
import time

from collect.post import Post
from collect.sources.base_source import BaseSource, SourceUnavailable
from collect.sources.http_client import HttpSession

# 移动端首页（作为 Referer）+ 移动端公开搜索接口。
_REFERER = "https://m.douban.com/"
_SEARCH_API = "https://m.douban.com/rexxar/api/v2/search/movie"
# 翻页上限：每页 20 条，最多 3 页 ≈ 60 条。豆瓣对高频请求返回 need_login(403)，
# 上限设小 + 页间延迟，控制单次采集请求量（触发 403 时会降级保留已拿数据）。
_MAX_PAGES = 3

# card_subtitle 中常见的类型词（用于把「类型段」与「人名段」区分开）。
_GENRE_WORDS = {
    "剧情", "喜剧", "动作", "爱情", "科幻", "动画", "儿童", "奇幻",
    "冒险", "悬疑", "惊悚", "犯罪", "灾难", "纪录片", "真人秀", "脱口秀",
    "综艺", "音乐", "歌舞", "戏曲", "古装", "历史", "战争", "传记",
    "运动", "短片", "同性", "情色", "家庭", "西部", "恐怖", "武侠",
    "神话", "侦探", "谍战", "医疗", "校园", "偶像", "犯罪", "励志",
}


def _parse_subtitle(subtitle: str) -> tuple[str, list[str]]:
    """解析 card_subtitle → (导演, 主演列表)。

    典型格式：「地区 / 类型... / 导演 / 主演...」；类型段可能缺失。
    地区段固定跳过；「全部由类型词组成」的段视为类型段跳过，
    其余段视为人名段，第一段即导演。
    """
    parts = [p.strip() for p in subtitle.split("/") if p.strip()]
    if not parts:
        return "", []
    names: list[str] = []
    for part in parts[1:]:  # 跳过地区段
        tokens = [t for t in re.split(r"\s+", part) if t]
        if tokens and all(t in _GENRE_WORDS for t in tokens):
            continue  # 类型段
        names.append(part)
    if not names:
        return "", []
    return names[0], names[1:]


class DoubanApiSource(BaseSource):
    name = "douban_api"
    platforms = ["douban"]

    def __init__(self, **kwargs):
        self._session = HttpSession()

    def search(self, keyword: str, platform: str | None = None,
               limit: int = 20) -> list[Post]:
        """搜索关键词，返回豆瓣书影音条目列表（必要时翻页凑够 limit）。

        豆瓣 rexxar 搜索接口用 start 偏移分页（start=20 是第 2 页）。
        limit 超过一页时递增 start 继续取，直到凑满 limit 或结果取完。
        注意：豆瓣对短时高频请求会返回 need_login(403)，因此：
          - 翻页上限较低（3 页 ≈ 60 条），页间小延迟；
          - 翻页中一旦触发 403，保留已拿到页降级返回，不导致整次失败
            （单页用户至少能拿到第一页结果）。
        """
        # 只服务豆瓣平台；调度器传了别的平台码时静默返回空。
        if (platform or "douban") != "douban":
            return []
        target = max(int(limit), 1)
        posts: list[Post] = []
        start = 0
        while len(posts) < target and start < _MAX_PAGES * 20:
            try:
                data = self._session.get_json(
                    _SEARCH_API,
                    params={"q": keyword, "count": 20, "start": start},
                    referer=_REFERER,
                )
            except Exception as exc:
                if posts:
                    # 降级：已有一页以上结果，直接返回，避免整次采集失败。
                    break
                raise SourceUnavailable(f"豆瓣接口请求失败：{exc}") from exc
            items = data.get("items") or []
            for it in items:
                if isinstance(it, dict):
                    posts.append(self._to_post(it, keyword))
            if len(items) < 20:
                break  # 不满一页 = 没有更多结果了
            start += 20
            if len(posts) < target:
                time.sleep(0.8)  # 页间延迟，降低连续请求触发 need_login 风险
        return posts[:target]

    # ---------------------------------------------------------------- 内部实现
    def _to_post(self, it: dict, keyword: str) -> Post:
        """把豆瓣搜索结果的一条记录转成统一 Post。"""
        target = it.get("target") or {}
        sid = str(target.get("id") or "")
        # 条目 url 字段可能缺失，用 subject id 构造唯一链接，
        # 保证调度器按 (platform, url) 去重时不会把多条压成一条。
        url = target.get("url") or (
            f"https://movie.douban.com/subject/{sid}/" if sid else "")
        subtitle = target.get("card_subtitle") or ""
        abstract = target.get("abstract") or ""
        rating = target.get("rating") if isinstance(target.get("rating"), dict) else {}
        director, actors = _parse_subtitle(subtitle)
        return Post(
            platform="douban",
            title=target.get("title") or "",
            text=subtitle or abstract or target.get("title") or "",
            url=url,
            author="",  # 影视条目没有发帖作者
            published_at="",
            record_type="catalog_item",
            source_adapter=self.name,
            keyword=keyword,
            extra={
                "subject_id": sid,
                "type": it.get("target_type") or target.get("type") or "",
                "rating": rating.get("value"),
                "rating_count": rating.get("count"),
                "year": target.get("year"),
                "director_inferred": director,
                "actors": actors,
            },
        )
