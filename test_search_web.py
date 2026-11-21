"""搜索公开行为与HTTP契约回归：假来源、假模型，不访问平台或真实账号。"""
import json
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import Mock, patch

from collect.post import Post
from collect.search_pipeline import SearchPipeline
from collect.web_app import Handler


def sample(index, **changes):
    """构造虚构帖子，链接和指标稳定，便于比较分页与统计。"""
    fields = dict(platform="bilibili", title="meme", text="meme", url=f"https://example.invalid/{index}", author="tester", published_at="2026-11-01 10:00:00", source_adapter="fake", keyword="topic", extra={"play": index})
    fields.update(changes)
    return Post(**fields)


class QuietHandler(Handler):
    """测试时关闭HTTP访问日志。"""
    def log_message(self, format, *args):
        """保持断言输出清晰。"""
        pass


class SearchHttpTests(unittest.TestCase):
    """通过真实本地HTTP核对响应，不读取业务模块的私有缓存。"""
    def setUp(self):
        """隔离来源、扩词、模型及后台增强，启动随机端口服务。"""
        self.pipe = SearchPipeline()
        self.addCleanup(self.pipe._executor.shutdown, wait=True)
        self.collect = self.enterContext(patch("collect.search_pipeline.orchestrator.collect", return_value=([sample(i) for i in range(24)], [], {})))
        self.enterContext(patch.object(self.pipe, "fuzzy_expand", side_effect=lambda word: [word]))
        self.enterContext(patch.object(self.pipe, "start_enrichment"))
        self.enterContext(patch("collect.search_pipeline.llm.available", return_value=False))
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        self.server.pipeline = self.pipe
        self.server.account_manager = Mock()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        """关闭本测试拥有的HTTP服务。"""
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def request(self, path, payload=None):
        """发送本机JSON请求，返回状态码及对象；错误响应也回传便于断言。"""
        data = None if payload is None else json.dumps(payload).encode()
        req = urllib.request.Request(f"http://127.0.0.1:{self.server.server_port}" + path, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as exc:
            raw = exc.read() or b"{}"
            try:
                return exc.code, json.loads(raw.decode("utf-8"))
            except ValueError:
                return exc.code, {"error": raw.decode("utf-8", "replace")}

    def test_search_pagination_cache_and_shape(self):
        """翻页复用同一搜索，保留数量、顺序、响应字段和错误列表。"""
        status, first = self.request("/api/search", {"keyword": "topic", "size": 10})
        self.assertEqual(status, 200)
        self.assertEqual(set(first), {"keyword", "expanded", "rows", "total", "page", "pages", "errors"})
        self.assertEqual((first["total"], first["pages"], first["page"]), (24, 3, 1))
        self.assertEqual([r["url"] for r in first["rows"]], [f"https://example.invalid/{i}" for i in range(23, 13, -1)])
        row = first["rows"][0]
        self.assertEqual(set(row), {"platform", "title", "text", "url", "author", "published_at", "source_adapter", "keyword", "extra", "record_type", "keywords", "fetched_at", "summary", "comments", "summary_status", "summary_error"})
        self.assertIsNone(row["summary"])
        _, last = self.request("/api/search", {"keyword": "topic", "page": 3, "size": 10})
        self.assertEqual(len(last["rows"]), 4)
        _, beyond = self.request("/api/search", {"keyword": "topic", "page": 4, "size": 10})
        self.assertEqual(beyond["rows"], [])
        self.assertEqual(self.collect.call_count, 1)
        self.assertFalse(self.collect.call_args.kwargs["save"])

    def test_empty_and_partial_failure(self):
        """空结果和部分源错误按原响应返回，空缓存仍能复用。"""
        self.collect.return_value = ([], ["weibo unavailable"], {})
        _, data = self.request("/api/search", {"keyword": "topic"})
        self.assertEqual((data["total"], data["pages"], data["rows"]), (0, 1, []))
        self.assertEqual(data["errors"], ["weibo unavailable"])
        self.request("/api/search", {"keyword": "topic"})
        self.assertEqual(self.collect.call_count, 1)

    def test_continue_keeps_results_and_advances_pages(self):
        """进行中的补搜可继续翻页，连续两次补搜前进并去重。"""
        request_path = "/api/search/continue"
        payload = {"keyword": "topic"}
        self.assertEqual(self.request(request_path, payload)[0], 409)
        self.request("/api/search", payload)
        started, release = threading.Event(), threading.Event()
        offsets = []

        def collect_more(word, **options):
            """每个模拟页返回一条旧记录和一条新的记录。"""
            offset = options["source_kwargs"]["bilibili_api"]["start_page"]
            offsets.append(offset)
            started.set()
            release.wait(3)
            return [sample(0), sample(100 + offset)], [], {}

        def wait_done():
            """等待后台任务终态，避免睡眠猜测线程执行速度。"""
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                _, state = self.request("/api/search/progress?task=topic")
                if state["status"] == "done":
                    return state
                time.sleep(.01)
            self.fail("补搜未按期完成")

        self.collect.side_effect = collect_more
        try:
            _, state = self.request(request_path, payload)
            self.assertEqual(state["status"], "running")
            self.assertTrue(started.wait(2))
            _, before = self.request("/api/search", {**payload, "snapshot": True, "page": 2})
            self.assertEqual((before["total"], before["page"]), (24, 2))
            self.request(request_path, payload)
        finally:
            release.set()
        self.assertEqual(wait_done()["added"], 1)
        self.request(request_path, payload)
        self.assertEqual(wait_done()["added"], 1)
        self.assertEqual(offsets, [1, 9])
        _, after = self.request("/api/search", {**payload, "snapshot": True})
        self.assertEqual(after["total"], 26)

        self.collect.side_effect = None
        self.collect.return_value = ([sample(0)], [], {})
        self.request(request_path, {**payload, "related_word": "补充关键词"})
        result = wait_done()
        self.assertEqual((result["added"], result["total"]), (0, 26))
        self.assertEqual(self.collect.call_args.args[0], "补充关键词")
        self.assertIn("重复", result["message"])

    def test_blank_keyword(self):
        """空关键词返回 400，不触发任何来源调用。"""
        status, data = self.request("/api/search", {"keyword": "  "})
        self.assertEqual(status, 400)
        self.assertEqual(data, {"error": "关键词不能为空"})
        self.collect.assert_not_called()

    def test_analysis_empty_and_fixed_counts(self):
        """未搜索提示和固定样本的日期、平台、作者计数保持一致。"""
        _, empty = self.request("/api/analysis?keyword=topic")
        self.assertEqual(empty, {"error": "请先搜索「topic」"})
        self.collect.return_value = ([sample(0), sample(1), sample(2, platform="weibo", author="", published_at="")], [], {})
        self.request("/api/search", {"keyword": "topic"})
        _, result = self.request("/api/analysis?keyword=topic")
        self.assertEqual(result, {"timeline": [["2026-11-01", 2]], "total": 3, "dated": 2, "tagged": 0, "topics": []})

    def test_completed_summary_and_comments(self):
        """模拟完成的增强任务，通过HTTP读取评论与空总结。"""
        post = sample(0)
        self.collect.return_value = ([post], [], {})
        self.request("/api/search", {"keyword": "topic"})
        with patch.object(self.pipe, "fetch_comments", return_value=["comment"]):
            self.pipe._enrich_one("topic", post)
        _, data = self.request("/api/summaries?keyword=topic")
        self.assertEqual(data, {"states": [{"url": post.url, "comments": ["comment"], "summary": None, "done": True, "status": "skipped", "error": None}]})
        _, search = self.request("/api/search", {"keyword": "topic"})
        self.assertEqual(search["rows"][0]["comments"], ["comment"])

    def test_account_routes_remain_forwarded(self):
        """账号接口只调用假管理器，不启动登录或删除档案。"""
        manager = self.server.account_manager
        manager.accounts.return_value = [{"platform": "xhs", "state": "pending"}]
        _, response = self.request("/api/accounts")
        self.assertEqual(response, {"accounts": manager.accounts.return_value})
        manager.cancel_login.return_value = {"ok": True, "platform": "xhs"}
        _, response = self.request("/api/login/cancel", {"platform": "xhs"})
        self.assertEqual(response, manager.cancel_login.return_value)
        manager.cancel_login.assert_called_once_with("xhs")

    # ------------------------------------------------------ 输入输出边界（阶段2）
    def test_non_object_body_rejected(self):
        """数组/数字/字符串等非对象请求体必须得到 400，不能静默成功。"""
        for bad in ([1, 2], 42, "text"):
            with self.subTest(bad=bad):
                status, body = self.request("/api/search", bad)
                self.assertEqual(status, 400)
                self.assertIn("error", body)

    def test_null_body_rejected(self):
        """null 请求体（json.loads 得 None）必须得到 400。"""
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.server.server_port}/api/search",
            data=b"null", headers={"Content-Type": "application/json"},
            method="POST")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 400)

    def test_invalid_page_and_size_rejected(self):
        """page/size 类型或范围非法必须得到 400，不统一回退成成功。"""
        for payload in ({"keyword": "topic", "page": "two"},
                        {"keyword": "topic", "page": 0},
                        {"keyword": "topic", "page": True},
                        {"keyword": "topic", "size": 5},
                        {"keyword": "topic", "size": 200}):
            with self.subTest(payload=payload):
                status, _ = self.request("/api/search", payload)
                self.assertEqual(status, 400)

    def test_long_or_non_string_keyword_rejected(self):
        """超长或非字符串关键词必须得到 400。"""
        status, _ = self.request("/api/search", {"keyword": "x" * 200})
        self.assertEqual(status, 400)
        status, _ = self.request("/api/search", {"keyword": 123})
        self.assertEqual(status, 400)

    def test_non_string_platform_rejected(self):
        """非字符串平台参数必须得到 400，不进入账号操作。"""
        status, _ = self.request("/api/login/cancel", {"platform": 123})
        self.assertEqual(status, 400)

    # ------------------------------------------------------ 重复任务与缓存（阶段4）
    def test_concurrent_same_keyword_collects_once(self):
        """两个线程同时搜索同一未缓存词，只执行一次真实采集。"""
        entered, release = threading.Event(), threading.Event()

        def slow_collect(*args, **kwargs):
            """模拟正在进行的慢搜索，制造并发窗口。"""
            entered.set()
            release.wait(3)
            return ([sample(i) for i in range(6)], [], {})
        results, errors = [], []
        saved = self.collect.side_effect
        self.collect.side_effect = slow_collect
        try:
            def worker():
                try:
                    _, d = self.request("/api/search", {"keyword": "dup"})
                    results.append(d)
                except Exception as exc:
                    errors.append(exc)
            threads = [threading.Thread(target=worker) for _ in range(2)]
            for t in threads:
                t.start()
            self.assertTrue(entered.wait(2), "第一次采集应开始并阻塞")
            time.sleep(0.2)   # 让第二个请求进入等待队列
            release.set()
            for t in threads:
                t.join(timeout=5)
        finally:
            self.collect.side_effect = saved
        self.assertFalse(errors)
        self.assertEqual([r["total"] for r in results], [6, 6])
        self.assertEqual(self.collect.call_count, 1)

    def test_cache_expires_and_refetches(self):
        """结果缓存超过 TTL 后再次访问自动重新采集。"""
        import collect.search_pipeline as sp
        with patch.object(sp, "_CACHE_TTL", 0.05):
            self.request("/api/search", {"keyword": "topic"})
            self.assertEqual(self.collect.call_count, 1)
            time.sleep(0.1)
            self.request("/api/search", {"keyword": "topic"})
        self.assertEqual(self.collect.call_count, 2)

    def test_failed_search_cooldown_then_retry(self):
        """搜索失败给等待者返回失败；冷却期内复用，冷却后再次访问重试。"""
        import collect.search_pipeline as sp

        def flaky(*args, **kwargs):
            """模拟来源全部失败。"""
            raise RuntimeError("source down")
        saved = self.collect.side_effect
        self.collect.side_effect = flaky
        try:
            _, first = self.request("/api/search", {"keyword": "topic"})
        finally:
            self.collect.side_effect = saved
        self.assertEqual(first["total"], 0)
        self.assertTrue(any("搜索失败" in e for e in first["errors"]))
        self.assertEqual(self.collect.call_count, 1)
        # 冷却期内复用失败结果，不立刻重复打拍。
        with patch.object(sp, "_FAIL_RETRY_SECS", 10):
            self.request("/api/search", {"keyword": "topic"})
            self.assertEqual(self.collect.call_count, 1)
        # 冷却期过后重试成功。
        def ok(*args, **kwargs):
            return ([sample(i) for i in range(3)], [], {})
        self.collect.side_effect = ok
        try:
            with patch.object(sp, "_FAIL_RETRY_SECS", -1):
                _, retry = self.request("/api/search", {"keyword": "topic"})
        finally:
            self.collect.side_effect = saved
        self.assertEqual(self.collect.call_count, 2)
        self.assertEqual(retry["total"], 3)

    def test_cache_capacity_bounded(self):
        """缓存条目数有上限，超过后淘汰最早写入的词条。"""
        import collect.search_pipeline as sp
        with patch.object(sp, "_CACHE_MAX_ENTRIES", 2):
            for index in range(5):
                self.request("/api/search", {"keyword": f"kw{index}"})
        self.assertLessEqual(len(self.pipe._cache), 2)

    # ------------------------------------------------------ 任务化搜索与进度（阶段5）
    def test_search_start_progress_then_result(self):
        """start 在途 → 轮询真实进度 → done 后取分页结果。"""
        entered, release = threading.Event(), threading.Event()

        def slow_collect(*args, **kwargs):
            entered.set()
            release.wait(3)
            return ([sample(i) for i in range(4)], [], {})
        saved = self.collect.side_effect
        self.collect.side_effect = slow_collect
        try:
            status, started = self.request("/api/search/start", {"keyword": "prog"})
            self.assertEqual((status, started["status"]), (200, "running"))
            self.assertTrue(entered.wait(2), "后台采集应开始并阻塞")
            _, progress = self.request("/api/search/progress?task=prog")
            self.assertEqual(progress["status"], "running")
            self.assertIn("step", progress)
            release.set()
            for _ in range(60):
                _, progress = self.request("/api/search/progress?task=prog")
                if progress["status"] == "done":
                    break
                time.sleep(0.05)
            self.assertEqual(progress["status"], "done")
        finally:
            self.collect.side_effect = saved
            release.set()
        _, result = self.request("/api/search", {"keyword": "prog", "page": 1})
        self.assertEqual(result["total"], 4)

    def test_search_start_cached_returns_done(self):
        """已搜索过的词再次启动任务直接返回 done，不重复采集。"""
        self.request("/api/search", {"keyword": "topic"})
        status, started = self.request("/api/search/start", {"keyword": "topic"})
        self.assertEqual(status, 200)
        self.assertEqual(started["status"], "done")
        self.assertEqual(self.collect.call_count, 1)

    def test_search_start_same_keyword_deduplicates(self):
        """同词并发启动只执行一次真实采集。"""
        entered, release = threading.Event(), threading.Event()

        def slow_collect(*args, **kwargs):
            entered.set()
            release.wait(3)
            return ([sample(i) for i in range(2)], [], {})
        saved = self.collect.side_effect
        self.collect.side_effect = slow_collect
        try:
            _, first = self.request("/api/search/start", {"keyword": "dup2"})
            self.assertEqual(first["status"], "running")
            self.assertTrue(entered.wait(2))
            _, second = self.request("/api/search/start", {"keyword": "dup2"})
            self.assertEqual(second["status"], "running")
        finally:
            self.collect.side_effect = saved
            release.set()
        self.assertEqual(self.collect.call_count, 1)

    def test_search_progress_unknown_task_idle(self):
        """未启动过任务的进度查询返回 idle，而不是报错。"""
        _, progress = self.request("/api/search/progress?task=never")
        self.assertEqual(progress["status"], "idle")
        self.assertEqual(progress["collected"], 0)

    def test_search_progress_missing_task_rejected(self):
        """缺少 task 参数的进度查询必须 400。"""
        status, body = self.request("/api/search/progress")
        self.assertEqual(status, 400)
        self.assertIn("error", body)

    def test_search_progress_partial_entry_stays_running(self):
        """主词阶段快照在缓存时，进度仍标记 running 但第 1 页已可取。"""
        import collect.search_pipeline as sp
        entry = {"keyword": "part", "expanded": ["part"],
                 "posts": [sample(i) for i in range(22)],
                 "errors": [], "partial": True, "created": time.time()}
        self.pipe._cache["part"] = entry
        _, progress = self.request("/api/search/progress?task=part")
        self.assertEqual(progress["status"], "running")
        self.assertEqual(progress["collected"], 22)
        _, result = self.request("/api/search",
                                 {"keyword": "part", "page": 1, "size": 10})
        self.assertEqual(result["total"], 22)
        self.assertEqual(len(result["rows"]), 10)


