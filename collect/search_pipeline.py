"""搜索引擎式搜索管道：模糊扩展 → 多源搜索 → 评论增强 → LLM 总结 → 分析统计。

设计（会话式：搜完即弃，不写库）：
    1. fuzzy_expand：B站搜索建议（游客态）+ LLM（有 Key 时）扩展相关词，
       实现「主动模糊搜索、扩大搜索量」；
    2. run_search：主词多平台深搜 + 扩展词 B站补充，合并去重、按热度排序，
       结果缓存于服务内存；
    3. 后台线程为每条结果「尽力而为」抓评论（B站评论游客态 -404 会跳过，
       小红书从 MediaCrawler 已抓 JSONL 里读），有 LLM Key 时据此生成
       一小段总结（原帖 + 评论区），前端轮询取回；
    4. build_analysis：基于搜索结果统计时间热度 / 相关话题 / 相关群体，
       供前端「数据分析」视图使用。
"""

import re
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from collect import llm, orchestrator
from collect.post import PLATFORM_LABELS
from collect.sources.http_client import HttpSession

_HOME_URL = "https://www.bilibili.com/"
_SUG_URL = "https://s.search.bilibili.com/main/suggest"
_VIEW_API = "https://api.bilibili.com/x/web-interface/view"
_REPLY_API = "https://api.bilibili.com/x/v2/reply/main"
# 扩展词默认搜 B站（速度快）；主词搜全平台游客态三源。
_PLATFORMS = ("bili", "douban", "wb")
_SOURCES = ("bilibili_api", "douban_api", "weibo_api")
_MAX_WORDS = 6          # 模糊扩展后最多搜的词数
_MAX_COMMENTS = 3       # 每条结果最多取的热评数
_MAX_WORKERS = 4        # 评论/总结后台并发


