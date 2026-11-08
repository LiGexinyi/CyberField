"""微博游客态搜索适配器（访客激活流程，免登录）。

微博网页/移动接口需要访客 Cookie（SUB/SUBP）。游客态激活流程
（参考 astron-weibo-mcp / yt-dlp 的实现）：
1. 访问 m.weibo.cn 主页（prime，种基础 Cookie）；
2. 请求 visitor.passport.weibo.cn/visitor/genvisitor 获取 tid；
3. 请求 visitor.passport.weibo.cn/visitor/visitor?a=incarnate&t=tid 换发 SUB/SUBP；
4. 带访客 Cookie 请求 m.weibo.cn 搜索接口。

无需登录、无验证码，属于对公开数据的合规访问。被风控或接口变动时
抛 SourceUnavailable，由调度器跳过该源。
"""

import json
import random
import re
import urllib.parse
from email.utils import parsedate_to_datetime

from collect.post import Post, normalize_platform
from collect.sources.base_source import BaseSource, SourceUnavailable
from collect.sources.http_client import HttpSession

# 首页（prime / Referer）+ 访客激活 + 搜索接口。
_HOME_URL = "https://m.weibo.cn/"
_GEN_URL = "https://visitor.passport.weibo.cn/visitor/genvisitor"
_ACTIVATE_URL = "https://visitor.passport.weibo.cn/visitor/visitor"
_SEARCH_API = "https://m.weibo.cn/api/container/getIndex"
# 微博正文/话题里带 <a> / <span> 等 HTML 标签，需要剥掉。
_TAG_RE = re.compile(r"<[^>]+>")


class WeiboApiSource(BaseSource):
    name = "weibo_api"
    platforms = ["weibo"]

    def __init__(self, **kwargs):
        # 每个实例独立 Cookie 会话；_visitor_ok 标记访客已激活（避免重复激活）。
        self._session = HttpSession()
        self._visitor_ok = False

    def search(self, keyword: str, platform: str | None = None,
               limit: int = 20) -> list[Post]:
        """搜索关键词，返回微博帖子列表。"""
        # 只服务微博平台（兼容 MediaCrawler 码 wb）。
        if normalize_platform(platform or "weibo") != "weibo":
            return []
        if not self._activate_visitor():
            raise SourceUnavailable("微博访客激活失败（风控或接口变动）")
        cid = f"100103type=1&q={keyword}"
        try:
            data = self._session.get_json(
                _SEARCH_API,
                params={"containerid": cid, "page": 1},
                referer=f"https://m.weibo.cn/search?containerid={urllib.parse.quote(cid)}",
            )
        except Exception as exc:
            raise SourceUnavailable(f"微博搜索请求失败：{exc}") from exc
        if data.get("ok") not in (1, True, "1"):
            raise SourceUnavailable(f"微博接口 ok={data.get('ok')}，可能被风控")
        cards = (data.get("data") or {}).get("cards") or []
        # 微博卡片有两种形态：直接含 mblog 的普通卡片，以及 card_group 卡片组
        # （组内混有用户/话题/微博卡片）。全部提取 mblog，并按 mid 去重。
        seen: set[str] = set()
        posts = []
        for card in cards:
            if not isinstance(card, dict):
                continue
            batch: list[dict] = []
            if card.get("mblog"):
                batch.append(card["mblog"])
            for gc in card.get("card_group") or []:
                if isinstance(gc, dict) and gc.get("mblog"):
                    batch.append(gc["mblog"])
            for mblog in batch:
                mid = str(mblog.get("id") or "")
                if mid and mid in seen:
                    continue
                if mid:
                    seen.add(mid)
                posts.append(self._to_post(mblog, keyword))
        return posts[:max(int(limit), 1)]

    # ---------------------------------------------------------------- 内部实现
    def _activate_visitor(self) -> bool:
        """生成并激活访客 Cookie，成功返回 True（重复调用幂等）。"""
        if self._visitor_ok:
            return True
        try:
            # 1. 访问主页，先种基础 Cookie。
            self._session.get(_HOME_URL)
            # 2. genvisitor 获取访客 tid。
            cb = f"gen_cb_{random.randint(100000, 999999)}"
            status, text = self._session.get(
                _GEN_URL,
                params={"cb": cb, "fp": "0", "tid": "", "from": "weibo",
                        "_rand": str(random.random())},
            )
            if status != 200:
                return False
            m = re.search(r"\((\{.*\})\)", text)
            if not m:
                return False
            data = json.loads(m.group(1)).get("data") or {}
            tid = str(data.get("tid") or "").strip()
            if not tid:
                return False
            # 3. incarnate 换发访客 Cookie；遍历 w 值直到拿到 SUB+SUBP。
            for w in ("2", "3", "1", "0"):
                self._session.get(
                    _ACTIVATE_URL,
                    params={"a": "incarnate", "t": tid, "w": w, "c": "095",
                            "gc": "", "cb": "cross_domain", "from": "weibo",
                            "_rand": str(random.random())},
                    referer=_HOME_URL,
                )
                if self._session.get_cookie("SUB") and self._session.get_cookie("SUBP"):
                    self._visitor_ok = True
                    return True
        except Exception:
            return False
        return False

    def _to_post(self, mblog: dict, keyword: str) -> Post:
        """把微博搜索结果的一条 mblog 记录转成统一 Post。"""
        # 微博没有独立标题，正文做 title 和 text。
        text = _TAG_RE.sub("", mblog.get("text") or "").strip()
        mid = str(mblog.get("id") or "")
        url = f"https://m.weibo.cn/status/{mid}" if mid else ""
        user = mblog.get("user") or {}
        return Post(
            platform="weibo",
            title=text[:40],
            text=text,
            url=url,
            author=user.get("screen_name") or "",
            published_at=self._parse_time(mblog.get("created_at")),
            source_adapter=self.name,
            keyword=keyword,
            extra={
                "mid": mid,
                "uid": user.get("id"),
                "reposts_count": mblog.get("reposts_count"),
                "comments_count": mblog.get("comments_count"),
                "attitudes_count": mblog.get("attitudes_count"),
            },
        )

    @staticmethod
    def _parse_time(raw) -> str:
        """把微博时间（Sun Aug 23 17:13:48 +0800 2026）转成统一格式。"""
        from collect.time_utils import normalize_time
        return normalize_time(raw)