class SearchLogicTests(unittest.TestCase):
    """固定样例验证去重、排序、来源错误与评论降级。"""
    def setUp(self):
        """创建不启动后台任务的搜索管道。"""
        self.pipe = SearchPipeline()
        self.addCleanup(self.pipe._executor.shutdown, wait=True)

    def test_multiword_merge_and_errors(self):
        """多个词搜索合并时保留首次重复项并按现有指标排序。"""
        first = sample(1)
        with patch.object(self.pipe, "fuzzy_expand", return_value=["topic", "variant"]), patch("collect.search_pipeline.orchestrator.collect", side_effect=[([first], ["source error"], {}), ([sample(1, title="duplicate"), sample(9)], [], {})]):
            data = self.pipe.run_search("topic")
        self.assertEqual([p.url for p in data["posts"]], [sample(9).url, first.url])
        self.assertEqual(data["posts"][1].title, "meme")
        self.assertEqual(data["errors"], ["source error"])
        self.assertEqual(data["expanded"], ["topic", "variant"])

    def test_enrichment_starts_after_final_result_is_cached(self):
        """扩展词帖子必须先进入结果缓存，再进入评论/总结队列。"""
        main_post = sample(0)
        extended_post = sample(1, platform="weibo", url="https://example.invalid/ext")
        with patch.object(self.pipe, "fuzzy_expand", return_value=["topic", "variant"]), \
                patch("collect.search_pipeline.orchestrator.collect",
                      side_effect=[([main_post], [], {}), ([extended_post], [], {})]), \
                patch("collect.search_pipeline.llm.available", return_value=False), \
                patch.object(self.pipe, "fetch_comments", return_value=[]):
            result = self.pipe._get_or_run("topic", size=90)
        self.assertEqual([p.url for p in result["posts"]],
                         [main_post.url, extended_post.url])
        self.assertIn(main_post.url, self.pipe._summary_cache)
        self.assertIn(extended_post.url, self.pipe._summary_cache)

    def test_comment_success_and_unavailable(self):
        """B站评论成功时取前三条，请求失败或缺ID时降级为空。"""
        post = sample(0, extra={"bvid": "fake"})
        with patch.object(self.pipe._session, "get_json", side_effect=[{"data": {"cid": 1}}, {"data": {"replies": [{"content": {"message": f"comment{i}"}} for i in range(5)]}}]):
            self.assertEqual(self.pipe.fetch_comments(post), ["comment0", "comment1", "comment2"])
        with patch.object(self.pipe._session, "get_json", side_effect=RuntimeError("network")):
            self.assertEqual(self.pipe.fetch_comments(post), [])
        self.assertEqual(self.pipe.fetch_comments(sample(0)), [])

    def test_count_supports_wan_commas_and_invalid(self):
        """热度计数解析：数字/逗号/万/亿支持，非法值与布尔按0不抛错。"""
        self.assertEqual(SearchPipeline._count("1.4万"), 14000.0)
        self.assertEqual(SearchPipeline._count("1,200"), 1200.0)
        self.assertEqual(SearchPipeline._count("3亿"), 300000000.0)
        self.assertEqual(SearchPipeline._count(500), 500.0)
        self.assertEqual(SearchPipeline._count(""), 0.0)
        self.assertEqual(SearchPipeline._count("abc"), 0.0)
        self.assertEqual(SearchPipeline._count(None), 0.0)
        self.assertEqual(SearchPipeline._count(True), 0.0)

    def test_hot_score_orders_without_crash(self):
        """含“万/逗号/非法值”的帖子参与热度排序时不抛错，最热的排最前。"""
        posts = [sample(i, extra=extra) for i, extra in enumerate([
            {"liked": "1.4万"}, {"liked": "abc"}, {"play": "1,200"},
            {"video_review": 500}, {},
        ])]
        ordered = sorted(posts, key=SearchPipeline._hot_score, reverse=True)
        self.assertEqual(ordered[0].extra["liked"], "1.4万")
        self.assertEqual(len(ordered), 5)

    # ------------------------------------------------ 平台混合分页（阶段6）
    def test_balanced_order_every_page_has_all_platforms(self):
        """轮转交错后，前几页每一页都同时出现 B站/小红书/知乎/微博/豆瓣。"""
        from collect.post import Post

        def mk(platform, i, hot):
            return Post(platform=platform, title=f"{platform}{i}", text="t",
                        url=f"https://x.invalid/{platform}/{i}", author="a",
                        published_at="2026-11-01 00:00:00",
                        source_adapter="fake", keyword="k",
                        extra={"liked": hot})

        posts = []
        for pl in ("bilibili", "xiaohongshu", "zhihu", "weibo", "douban"):
            for i in range(30):
                posts.append(mk(pl, i, 1000 - i))
        ordered = SearchPipeline._balanced_order(posts)
        # 每 20 条一页，前 5 页都必须四种核心平台齐全。
        for page in range(5):
            rows = ordered[page * 20:(page + 1) * 20]
            plats = {p.platform for p in rows}
            for need in ("bilibili", "xiaohongshu", "zhihu", "weibo"):
                self.assertIn(need, plats, f"第 {page + 1} 页缺 {need}")
        # 平台内部仍按热度降序：小红书第 1、2 条热度 1000、999。
        xhs = [p for p in ordered if p.platform == "xiaohongshu"]
        self.assertEqual(xhs[0].extra["liked"], 1000)
        self.assertEqual(xhs[1].extra["liked"], 999)

    def test_balanced_order_single_platform_desc(self):
        """单平台时混合排序退化为按热度降序（兼容旧分页行为）。"""
        posts = [sample(i, extra={"play": i}) for i in range(24)]
        ordered = SearchPipeline._balanced_order(posts)
        self.assertEqual([p.extra["play"] for p in ordered],
                         list(range(23, -1, -1)))

    def test_assemble_partial_and_final(self):
        """主词快照带 partial 标记；最终结果不带，供进度查询区分。"""
        posts = [sample(i, extra={"play": i}) for i in range(6)]
        data = self.pipe._assemble("t", ["t"], posts, [], partial=True)
        self.assertTrue(data["partial"])
        self.assertEqual(len(data["posts"]), 6)
        final = self.pipe._assemble("t", ["t"], posts, [])
        self.assertNotIn("partial", final)
        self.assertEqual(final["posts"][0].extra["play"], 5)


if __name__ == "__main__":
    unittest.main()
