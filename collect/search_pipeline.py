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

import threading
import time
import logging
from concurrent.futures import ThreadPoolExecutor, wait, as_completed

from collect import analysis, comments, llm, orchestrator, settings
from collect.num_utils import parse_count
from collect.sources.http_client import HttpSession
from collect.sources.bilibili_source import MAX_SEARCH_PAGES

_HOME_URL = "https://www.bilibili.com/"
_SUG_URL = "https://s.search.bilibili.com/main/suggest"
# 扩展词默认搜 B站（速度快）；主词搜全平台游客态三源。
_PLATFORMS = settings.SEARCH_PLATFORMS
_SOURCES = settings.SEARCH_SOURCES
_MAX_WORDS = settings.MAX_SEARCH_WORDS          # 模糊扩展后最多搜的词数
_MAX_COMMENTS = settings.MAX_COMMENTS       # 每条结果最多取的热评数
_MAX_WORKERS = settings.ENRICHMENT_WORKERS        # 评论/总结后台并发
_CACHE_TTL = settings.SEARCH_CACHE_TTL            # 结果缓存有效期（秒）
_CACHE_MAX_ENTRIES = settings.SEARCH_CACHE_MAX_ENTRIES  # 缓存容量上限
_FAIL_RETRY_SECS = settings.SEARCH_FAIL_RETRY_SECS      # 失败结果冷却期
_INFLIGHT_TIMEOUT = settings.SEARCH_INFLIGHT_TIMEOUT    # 等待并发搜索超时
_COLLECT_WORKERS = settings.SEARCH_COLLECT_WORKERS      # 单次搜索并行采集并发数

logger = logging.getLogger(__name__)


