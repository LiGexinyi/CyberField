"""登录管理器的单元测试：状态判定 / 账号列表 / 轮询边界。"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from collect.login_manager import LoginManager, PLATFORMS


class LoginManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mc_dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _manager(self):
        mgr = LoginManager()
        patch.object(mgr, "browser_dir",
                     lambda platform: self.mc_dir / "browser_data"
                     / f"{platform}_user_data_dir").start()
        self.addCleanup(patch.stopall)
        return mgr

    def _make_profile(self, platform, cookie_bytes=b"cookie-data"):
        profile = self.mc_dir / "browser_data" / f"{platform}_user_data_dir"
        (profile / "Default" / "Network").mkdir(parents=True, exist_ok=True)
        (profile / "Default" / "Network" / "Cookies").write_bytes(cookie_bytes)
        return profile

    def test_missing_profile_is_not_logged_in(self):
        self.assertFalse(self._manager().is_logged_in("zhihu"))

    def test_empty_cookie_is_not_logged_in(self):
        self._make_profile("xhs", cookie_bytes=b"")
        self.assertFalse(self._manager().is_logged_in("xhs"))

    def test_cookie_profile_is_logged_in(self):
        self._make_profile("xhs")
        self.assertTrue(self._manager().is_logged_in("xhs"))

    def test_accounts_shape(self):
        self._make_profile("xhs")
        acc = self._manager().accounts()
        self.assertEqual([a["platform"] for a in acc],
                         [p for p, _ in PLATFORMS])
        by = {a["platform"]: a for a in acc}
        self.assertTrue(by["xhs"]["logged_in"])
        self.assertFalse(by["zhihu"]["logged_in"])
        self.assertEqual(by["bili"]["label"], "B站")

    def test_poll_idle_without_job(self):
        self.assertEqual(self._manager().poll_login("xhs"),
                         {"status": "idle"})


if __name__ == "__main__":
    unittest.main()
