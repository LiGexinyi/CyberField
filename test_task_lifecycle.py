"""后台任务竞态回归：事件控制执行顺序，不依赖真实网络或登录态。"""
import threading
import queue
import time
import unittest
from unittest.mock import patch
from collect.search_pipeline import SearchPipeline
from test_search_web import sample
import test_account_manager as account_tests


class SummaryLifecycleTests(unittest.TestCase):
    """复现总结尚未完成却报告done，以及失败任务无终态。"""
    def setUp(self):
        """准备虚构缓存；所有外部来源由假函数替代。"""
        self.pipe = SearchPipeline()
        self.post = sample(0)
        self.addCleanup(self.pipe._executor.shutdown, wait=True)
        self.pipe._cache["topic"] = {"posts": [self.post]}

    def test_running_task_is_not_done(self):
        """阻塞评论获取，执行过程中done必须为False。"""
        entered, release = threading.Event(), threading.Event()
        def blocked(post):
            """模拟可控的在途请求。"""
            entered.set()
            release.wait(3)
            return ["comment"]
        with patch.object(self.pipe, "fetch_comments", side_effect=blocked), patch("collect.search_pipeline.llm.available", return_value=False):
            try:
                self.pipe.start_enrichment("topic")
                self.assertTrue(entered.wait(2))
                self.assertFalse(self.pipe.summary_state("topic")[0]["done"])
            finally:
                release.set()
                self.pipe._executor.shutdown(wait=True)
        self.assertTrue(self.pipe.summary_state("topic")[0]["done"])

    def test_exception_has_terminal_state(self):
        """异常任务必须结束轮询，并报告失败而不是永远生成中。"""
        with patch.object(self.pipe, "fetch_comments", side_effect=RuntimeError("fake failure")):
            self.pipe.start_enrichment("topic")
            self.pipe._executor.shutdown(wait=True)
        state = self.pipe.summary_state("topic")[0]
        self.assertTrue(state["done"])
        self.assertEqual(state.get("status"), "failed")

    def test_close_rejects_new_work(self):
        """关闭可重复调用，关闭后不得提交新任务。"""
        self.pipe.close()
        self.pipe.close()
        with self.assertRaises(RuntimeError):
            self.pipe.start_enrichment("topic")

    def test_failed_model_is_not_reported_as_disabled(self):
        """已配置但返回空结果的模型应明确失败。"""
        with patch("collect.settings.ENABLE_AI_SUMMARY", True), patch.object(self.pipe, "fetch_comments", return_value=["comment"]), patch("collect.search_pipeline.llm.available", return_value=True), patch("collect.search_pipeline.llm.summarize_post", return_value=None):
            self.pipe.start_enrichment("topic")
            self.pipe._executor.shutdown(wait=True)
        state = self.pipe.summary_state("topic")[0]
        self.assertEqual(state["status"], "failed")
        self.assertEqual(state["comments"], ["comment"])
        self.assertTrue(state["done"])

    def test_close_cancels_queued_and_blocks_late_write(self):
        """关闭时取消未执行任务，运行中的旧结果不能覆盖取消状态。"""
        entered, release = threading.Event(), threading.Event()
        # 单工作线程保证第二条仍在队列里，不依赖调度时机。
        self.pipe._executor.shutdown(wait=True)
        from concurrent.futures import ThreadPoolExecutor
        self.pipe._executor = ThreadPoolExecutor(max_workers=1)
        self.pipe._cache["topic"]["posts"].append(sample(1))
        def blocked(post):
            """模拟不能立刻中断的在途IO。"""
            entered.set()
            release.wait(3)
            return ["late comment"]
        with patch.object(self.pipe, "fetch_comments", side_effect=blocked) as fetch, patch("collect.search_pipeline.llm.available", return_value=False):
            try:
                self.pipe.start_enrichment("topic")
                self.assertTrue(entered.wait(2))
                self.assertFalse(self.pipe.close(timeout=0))
                self.assertTrue(all(s["status"] == "cancelled" and s["done"] for s in self.pipe.summary_state("topic")))
            finally:
                release.set()
                self.pipe._executor.shutdown(wait=True)
            self.assertEqual(fetch.call_count, 1)
        self.assertTrue(all(s["status"] == "cancelled" and not s["comments"] for s in self.pipe.summary_state("topic")))


