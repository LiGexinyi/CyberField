"""账号状态机与登录 / 验证 / 退出管理的单元测试。

通过 patch 模块级路径常量，把所有子进程与真实档案隔离到临时目录。
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import collect.account_manager as am_mod
from collect.account_manager import AccountManager


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


if __name__ == "__main__":
    unittest.main()
