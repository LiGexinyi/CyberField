"""账号状态机与登录 / 验证 / 退出管理的单元测试。

通过 patch 模块级路径常量，把所有子进程与真实档案隔离到临时目录。
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import collect.account_manager as am_mod
from collect.account_manager import AccountManager


class _FakeProcess:
    """模拟登录脚本子进程：逐行吐出协议，wait 返回退出码。"""
    def __init__(self, lines, code=0):
        self._lines = [line + "\n" for line in lines]
        self._code = code

    @property
    def stdout(self):
        return iter(self._lines)

    def wait(self):
        return self._code

    def poll(self):
        """模拟已退出的子进程，供关闭清理直接跳过。"""
        return self._code


class AccountManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.mc = base / "mc"
        self.mc.mkdir()
        self.state_file = base / "data" / "accounts.json"
        patcher = patch.multiple(
            am_mod,
            _MC_DIR=self.mc,
            _MC_PYTHON=self.mc / "missing-python.exe",
            _LOGIN_SCRIPT=self.mc / "login_standalone.py",
            _ZHIHU_LOGIN_SCRIPT=self.mc / "zhihu_login_standalone.py",
            _VERIFY_SCRIPT=self.mc / "verify_session.py",
            _STATE_FILE=self.state_file,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def _mgr(self):
        return AccountManager()

    def test_accounts_shape(self):
        acc = self._mgr().accounts()
        self.assertEqual([a["platform"] for a in acc],
                         ["xhs", "zhihu", "bili", "wb", "douban"])
        by = {a["platform"]: a for a in acc}
        self.assertFalse(by["douban"]["login_supported"])
        self.assertTrue(by["xhs"]["login_supported"])
        self.assertEqual(by["xhs"]["state"], "no_profile")
        self.assertEqual(by["bili"]["search_mode"], "游客模式")

    def test_state_persistence(self):
        mgr = self._mgr()
        mgr.apply_verify_result("xhs", "ok", "测试昵称", None)
        self.assertEqual(mgr.accounts()[0]["state"], "logged_in")
        self.assertEqual(mgr.accounts()[0]["nickname"], "测试昵称")
        # 重新实例化（模拟服务重启）后仍能读回
        mgr2 = self._mgr()
        st = {a["platform"]: a for a in mgr2.accounts()}
        self.assertEqual(st["xhs"]["state"], "logged_in")
        self.assertEqual(st["xhs"]["nickname"], "测试昵称")

    def test_verify_mapping(self):
        mgr = self._mgr()
        mgr.apply_verify_result("zhihu", "ok", "知友", None)
        self.assertEqual(mgr.platform_state("zhihu")["state"], "logged_in")
        mgr.apply_verify_result("zhihu", "invalid", None, "未登录")
        self.assertEqual(mgr.platform_state("zhihu")["state"], "expired")
        mgr.apply_verify_result("zhihu", "missing", None, "无档案")
        self.assertEqual(mgr.platform_state("zhihu")["state"], "no_profile")

    def test_network_error_keeps_nickname_and_unknown(self):
        mgr = self._mgr()
        mgr.apply_verify_result("bili", "ok", "B站用户", None)
        mgr.apply_verify_result("bili", "network", None, "连接超时")
        st = mgr.platform_state("bili")
        self.assertEqual(st["state"], "unknown")     # 网络错误 → 状态未知
        self.assertEqual(st["nickname"], "B站用户")    # 不降级、保留昵称

    def test_last_verified_at_only_updates_on_real_verify(self):
        """只有真实验证结果才更新“最近验证时间”，取消/退出不冒充验证。"""
        mgr = self._mgr()
        with patch.object(am_mod, "_now_iso", return_value="2026-11-15 10:00:00"):
            mgr.apply_verify_result("xhs", "ok", "昵称", None)
        self.assertEqual(mgr.platform_state("xhs")["last_verified_at"],
                         "2026-11-15 10:00:00")
        # 非验证操作（登录失败后的取消）不得更新最近验证时间。
        mgr.start_login("xhs")   # _MC_PYTHON 不存在 → 直接 failed
        mgr.cancel_login("xhs")
        self.assertEqual(mgr.platform_state("xhs")["last_verified_at"],
                         "2026-11-15 10:00:00")
        # 真实验证（即使网络错误）应更新时间。
        with patch.object(am_mod, "_now_iso", return_value="2026-11-15 11:00:00"):
            mgr.apply_verify_result("xhs", "network", None, "超时")
        self.assertEqual(mgr.platform_state("xhs")["last_verified_at"],
                         "2026-11-15 11:00:00")

    def test_login_failed_then_cancel_reverts(self):
        mgr = self._mgr()
        # _MC_PYTHON 指向不存在的解释器 → start_login 直接 failed，不拉起进程
        job = mgr.start_login("xhs")
        self.assertEqual(job["status"], "failed")
        self.assertEqual(mgr.platform_state("xhs")["state"], "login_failed")
        mgr.cancel_login("xhs")
        self.assertEqual(mgr.platform_state("xhs")["state"], "no_profile")

    def test_logout_removes_only_this_profile(self):
        mgr = self._mgr()
        (self.mc / "browser_data" / "xhs_user_data_dir").mkdir(parents=True)
        (self.mc / "browser_data" / "zhihu_user_data_dir").mkdir(parents=True)
        mgr.apply_verify_result("xhs", "ok", "昵称", None)
        res = mgr.logout("xhs")
        self.assertTrue(res["ok"])
        self.assertFalse(
            (self.mc / "browser_data" / "xhs_user_data_dir").exists())
        self.assertTrue(
            (self.mc / "browser_data" / "zhihu_user_data_dir").exists())
        self.assertEqual(mgr.platform_state("xhs")["state"], "no_profile")

    # ------------------------------------------------------ 登录脚本协议与诊断
    def _login_reader_job(self, mgr, process):
        """构造一个已登记的知乎登录任务并直接驱动 _login_reader。"""
        mgr._generations["zhihu"] = 1
        job = {"platform": "zhihu", "generation": 1, "proc": process,
               "qr": None, "qr_error": None, "status": "starting",
               "error": None, "prev_snapshot": mgr._default_state()}
        mgr._login_jobs["zhihu"] = job
        return job

    def test_login_reader_qr_then_success(self):
        """QR 行后接 LOGGED_IN：任务成功，二维码交前端，随后自动验证。"""
        mgr = self._mgr()
        job = self._login_reader_job(mgr, _FakeProcess(["QR:AAAA", "LOGGED_IN"], code=0))
        with patch.object(mgr, "_begin_verify") as verify:
            mgr._login_reader(job)
        self.assertEqual(job["status"], "logged_in")
        self.assertEqual(job["qr"], "AAAA")
        verify.assert_called_once_with("zhihu", expected=1)

    def test_login_reader_qr_missing_then_success(self):
        """读不到二维码但窗口内完成扫码：仍判定登录成功并自动验证。"""
        mgr = self._mgr()
        job = self._login_reader_job(
            mgr, _FakeProcess(["QR_MISSING:未能自动截取二维码，请在窗口内扫码", "LOGGED_IN"], code=0))
        with patch.object(mgr, "_begin_verify") as verify:
            mgr._login_reader(job)
        self.assertEqual(job["status"], "logged_in")
        self.assertIsNone(job["qr"])
        self.assertIn("窗口内扫码", job["qr_error"])
        verify.assert_called_once_with("zhihu", expected=1)

    def test_login_reader_crash_captures_reason(self):
        """脚本崩溃（退出码非0）时，从输出尾部提取可读原因而非笼统提示。"""
        mgr = self._mgr()
        process = _FakeProcess([
            "[ZhiHu.login_by_qrcode] login failed , have not found qrcode please check ....",
            "Traceback (most recent call last):",
            "    raise TimeoutError(...)",
        ], code=1)
        job = self._login_reader_job(mgr, process)
        with patch.object(mgr, "_begin_verify") as verify:
            mgr._login_reader(job)
        self.assertEqual(job["status"], "failed")
        self.assertIn("have not found qrcode", job["error"])
        self.assertEqual(mgr.platform_state("zhihu")["state"], "login_failed")
        verify.assert_not_called()

    def test_login_reader_qr_then_crash_expired(self):
        """已展示过二维码后脚本退出失败：按二维码过期处理，保留二维码。"""
        mgr = self._mgr()
        job = self._login_reader_job(mgr, _FakeProcess(["QR:BBBB"], code=1))
        with patch.object(mgr, "_begin_verify") as verify:
            mgr._login_reader(job)
        self.assertEqual(job["status"], "expired")
        self.assertEqual(job["qr"], "BBBB")
        self.assertEqual(mgr.platform_state("zhihu")["state"], "expired")
        verify.assert_not_called()

    def test_zhihu_login_uses_dedicated_script_and_profile(self):
        """知乎登录启动自建脚本，并显式传入专用档案目录。"""
        (self.mc / "zhihu_login_standalone.py").write_text("print()", encoding="utf-8")
        python = self.mc / "py.exe"
        python.write_text("", encoding="utf-8")
        mgr = self._mgr()
        popen = Mock(return_value=_FakeProcess([], code=0))
        with patch.object(am_mod, "_MC_PYTHON", python), patch.object(am_mod.subprocess, "Popen", popen):
            job = mgr.start_login("zhihu")
        args = popen.call_args.args[0]
        self.assertEqual(args[0], str(python))
        self.assertTrue(str(args[1]).endswith("zhihu_login_standalone.py"))
        self.assertIn("--profile", args)
        profile = args[args.index("--profile") + 1]
        self.assertEqual(profile, str(self.mc / "browser_data" / "zhihu_user_data_dir"))
        self.assertEqual(job["status"], "starting")
        mgr.close()   # 干净回收登录读取线程，避免污染后续测试


if __name__ == "__main__":
    unittest.main()