class AccountRaceTests(unittest.TestCase):
    """复用临时目录隔离，仅在选定测试中控制验证线程。"""
    setUp = account_tests.AccountManagerTests.setUp
    tearDown = account_tests.AccountManagerTests.tearDown
    _mgr = account_tests.AccountManagerTests._mgr

    def test_old_verification_cannot_restore_logout(self):
        """验证等待期间退出，旧验证成功结果不得恢复已登录。"""
        manager = self._mgr()
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        def verify(*args):
            """模拟退出后才返回成功的旧验证。"""
            entered.set()
            release.wait(3)
            return {"kind": "ok", "nickname": "old", "error": None}
        original = manager._verify_worker
        def worker(*args):
            """记录工作线程退出，避免用sleep猜测执行完成。"""
            try:
                original(*args)
            finally:
                finished.set()
        with patch.object(manager, "_run_verify", side_effect=verify), patch.object(manager, "_verify_worker", side_effect=worker):
            try:
                manager.start_verify("xhs")
                self.assertTrue(entered.wait(2))
                self.assertTrue(manager.logout("xhs")["ok"])
            finally:
                release.set()
                self.assertTrue(finished.wait(2))
        self.assertEqual(manager.platform_state("xhs")["state"], "no_profile")

    def test_new_verification_wins_over_old_result(self):
        """新验证先结束后，旧验证迟到不能覆盖昵称和状态。"""
        manager = self._mgr()
        entered, release = threading.Event(), threading.Event()
        finished = queue.Queue()
        original = manager._verify_worker
        first = [True]
        def verify(*args):
            """第一次等待，第二次立即返回不同昵称。"""
            if first[0]:
                first[0] = False
                entered.set()
                release.wait(3)
                return {"kind": "ok", "nickname": "old"}
            return {"kind": "ok", "nickname": "new"}
        def worker(*args):
            """用队列确认每个工作线程已回写或拒绝回写。"""
            try:
                original(*args)
            finally:
                finished.put(True)
        with patch.object(manager, "_run_verify", side_effect=verify), patch.object(manager, "_verify_worker", side_effect=worker):
            try:
                manager.start_verify("xhs")
                self.assertTrue(entered.wait(2))
                manager.start_verify("xhs")
                finished.get(timeout=2)
                self.assertEqual(manager.platform_state("xhs")["nickname"], "new")
            finally:
                release.set()
                finished.get(timeout=2)
        self.assertEqual(manager.platform_state("xhs")["nickname"], "new")
        manager.close()

    def test_cancel_restores_nickname_and_rejects_old_reader(self):
        """取消恢复昵称；旧扫码成功行不得再次触发验证。"""
        manager = self._mgr()
        manager.apply_verify_result("xhs", "ok", "before", None)
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        class FakeProcess:
            """仅模拟本测试拥有的进程，没有实际PID。"""
            pid = None
            def __init__(self):
                """进程输出由事件控制。"""
                self.returncode = None
                self.stdout = self.lines()
            def lines(self):
                """取消后才输出认证成功。"""
                entered.set()
                release.wait(3)
                yield "LOGGED_IN\n"
            def poll(self):
                """返回模拟退出码。"""
                return self.returncode
            def kill(self):
                """标记进程被结束。"""
                self.returncode = -1
            def wait(self, timeout=None):
                """模拟回收。"""
                return self.returncode or 0
        import collect.account_manager as account_module
        account_module._LOGIN_SCRIPT.touch()
        account_module._MC_PYTHON.touch()
        original = manager._login_reader
        def reader(job):
            """记录旧读线程完成。"""
            try:
                original(job)
            finally:
                finished.set()
        process = FakeProcess()
        with patch("collect.account_manager.subprocess.Popen", return_value=process), patch.object(manager, "_login_reader", side_effect=reader), patch.object(manager, "_run_verify") as verify:
            try:
                manager.start_login("xhs")
                self.assertTrue(entered.wait(2))
                manager.cancel_login("xhs")
            finally:
                release.set()
                self.assertTrue(finished.wait(2))
            verify.assert_not_called()
        self.assertEqual(manager.platform_state("xhs")["nickname"], "before")
        self.assertEqual(manager.poll_login("xhs")["status"], "cancelled")
        manager.close()

    def test_closed_manager_ignores_late_result_and_preserves_profile(self):
        """关闭不删除档案，迟到验证不回写，关闭后拒绝操作。"""
        manager = self._mgr()
        profile = manager.browser_dir("xhs")
        profile.mkdir(parents=True)
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        def verify(*args):
            """模拟已在运行但还未返回的验证。"""
            entered.set()
            release.wait(3)
            return {"kind": "ok", "nickname": "late"}
        original = manager._verify_worker
        def worker(*args):
            """通知线程已结束。"""
            try:
                original(*args)
            finally:
                finished.set()
        with patch.object(manager, "_run_verify", side_effect=verify), patch.object(manager, "_verify_worker", side_effect=worker):
            try:
                manager.start_verify("xhs")
                self.assertTrue(entered.wait(2))
                self.assertFalse(manager.close(timeout=0))
                with self.assertRaises(RuntimeError):
                    manager.start_verify("xhs")
            finally:
                release.set()
                self.assertTrue(finished.wait(2))
        self.assertEqual(manager.platform_state("xhs")["state"], "pending")
        self.assertTrue(profile.exists())
        self.assertTrue(manager.close())

    def test_invalid_platform_cannot_reach_filesystem(self):
        """任意平台字符串不能转换成删除路径。"""
        manager = self._mgr()
        with self.assertRaises(ValueError), patch("collect.account_manager.shutil.rmtree") as remove:
            manager.logout("../outside")
        remove.assert_not_called()

    def test_late_cancel_after_logout_cannot_restore_login(self):
        """已登录→重新登录→退出→迟到取消：保持退出，不能恢复旧登录态。"""
        import collect.account_manager as account_module
        manager = self._mgr()
        manager.apply_verify_result("xhs", "ok", "user", None)   # 原先已登录
        account_module._LOGIN_SCRIPT.touch()
        account_module._MC_PYTHON.touch()
        class DummyProcess:
            """模拟一个不输出、不结束的登录进程。"""
            pid = None
            returncode = None
            stdout = iter(())
            def poll(self):
                """进程仍在运行。"""
                return self.returncode
            def kill(self):
                """标记被结束。"""
                self.returncode = -1
            def wait(self, timeout=None):
                """模拟回收。"""
                return self.returncode or 0
        with patch("collect.account_manager.subprocess.Popen",
                   return_value=DummyProcess()), \
             patch.object(manager, "_login_reader"):   # 阻止读线程推进任务
            manager.start_login("xhs")                 # 发起重新登录
        manager.browser_dir("xhs").mkdir(parents=True)
        manager.logout("xhs")                          # 退出：作废任务并删除档案
        result = manager.cancel_login("xhs")           # 迟到的取消
        self.assertFalse(result["cancelled"])
        self.assertEqual(manager.platform_state("xhs")["state"], "no_profile")
        self.assertIsNone(manager.platform_state("xhs")["nickname"])
        manager.close()

    def test_cancel_after_completed_login_has_no_side_effect(self):
        """登录与自动验证完成后，迟到的取消不得回写登录前快照。"""
        import collect.account_manager as account_module
        manager = self._mgr()
        account_module._LOGIN_SCRIPT.touch()
        account_module._MC_PYTHON.touch()
        class FakeProcess:
            """登录进程立即输出 LOGGED_IN，退出码 0。"""
            pid = None
            returncode = 0
            stdout = ["LOGGED_IN\n"]
            def poll(self):
                """进程已结束。"""
                return self.returncode
            def kill(self):
                """标记被结束。"""
                self.returncode = -1
            def wait(self, timeout=None):
                """模拟回收。"""
                return self.returncode or 0
        with patch("collect.account_manager.subprocess.Popen",
                   return_value=FakeProcess()), \
             patch.object(manager, "_run_verify",
                          return_value={"kind": "ok", "nickname": "done",
                                        "error": None}):
            manager.start_login("xhs")
            # 等待登录完成并自动验证回写为已登录。
            deadline = time.time() + 3
            while time.time() < deadline:
                if manager.platform_state("xhs")["state"] == "logged_in":
                    break
                time.sleep(0.02)
        self.assertEqual(manager.platform_state("xhs")["state"], "logged_in")
        result = manager.cancel_login("xhs")
        self.assertFalse(result["cancelled"])
        self.assertEqual(manager.platform_state("xhs")["nickname"], "done")
        manager.close()


class ServerCloseTests(unittest.TestCase):
    """确保关闭中的异常不会跳过其他资源清理。"""
    def test_cleanup_continues_after_pipeline_failure(self):
        """即使搜索关闭失败，账号与HTTP服务仍会关闭。"""
        from unittest.mock import Mock
        from collect.web_app import close_services
        server = Mock()
        server.pipeline.close.side_effect = RuntimeError("fake")
        with self.assertRaises(RuntimeError):
            close_services(server)
        server.account_manager.close.assert_called_once_with(timeout=2.0)
        server.server_close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