class SearchPipeline:
    """一次搜索的生命周期管理（结果在内存，换词即弃）。"""

    def __init__(self):
        self._session = HttpSession()
        # url -> {"comments": [...], "summary": str|None}（由后台线程填充）
        self._summary_cache: dict[str, dict] = {}
        self._cache_lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=_MAX_WORKERS)
        self._cache: dict[str, dict] = {}   # keyword -> run_search 结果

    # ------------------------------------------------------------ 模糊扩展
    def fuzzy_expand(self, keyword: str) -> list[str]:
        """扩展相关搜索词：B站搜索建议（真实用户搜索）优先，LLM 补充。"""
        words = [keyword]
        try:
            self._session.get(_HOME_URL)  # 游客 cookie
            sug = self._session.get_json(_SUG_URL,
                                         params={"term": keyword},
                                         referer=_HOME_URL)
            for t in ((sug.get("result") or {}).get("tag") or [])[:5]:
                v = (t.get("value") or "").strip()
                if v and v not in words:
                    words.append(v)
        except Exception:
            pass
        for w in llm.expand_keywords(keyword):  # 无 Key 时原样返回
            if w and w not in words:
                words.append(w)
        return words[:_MAX_WORDS]

    # ------------------------------------------------------------ 搜索执行
    def run_search(self, keyword: str, size: int = 90) -> dict:
        """执行一次模糊搜索，返回结果缓存（posts 全量 + 元信息）。"""
        words = self.fuzzy_expand(keyword)
        posts, errors = [], []
        for i, w in enumerate(words):
            if i == 0:
                limit = max(size // 3, 20)      # 主词：多平台深搜
                plats, srcs = _PLATFORMS, _SOURCES
            else:
                limit = max(15, size // 6)      # 扩展词：B站补充
                plats, srcs = ("bili",), ("bilibili_api",)
            got, errs, _ = orchestrator.collect(
                w, platforms=plats, limit=limit,
                source_names=srcs, save=False)
            posts.extend(got)
            errors.extend(errs)
        uniq, seen = [], set()
        for p in posts:  # 多词/多源合并去重
            key = (p.platform, p.url)
            if key not in seen:
                seen.add(key)
                uniq.append(p)
        uniq.sort(key=self._hot_score, reverse=True)  # 按热度排，先看最火的
        result = {"keyword": keyword, "expanded": words,
                  "posts": uniq, "errors": errors}
        self._cache[keyword] = result
        return result

    @staticmethod
    def _hot_score(p) -> float:
        """热度分：优先播放/点赞/评论/收藏，其次看评论数。"""
        e = p.extra or {}
        return max(float(e.get("play") or e.get("liked") or 0),
                   float(e.get("comment") or e.get("reply") or 0),
                   float(e.get("video_review") or 0))

    # ------------------------------------------------------------ 评论+总结
    def start_enrichment(self, keyword: str) -> None:
        """后台为本次搜索结果抓评论并（有 Key 时）生成 LLM 总结。"""
        posts = self._cache_posts(keyword)
        if not posts:
            return
        for p in posts:
            url = p.url
            with self._cache_lock:
                if url in self._summary_cache:
                    continue
                self._summary_cache[url] = {"comments": [], "summary": None}
            self._executor.submit(self._enrich_one, keyword, p)

    def _enrich_one(self, keyword: str, p):
        comments = self.fetch_comments(p)
        summary = None
        if llm.available():
            summary = llm.summarize_post(
                p.title, p.text, comments, platform=p.platform)
        with self._cache_lock:
            self._summary_cache[p.url] = {"comments": comments,
                                          "summary": summary}

    def fetch_comments(self, p) -> list[str]:
        """尽力而为取热评：B站评论接口游客态不可用会跳过；小红书读已抓 JSONL。"""
        if p.platform == "bilibili":
            bvid = (p.extra or {}).get("bvid")
            if not bvid:
                return []
            try:
                view = self._session.get_json(_VIEW_API,
                                              params={"bvid": bvid},
                                              referer=_HOME_URL)
                d = view.get("data") or {}
                cid, up = d.get("cid"), (d.get("owner") or {}).get("mid")
                if not cid:
                    return []
                reply = self._session.get_json(
                    _REPLY_API,
                    params={"type": 1, "oid": cid, "mode": 3, "next": 0},
                    referer=f"https://www.bilibili.com/video/{bvid}")
                reps = ((reply.get("data") or {}).get("replies")) or []
                return [(r.get("content") or {}).get("message", "").strip()
                        for r in reps[:_MAX_COMMENTS]
                        if (r.get("content") or {}).get("message")]
            except Exception:
                return []
        if p.platform == "xiaohongshu":
            return self._xhs_comments_from_jsonl(p)
        return []

    @staticmethod
    def _xhs_comments_from_jsonl(p) -> list[str]:
        """从 MediaCrawler 已抓的评论 JSONL 里读该笔记的高赞评论（尽力而为）。"""
        import json
        from pathlib import Path
        note_id = str((p.extra or {}).get("note_id") or "")
        if not note_id:
            return []
        data_dir = Path(r"D:\Projects\MediaCrawler\data\xhs\jsonl")
        if not data_dir.exists():
            return []
        hits = []
        for f in sorted(data_dir.glob("search_comments_*.jsonl"))[-2:]:
            try:
                for line in f.read_text(encoding="utf-8",
                                        errors="replace").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if str(r.get("note_id") or "") != note_id:
                        continue
                    hits.append(r)
            except OSError:
                continue
        hits.sort(key=lambda r: -_like_num(r.get("like_count")))
        return [(h.get("content") or "").strip() for h in hits[:_MAX_COMMENTS]
                if (h.get("content") or "").strip()]

    # ------------------------------------------------------------ 状态读取
    def _cache_posts(self, keyword: str) -> list:
        cache = getattr(self, "_cache", {})
        entry = cache.get(keyword) or {}
        return entry.get("posts") or []

    def summary_state(self, keyword: str) -> list[dict]:
        """返回本次搜索各结果的评论/总结状态（前端轮询）。"""
        posts = self._cache_posts(keyword)
        out = []
        with self._cache_lock:
            for p in posts:
                s = self._summary_cache.get(p.url) or {}
                out.append({"url": p.url,
                            "comments": s.get("comments") or [],
                            "summary": s.get("summary"),
                            "done": bool(s)})
        return out

    # ------------------------------------------------------------ 分析统计
    @staticmethod
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


def _like_num(value) -> int:
    """'1.4万' → 14000；解析失败返回 0。"""
    try:
        s = str(value or "").replace(",", "")
        m = re.match(r"^([\d.]+)(万)?$", s)
        if not m:
            return 0
        return int(float(m.group(1)) * 10000) if m.group(2) else int(float(m.group(1)))
    except ValueError:
        return 0
