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
from concurrent.futures import ThreadPoolExecutor, wait

from collect import analysis, comments, llm, orchestrator, settings
from collect.sources.http_client import HttpSession

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


class SearchPipeline:
    """一次搜索的生命周期管理（结果在内存，换词即弃）。

    搜索任务化：start_search 立即返回（done/running/failed），后台线程执行
    真实采集，search_progress 轮询真实进度；/api/search 仍保留同步语义，
    任务未完成时会阻塞等待同一份缓存结果。
    """

    def __init__(self):
        self._session = HttpSession()
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
    def run_search(self, keyword: str, size: int = 90,
                   on_progress=None) -> dict:
        """执行一次模糊搜索：主词多平台深搜 → 先发布主词结果（第 1 页立即可取），
        再扩词补量 → 合并去重 → 平台混合按热度排序。

        on_progress(step=..., collected=...) 每完成一个词由采集线程回调用以
        刷新进度。全部词都失败时结果标记 failed，缓存层按失败冷却期重试。
        """
        from concurrent.futures import ThreadPoolExecutor
        words = self.fuzzy_expand(keyword)
        if on_progress:
            on_progress(step=f"扩展为 {len(words)} 个词，开始并行采集…",
                        collected=0)
        main_limit = max(size // 2, settings.SEARCH_COLLECT_PER_SOURCE)
        ext_limit = max(15, main_limit // 2)     # 扩展词：B站补充
        pool = ThreadPoolExecutor(max_workers=_COLLECT_WORKERS)
        posts, errors = [], []
        # 阶段1：主词多源深搜。先取回主词 → 发布 partial（第 1 页立即可读），
        # 再补扩展词。这样前端能在搜索尚未完全结束时先显示第 1 页。
        main_future = pool.submit(
            orchestrator.collect, words[0], platforms=_PLATFORMS,
            limit=main_limit, source_names=_SOURCES, save=False)
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
        pool.shutdown(wait=True)
        return self._assemble(keyword, words, posts, errors)

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
        return result

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
        """把互动数转成可比较数字（仅用于热度排序，不合并其他计数解析器）。

        支持：int/float、含逗号字符串、'万'/'亿' 后缀；解析失败按 0 处理，
        绝不抛错中断整次搜索。
        """
        if isinstance(value, bool):
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        if not isinstance(value, str):
            return 0.0
        text = value.strip().replace(",", "")
        if not text:
            return 0.0
        multiplier = 1.0
        if text.endswith("亿"):
            multiplier, text = 100000000.0, text[:-1]
        elif text.endswith("万"):
            multiplier, text = 10000.0, text[:-1]
        try:
            return float(text) * multiplier
        except ValueError:
            return 0.0

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

        return max(pick("play", "liked", "voteup", "attitudes_count",
                        "reposts_count", "favorites", "coin",
                        "rating_count", "rating"),
                   pick("comment", "reply", "comments_count",
                        "reviews_count", "discuss"),
                   pick("video_review", "danmaku"))

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
                self.start_enrichment(keyword)
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
    def start_search(self, keyword: str, size: int = 90) -> str:
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
            self._tasks[keyword] = {"status": "running", "step": "准备搜索…",
                                    "collected": 0, "errors": [],
                                    "started": time.time()}
            self._bounded_tasks()
            try:
                future = self._executor.submit(self._run_task, keyword, size)
            except RuntimeError:   # 线程池已关闭的竞态
                self._tasks[keyword].update(status="failed", error="服务已关闭")
                return "failed"
            self._futures.add(future)
            future.add_done_callback(self._forget_future)
        return "running"

    def _run_task(self, keyword: str, size: int) -> None:
        """后台执行搜索并回写进度，结束必须写出终态。"""
        def on_progress(**updates):
            """由采集线程回调，仅刷新任务记录，不参与缓存发布。"""
            with self._cache_lock:
                task = self._tasks.get(keyword)
                if task is not None:
                    task.update(**updates)
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
        if entry is not None and self._servable(entry):
            if entry.get("partial"):
                # 主词阶段快照已就绪：第 1 页可先取，但任务仍标记在途。
                return {"task": keyword, "status": "running",
                        "step": "主词采集完成，正在补扩展词…",
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
    def start_enrichment(self, keyword: str) -> None:
        """提交增强任务；排队不代表完成，关闭后拒绝新任务。"""
        with self._cache_lock:
            if self._closed:
                raise RuntimeError("搜索服务已关闭")
        for post in self.get_posts(keyword):
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
            if not llm.available():
                status = "skipped"
            else:
                summary = llm.summarize_post(p.title, p.text, texts, platform=p.platform)
                status = "completed" if summary else "failed"
                if not summary:
                    error = "总结请求失败或未返回内容"
        except Exception:
            # 不把外部异常原文发送前端，避免其中夹带请求凭据。
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
        """兼容现有入口，委托评论模块并复用当前HTTP会话。"""
        return comments.fetch_comments(p, self._session, max_comments=_MAX_COMMENTS)

    # ------------------------------------------------------------ 状态读取
    def get_posts(self, keyword: str) -> list:
        """返回关键词对应的帖子列表副本，不暴露缓存容器。"""
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

    def search_page(self, keyword: str, page: int = 1, size: int = settings.DEFAULT_PAGE_SIZE) -> dict:
        """获取分页结果；page/size由入口校验，首次搜索才启动增强任务。"""
        cache = self._get_or_run(keyword, size * 3)
        posts = cache.get("posts") or []
        total = len(posts)
        start = (page - 1) * size
        # 返回分页快照，HTTP层只需要序列化Post，不再了解内部缓存。
        return {"keyword": keyword,
                "expanded": list(cache.get("expanded") or [keyword]),
                "posts": list(posts[start:start + size]),
                "total": total, "page": page,
                "pages": max(1, (total + size - 1) // size),
                "errors": list(cache.get("errors") or [])}

    def analysis_for(self, keyword: str) -> dict:
        """根据已搜索样本返回统计，未有样本时保留原错误提示。"""
        posts = self.get_posts(keyword)
        if not posts:
            return {"error": "请先搜索「" + keyword + "」"}
        return self.build_analysis(posts)

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