class SearchPipeline:
    """一次搜索的生命周期管理（结果在内存，换词即弃）。

    搜索任务化：start_search 立即返回（done/running/failed），后台线程执行
    真实采集，search_progress 轮询真实进度；/api/search 仍保留同步语义，
    任务未完成时会阻塞等待同一份缓存结果。
    """

    def __init__(self, public=False):
        """访客进程只使用免登录数据源，限制并发采集任务数。"""
        self.public = public
        source_pairs = [(source, platform) for source, platform in zip(_SOURCES, _PLATFORMS)
                        if not public or platform in ("bili", "douban", "wb")]
        self._sources, self._platforms = zip(*source_pairs)
        # 主线程保留一个默认会话，兼容既有测试与调用方的 patch 用法；
        # 后台/HTTP 工作线程改用线程本地会话，避免共享 CookieJar 产生竞态。
        self._session = HttpSession()
        self._thread_local = threading.local()
        # url -> {"comments": [...], "summary": str|None}（由后台线程填充）
        self._summary_cache: dict[str, dict] = {}
        self._cache_lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=_MAX_WORKERS)
        self._cache: dict[str, dict] = {}   # keyword -> run_search 结果
        self._inflight: dict[str, threading.Condition] = {}  # 同词并发去重
        self._tasks: dict[str, dict] = {}   # keyword -> 搜索任务进度
        self._closed = False
        self._futures = set()

    # ------------------------------------------------------------ 模糊扩展
    def _http_session(self) -> HttpSession:
        """取当前线程可用的 HTTP 会话：主线程用默认会话，其他线程各自独立。"""
        # CookieJar/urllib opener 非线程安全；后台增强线程若共享同一会话，
        # 并发请求可能交叉读写 cookie。工作线程因此持有自己的会话实例。
        if threading.current_thread() is threading.main_thread():
            return self._session
        session = getattr(self._thread_local, "session", None)
        if session is None:
            session = HttpSession()
            self._thread_local.session = session
        return session

    def fuzzy_expand(self, keyword: str) -> list[str]:
        """扩展相关搜索词：B站搜索建议（真实用户搜索）优先，LLM 补充。"""
        words = [keyword]
        session = self._http_session()
        try:
            session.get(_HOME_URL)  # 游客 cookie
            sug = session.get_json(_SUG_URL,
                                   params={"term": keyword},
                                   referer=_HOME_URL)
            for t in ((sug.get("result") or {}).get("tag") or [])[:5]:
                v = (t.get("value") or "").strip()
                if v and v not in words:
                    words.append(v)
        except Exception:
            # 搜索建议是增强手段，失败静默降级为只用 LLM/原词；原因留日志。
            logger.debug("B站搜索建议获取失败，跳过扩词来源", exc_info=True)
        for w in (() if self.public else llm.expand_keywords(keyword)):  # 无 Key 时原样返回
            if w and w not in words:
                words.append(w)
        return words[:_MAX_WORDS]

    # ------------------------------------------------------------ 搜索执行
    def run_search(self, keyword: str, size: int = 90,
                   on_progress=None) -> dict:
        """执行一次模糊搜索：主词多平台深搜 → 先发布主词结果（第 1 页立即可取），
        再扩词补量 → 合并去重 → 平台混合按热度排序。

        on_progress(step=..., collected=...) 每完成一个词由采集线程回调用以
        刷新进度。全部词都失败时结果标记 failed，缓存层按失败冷却期重试。
        """
        if getattr(on_progress, "progressive", False):
            return self._round_search(keyword, on_progress)
        words = self.fuzzy_expand(keyword)
        if on_progress:
            on_progress(step=f"扩展为 {len(words)} 个词，开始并行采集…",
                        collected=0)
        main_limit = max(size // 2, settings.SEARCH_COLLECT_PER_SOURCE)
        ext_limit = max(15, main_limit // 2)     # 扩展词：B站补充
        pool = ThreadPoolExecutor(max_workers=_COLLECT_WORKERS)
        posts, errors = [], []
        try:
            # 阶段1：主词多源深搜。先取回主词 → 发布 partial（第 1 页立即可读），
            # 再补扩展词。这样前端能在搜索尚未完全结束时先显示第 1 页。
            main_future = pool.submit(
                orchestrator.collect, words[0], platforms=self._platforms,
                limit=main_limit, source_names=self._sources, save=False)
            try:
                got, errs, _ = main_future.result()
            except Exception as exc:   # 主词整体失败不影响扩展词
                got, errs = [], [f"{words[0]}: 搜索失败 {exc}"]
            posts.extend(got)
            errors.extend(errs)
            if on_progress:
                on_progress(step=f"主词「{words[0]}」采集完成，已找到 {len(posts)} 条",
                            collected=len(posts))
            partial = self._assemble(keyword, words, posts, errors, partial=True)
            self._publish_partial(keyword, partial)
            # 阶段2：扩展词 B站补充。
            ext_futures = []
            for w in words[1:]:
                ext_futures.append((w, pool.submit(
                    orchestrator.collect, w, platforms=("bili",),
                    limit=ext_limit, source_names=("bilibili_api",),
                    save=False)))
            for i, (w, future) in enumerate(ext_futures, start=1):
                try:
                    got, errs, _ = future.result()
                except Exception as exc:
                    got, errs = [], [f"{w}: 搜索失败 {exc}"]
                posts.extend(got)
                errors.extend(errs)
                if on_progress:
                    step = (f"已完成 {i + 1}/{len(words)} 个词（扩展词「{w}」）"
                            if i + 1 < len(words) else "采集完成，正在合并去重…")
                    on_progress(step=step, collected=len(posts))
        finally:
            # 中途异常也必须关闭采集线程池，避免线程泄漏。
            pool.shutdown(wait=True)
        return self._assemble(keyword, words, posts, errors)

    def _round_search(self, keyword, progress):
        """先并行取各源首批，再按原词和建议词加深；每个来源完成即发布。"""
        sources = dict(zip(self._sources, self._platforms))
        records, errors, words = {}, [], [keyword]
        def collect_round(pool, word, limit, number):
            progress(step=f"第 {number} 轮 · {word}", collected=len(records))
            futures = {pool.submit(orchestrator.collect, word, platforms=(platform,),
                                   limit=limit, source_names=(name,), save=False): name
                       for name, platform in sources.items()}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    batch, issues, _ = future.result()
                except Exception:
                    batch, issues = [], [f"{name} 搜索失败"]
                if issues:
                    errors.extend(issues)
                    sources.pop(name, None)
                for post in batch:
                    records.setdefault((post.platform, post.url), post)
                snapshot = self._assemble(keyword, words.copy(), list(records.values()), errors.copy(), partial=True)
                snapshot["step"] = f"第 {number} 轮 · {word}"
                # 首轮只发布社交帖子，避免最先返回的书影音条目占据首屏。
                if number == 1:
                    snapshot["posts"] = [p for p in snapshot["posts"]
                                         if p.record_type != "catalog_item"]
                self._publish_partial(keyword, snapshot)
                progress(step=snapshot["step"], collected=len(records))
        with ThreadPoolExecutor(max_workers=len(sources)) as pool:
            collect_round(pool, keyword, 6, 1)
            if sources and not self._closed:
                collect_round(pool, keyword, 220, 2)
            if sources and len(records) < 1000 and not self._closed:
                for number, word in enumerate(self.fuzzy_expand(keyword)[1:], 3):
                    if not sources or len(records) >= 1000 or self._closed:
                        break
                    words.append(word)
                    collect_round(pool, word, settings.SEARCH_COLLECT_PER_SOURCE, number)
        result = self._assemble(keyword, words, list(records.values()), errors)
        result["progressive"] = True
        return result

    def _assemble(self, keyword: str, words: list, posts: list,
                  errors: list, partial: bool = False) -> dict:
        """合并去重 → 平台混合热度排序 → 组装搜索结果字典。

        partial=True 表示主词阶段快照（前端可先取第 1 页，任务仍标记在途）。
        """
        uniq, seen = [], set()
        for p in posts:  # 多词/多源合并去重
            key = (p.platform, p.url)
            if key not in seen:
                seen.add(key)
                uniq.append(p)
        ordered = self._balanced_order(uniq)
        result = {"keyword": keyword, "expanded": words,
                  "posts": ordered, "errors": errors}
        if partial:
            result["partial"] = True
        if not ordered and errors:
            result["failed"] = True   # 全部词失败 → 按失败冷却期重试
        return result

    def _publish_partial(self, keyword: str, result: dict) -> None:
        """发布主词阶段结果：搜索完成前先让第 1 页可读。

        最终结果由 _get_or_run 在 run_search 返回后覆盖并通知等待者。
        """
        with self._cache_lock:
            if self._closed:
                return
            result.setdefault("created", time.time())
            self._cache[keyword] = result
            self._bounded_evict()
            condition = self._inflight.get(keyword)
            if condition is not None:
                condition.notify_all()

    @staticmethod
    def _balanced_order(posts, page_size: int | None = None):
        """平台混合排序：各平台内部按热度降序，再按页均分轮转。

        每个平台把帖子均匀摊到总页数上（越靠前的页放越热的内容），再逐页
        轮转，因此稀缺平台（如微博只有几条）也能铺到尽量多的页，而每一页
        都会同时出现各平台内容且各平台内部越靠前越热；单平台时等价于按
        热度降序。
        """
        if not posts:
            return []
        page_size = page_size or settings.DEFAULT_PAGE_SIZE
        # 混合分页优先保留给社交帖子；书影音条目随后按自身热度排列。
        catalog = [p for p in posts if p.record_type == "catalog_item"]
        posts = [p for p in posts if p.record_type != "catalog_item"]
        if not posts:
            return sorted(catalog, key=SearchPipeline._hot_score, reverse=True)
        groups: dict[str, list] = {}
        for p in posts:
            groups.setdefault(p.platform, []).append(p)
        for lst in groups.values():
            lst.sort(key=SearchPipeline._hot_score, reverse=True)
        pages = max(1, -(-len(posts) // page_size))
        # 规范平台顺序，让同热度下各平台稳定轮转。
        order = [pl for pl in ("bilibili", "xiaohongshu", "zhihu",
                               "weibo", "douban", "douyin", "kuaishou",
                               "tieba") if pl in groups]
        order += [pl for pl in groups if pl not in order]
        chunks = {pl: SearchPipeline._chunk_pages(lst, pages)
                  for pl, lst in groups.items()}
        result = []
        for pi in range(pages):
            # 页内：把各平台分给本页的分块轮转交错，让这一页多平台共存。
            slots = [(pl, chunks[pl][pi]) for pl in order
                     if pl in chunks and chunks[pl][pi]]
            while slots:
                keep = []
                for pl, slot in slots:
                    result.append(slot.pop(0))
                    if slot:
                        keep.append((pl, slot))
                slots = keep
        return result + sorted(catalog, key=SearchPipeline._hot_score, reverse=True)

    @staticmethod
    def _chunk_pages(lst, pages):
        """把有序列表尽量均匀地切成 pages 段（前段先放更热的内容）。"""
        out = [[] for _ in range(pages)]
        size = -(-len(lst) // pages)   # 每页均分量（向上取整）
        for i, item in enumerate(lst):
            out[min(pages - 1, i // size)].append(item)
        return out

    @staticmethod
    def _count(value) -> float:
        """把互动数转成可比较数字（仅用于热度排序）。

        实现统一在 collect.num_utils.parse_count；解析失败按 0 处理，
        绝不抛错中断整次搜索。
        """
        return parse_count(value)

    @staticmethod
    def _hot_score(p) -> float:
        """热度分：取播放/点赞、评论/回复、视频评论三类中最大的可解析值。"""
        e = p.extra or {}

        def pick(*keys):
            """取第一组里第一个能解析为正数的指标。"""
            for key in keys:
                if e.get(key) is None:
                    continue
                value = SearchPipeline._count(e[key])
                if value > 0:
                    return value
            return 0.0

        return (pick("liked", "voteup", "attitudes_count", "favorites", "rating_count")
                + 2 * pick("comment", "reply", "comments_count", "reviews_count", "discuss")
                + 3 * pick("reposts_count", "share") + pick("video_review", "danmaku")
                + 0.01 * pick("play"))

    # ------------------------------------------------------------ 缓存与并发
    def _servable(self, entry) -> bool:
        """缓存条目是否可直接使用：新鲜成功结果，或失败冷却期内的失败结果。"""
        age = time.time() - entry.get("created", 0)
        if entry.get("failed"):
            return age < _FAIL_RETRY_SECS
        return age < _CACHE_TTL

    def _bounded_evict(self):
        """缓存容量有界：超过上限时淘汰最早写入的词条。"""
        while len(self._cache) > _CACHE_MAX_ENTRIES:
            oldest = min(self._cache,
                         key=lambda k: self._cache[k].get("created", 0))
            self._cache.pop(oldest, None)

    def _get_or_run(self, keyword: str, size: int, on_progress=None) -> dict:
        """同词并发只执行一次真实搜索：首个线程执行，其余线程等待复用结果。

        失败结果也会发布给等待者（避免永久卡住），冷却期后再访问自动重试；
        成功结果带 TTL，过期后再次访问自动重搜；缓存条目数有上限。
        on_progress 转发给 run_search 用于刷新任务进度。
        """
        with self._cache_lock:
            entry = self._cache.get(keyword)
            if entry is not None and self._servable(entry):
                return entry
            runner = keyword not in self._inflight
            if runner:
                # 我是第一个到达的线程 → 成为执行者，登记条件变量供等待者。
                self._inflight[keyword] = threading.Condition(self._cache_lock)
        if runner:
            try:
                result = self.run_search(keyword, size=size,
                                         on_progress=on_progress)
            except Exception as exc:
                # 失败也要发布，否则等待者永久卡死；冷却期后会自动重试。
                result = {"keyword": keyword, "expanded": [keyword],
                          "posts": [], "errors": ["搜索失败，请稍后重试"],
                          "failed": True}
            with self._cache_lock:
                result.setdefault("created", time.time())
                result.setdefault("failed", False)
                self._cache[keyword] = result
                self._bounded_evict()
                condition = self._inflight.pop(keyword, None)
                if condition is not None:
                    condition.notify_all()
            # 增强任务必须在最终结果进入缓存后启动：start_enrichment 会读取
            # get_posts(keyword)，若提前调用，扩展词帖子将拿不到评论/总结状态。
            try:
                if not self.public and not result.get("progressive"):
                    self.start_enrichment(keyword)
            except RuntimeError:
                # 服务关闭时拒绝新增强任务，不影响已发布搜索结果。
                pass
            return result
        # 等待者：等待执行者发布结果。
        with self._cache_lock:
            condition = self._inflight.get(keyword)
        if condition is not None:
            with condition:
                while True:
                    entry = self._cache.get(keyword)
                    if entry is not None and self._servable(entry):
                        return entry
                    if not condition.wait(timeout=_INFLIGHT_TIMEOUT):
                        break  # 防御：避免执行者异常时永久等待
        # 兜底：超时仍未拿到结果，以执行者身份再试一次。
        return self._get_or_run(keyword, size)

    # ------------------------------------------------------------ 任务与进度
    def start_search(self, keyword: str, size: int = 90, progressive=False) -> str:
        """启动（或复用）一次搜索任务，立即返回状态；进度经 search_progress 轮询。

        done    结果已就绪（缓存新鲜可用），可直接取分页；
        running 任务在途（首个请求启动后台执行，其余请求复用同一任务）；
        failed  服务已关闭或任务提交失败。
        """
        with self._cache_lock:
            entry = self._cache.get(keyword)
            # 主词阶段快照（partial）不算完成：任务仍在补扩展词。
            if (entry is not None and self._servable(entry)
                    and not entry.get("partial")):
                return "done"
            task = self._tasks.get(keyword)
            if task is not None and task.get("status") == "running":
                return "running"
            if self._closed:
                return "failed"
            # 多访客请求共享同一进程，拒绝堆积过多新采集。
            if self.public and sum(t.get("status") == "running" for t in self._tasks.values()) >= 2:
                return "busy"
            self._tasks[keyword] = {"status": "running", "step": "准备搜索…",
                                    "collected": 0, "errors": [],
                                    "started": time.time()}
            self._bounded_tasks()
            try:
                future = self._executor.submit(self._run_task, keyword, size, progressive)
            except RuntimeError:   # 线程池已关闭的竞态
                self._tasks[keyword].update(status="failed", error="服务已关闭")
                return "failed"
            self._futures.add(future)
            future.add_done_callback(self._forget_future)
        return "running"

    def continue_search(self, keyword: str, related_word: str = "") -> str:
        """从已有结果启动补搜，即使结果超过普通搜索的缓存时限。"""
        with self._cache_lock:
            if self._closed:
                return "failed"
            task = self._tasks.get(keyword, {})
            if task.get("status") == "running" or keyword in self._inflight:
                return "running"
            entry = self._cache.get(keyword)
            if entry is None:
                return "idle"
            # 延长当前快照的有效期，让等待补搜时仍可浏览旧结果。
            entry["created"] = time.time()
            # 多访客请求共享同一进程，拒绝堆积过多新采集。
            if self.public and sum(t.get("status") == "running" for t in self._tasks.values()) >= 2:
                return "busy"
            self._tasks[keyword] = {
                "status": "running", "continuation": True, "step": "正在寻找更多内容…",
                "started": time.time(), "collected": len(entry["posts"]),
            }
            self._bounded_tasks()
            try:
                future = self._executor.submit(self._continue_task, keyword, related_word, entry)
            except RuntimeError:
                self._tasks[keyword].update(status="failed", error="服务已关闭")
                return "failed"
            self._futures.add(future)
            future.add_done_callback(self._forget_future)
            return "running"

    def _continue_task(self, keyword, related_word, entry):
        """扫描下一段公开页或补查相关词，按平台和链接合并。"""
        previous = entry["posts"]
        words = list(entry.get("expanded") or [keyword])
        next_page = entry.get("bili_next_page", 1)
        extra_posts, errors = [], []
        try:
            if not related_word and next_page <= MAX_SEARCH_PAGES:
                batch, issues, _ = orchestrator.collect(
                    keyword, platforms=("bili",), source_names=("bilibili_api",),
                    limit=400, save=False,
                    source_kwargs={"bilibili_api": {"start_page": next_page, "page_window": 8}},
                )
                extra_posts.extend(batch)
                errors.extend(issues)
                if not issues:
                    next_page = next_page + 8 if batch else MAX_SEARCH_PAGES + 1

            # 有新建议时才扩词。平台拒绝返回原词结果时保留游标，等下一次手动重试。
            if not related_word and not errors and not self._closed:
                searched = {word.casefold() for word in words}
                related_word = next((word for word in self.fuzzy_expand(keyword)
                                     if word.casefold() not in searched), "")
            if related_word and not self._closed:
                batch, issues, _ = orchestrator.collect(
                    related_word, platforms=self._platforms, source_names=self._sources,
                    limit=settings.SEARCH_COLLECT_PER_SOURCE, save=False,
                )
                extra_posts.extend(batch)
                errors.extend(issues)
                if related_word not in words:
                    words.append(related_word)
        except Exception:
            logger.exception("继续搜索失败")
            errors.append("继续搜索暂不可用")

        result = self._assemble(keyword, words, [*previous, *extra_posts], errors)
        count = len(result["posts"])
        added = count - len(previous)
        if added:
            message = f"本次新增 {added} 条，累计 {count} 条。"
        elif errors:
            message = "本次没有新增，部分来源暂不可用。可以稍后重试或换个补搜词。"
        elif next_page > MAX_SEARCH_PAGES:
            message = "没有发现新结果。可以输入其他相关词继续补搜。"
        else:
            message = "这批结果与已有内容重复。可以继续查下一批，或输入相关词。"

        with self._cache_lock:
            if self._closed:
                return
            result.update(progressive=True, created=time.time(), bili_next_page=next_page)
            self._cache[keyword] = result
            self._bounded_evict()
            self._tasks[keyword].update(status="done", total=count, added=added, message=message)

    def _run_task(self, keyword: str, size: int, progressive=False) -> None:
        """后台执行搜索并回写进度，结束必须写出终态。"""
        def on_progress(**updates):
            """由采集线程回调，仅刷新任务记录，不参与缓存发布。"""
            with self._cache_lock:
                task = self._tasks.get(keyword)
                if task is not None:
                    task.update(**updates)
        on_progress.progressive = progressive
        try:
            result = self._get_or_run(keyword, size, on_progress=on_progress)
        except Exception as exc:
            with self._cache_lock:
                task = self._tasks.get(keyword)
                if task is not None:
                    task.update(status="failed", error=f"搜索失败：{exc}")
            return
        with self._cache_lock:
            task = self._tasks.get(keyword)
            if task is not None:
                task.update(status="done",
                            total=len(result.get("posts") or []),
                            step="完成")

    def search_progress(self, keyword: str) -> dict:
        """返回搜索任务进度；结果就绪时直接报告完成（失败结果按冷却期复用）。"""
        with self._cache_lock:
            entry = self._cache.get(keyword)
            task = self._tasks.get(keyword)
        if task and task.get("continuation"):
            return {"task": keyword, **task}
        if entry is not None and self._servable(entry):
            if entry.get("partial"):
                # 主词阶段快照已就绪：第 1 页可先取，但任务仍标记在途。
                return {"task": keyword, "status": "running",
                        "step": (task or {}).get("step") or entry.get("step", "继续搜索…"),
                        "collected": len(entry.get("posts") or []),
                        "errors": entry.get("errors") or []}
            return {"task": keyword, "status": "done",
                    "total": len(entry.get("posts") or [])}
        if task is not None:
            return {"task": keyword, "status": task.get("status"),
                    "step": task.get("step"),
                    "collected": task.get("collected", 0),
                    "errors": task.get("errors") or [],
                    "error": task.get("error")}
        return {"task": keyword, "status": "idle", "step": "任务未开始",
                "collected": 0, "errors": []}

    def _bounded_tasks(self):
        """任务记录有界：超过上限时移除最早开始且已结束的任务记录。"""
        while len(self._tasks) > _CACHE_MAX_ENTRIES:
            finished = [k for k, t in self._tasks.items()
                        if t.get("status") != "running"]
            if not finished:
                break
            oldest = min(finished,
                         key=lambda k: self._tasks[k].get("started", 0))
            self._tasks.pop(oldest, None)

    # ------------------------------------------------------------ 评论+总结
    def start_enrichment(self, keyword: str, posts=None) -> None:
        """提交增强任务；排队不代表完成，关闭后拒绝新任务。"""
        with self._cache_lock:
            if self._closed:
                raise RuntimeError("搜索服务已关闭")
        for post in (self.get_posts(keyword) if posts is None else posts):
            with self._cache_lock:
                if self._closed:
                    raise RuntimeError("搜索服务已关闭")
                if post.url in self._summary_cache:
                    continue
                self._summary_cache[post.url] = {
                    "comments": [], "summary": None, "status": "queued", "error": None}
                # 提交与关闭共用锁，避免关闭线程池后仍插入排队状态。
                try:
                    future = self._executor.submit(self._enrich_one, keyword, post)
                except RuntimeError:
                    self._summary_cache[post.url].update(status="failed", error="任务提交失败")
                    continue
                self._futures.add(future)
            future.add_done_callback(self._forget_future)

    def _forget_future(self, future) -> None:
        """释放已完成任务引用，不保留多余Future对象。"""
        with self._cache_lock:
            self._futures.discard(future)

    def _enrich_one(self, keyword: str, p):
        """执行评论与总结；正常、无配置、异常均写入明确终态。"""
        with self._cache_lock:
            if self._closed:
                return
            self._summary_cache[p.url] = {
                "comments": [], "summary": None, "status": "running", "error": None}
        texts, summary, error = [], None, None
        try:
            texts = self.fetch_comments(p)
            with self._cache_lock:
                if self._closed:
                    return
            if not settings.ENABLE_AI_SUMMARY or not llm.available():
                status = "skipped"
            else:
                summary = llm.summarize_post(p.title, p.text, texts, platform=p.platform)
                status = "completed" if summary else "failed"
                if not summary:
                    error = "总结请求失败或未返回内容"
        except Exception:
            # 不把外部异常原文发送前端，避免其中夹带请求凭据；细节进日志。
            logger.debug("评论/总结任务执行失败（url=%s）", p.url, exc_info=True)
            status, error = "failed", "评论或总结任务执行失败"
        with self._cache_lock:
            if not self._closed:
                self._summary_cache[p.url] = {
                    "comments": texts, "summary": summary, "status": status, "error": error}

    def close(self, timeout: float = 2.0) -> bool:
        """停止接收任务并取消排队项；最多等待timeout秒，返回是否全部结束。"""
        with self._cache_lock:
            self._closed = True
            futures = set(self._futures)
            for state in self._summary_cache.values():
                if state.get("status") in ("queued", "running"):
                    state.update(status="cancelled", error="服务已关闭")
            for task in self._tasks.values():
                if task.get("status") == "running":
                    task.update(status="failed", error="服务已关闭")
        # 回调需要获取锁，不能在持锁期间取消Future。
        self._executor.shutdown(wait=False, cancel_futures=True)
        if not futures:
            return True
        _, pending = wait(futures, timeout=max(0, timeout))
        return not pending

    def fetch_comments(self, p) -> list[str]:
        """兼容现有入口，委托评论模块并复用当前线程的HTTP会话。"""
        return comments.fetch_comments(p, self._http_session(), max_comments=_MAX_COMMENTS)

    # ------------------------------------------------------------ 状态读取
    def get_posts(self, keyword: str) -> list:
        """返回关键词对应的帖子列表副本，不暴露缓存容器。"""
        with self._cache_lock:
            entry = self._cache.get(keyword) or {}
        return list(entry.get("posts") or [])

    def result_details(self, url: str) -> dict:
        """读取单条结果的总结与前三条评论，返回独立字典和列表。"""
        with self._cache_lock:
            state = self._summary_cache.get(url) or {}
            return {"summary": state.get("summary"),
                    "comments": list(state.get("comments") or [])[:3],
                    "summary_status": state.get("status", "idle"),
                    "summary_error": state.get("error")}

    def search_page(self, keyword: str, page: int = 1, size: int = settings.DEFAULT_PAGE_SIZE, platforms=None, snapshot=False) -> dict:
        """获取分页结果；page/size由入口校验，首次搜索才启动增强任务。"""
        if snapshot:
            # 翻页时仅取快照，避免缓存过期后意外覆盖本次累积的搜索结果。
            with self._cache_lock:
                cache = self._cache.get(keyword) or {}
        else:
            cache = self._get_or_run(keyword, size * 3)
        posts = cache.get("posts") or []
        if platforms is not None:
            posts = self._balanced_order([p for p in posts if p.platform in platforms], size)
        total = len(posts)
        start = (page - 1) * size
        if not self.public and (cache.get("progressive") or cache.get("step")):
            self.start_enrichment(keyword, posts[start:start + size])
        # 返回分页快照，HTTP层只需要序列化Post，不再了解内部缓存。
        return {"keyword": keyword,
                "expanded": list(cache.get("expanded") or [keyword]),
                "posts": list(posts[start:start + size]),
                "total": total, "page": page,
                "pages": max(1, (total + size - 1) // size),
                "errors": list(cache.get("errors") or [])}

    def analysis_for(self, keyword: str, with_text=False) -> dict:
        """根据已搜索样本返回统计，未有样本时保留原错误提示。"""
        posts = list(analysis.combined_posts(self.get_posts(keyword), keyword,
                                             include_catalog=with_text, include_archive=not self.public))
        if not posts:
            return {"error": "请先搜索「" + keyword + "」"}
        result = analysis.build_analysis([p for p in posts if p.record_type == "post"], keyword)
        if with_text:
            # 条目简介仅作文本资料，不能把上映日期计为发帖时间。
            result["documents"] = [{"platform": p.platform, "text": " ".join(dict.fromkeys(
                filter(None, (p.title, p.text))))} for p in posts]
        return result

    def summary_state(self, keyword: str) -> list[dict]:
        """返回本次搜索各结果的评论/总结状态（前端轮询）。"""
        posts = self.get_posts(keyword)
        out = []
        with self._cache_lock:
            for p in posts:
                s = self._summary_cache.get(p.url) or {}
                out.append({"url": p.url,
                            "comments": s.get("comments") or [],
                            "summary": s.get("summary"),
                            "done": s.get("status") in ("completed", "skipped", "failed", "cancelled"),
                            "status": s.get("status", "idle"),
                            "error": s.get("error")})
        return out

    # ------------------------------------------------------------ 分析统计
    @staticmethod
    def build_analysis(posts) -> dict:
        """兼容旧统计入口，计算委托给analysis纯函数。"""
        return analysis.build_analysis(posts)
