"""小红书登录态搜索适配器测试：假脚本输出协议，不访问真实平台/账号。"""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from collect.sources import create_source
from collect.sources.base_source import SourceUnavailable
from collect.sources.xhs_source import XhsApiSource


def _ok_stdout(items):
    return SimpleNamespace(returncode=0,
                           stdout=__import__("json").dumps(
                               {"ok": True, "items": items}, ensure_ascii=False) + "\n",
                           stderr="")


class XhsApiSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.mc = base / "mc"
        self.mc.mkdir()
        (self.mc / ".venv" / "Scripts").mkdir(parents=True)
        (self.mc / ".venv" / "Scripts" / "python.exe").touch()
        (self.mc / "xhs_search_standalone.py").touch()
        (self.mc / "browser_data").mkdir()
        (self.mc / "browser_data" / "xhs_user_data_dir").mkdir()
        self.src = XhsApiSource(
            mc_dir=str(self.mc),
            mc_python=str(self.mc / ".venv" / "Scripts" / "python.exe"),
            script=str(self.mc / "xhs_search_standalone.py"),
            timeout=30)

    def tearDown(self):
        self.tmp.cleanup()

    def _item(self, **changes):
        fields = dict(
            id="abc123", xsec_token="t0k3n", xsec_source="pc_search",
            model_type="note", type="normal", title="标题",
            desc="正文内容", user={"nickname": "作者"},
            interact_info={"liked_count": "1.2万", "collected_count": 88,
                           "comment_count": "12"},
        )
        fields.update(changes)
        return fields

    def test_to_post_unwrapped_item(self):
        """无 note_card 包装的搜索项也能转成统一 Post。"""
        post = self.src._to_post(self._item(), "奶茶")
        self.assertEqual(post.platform, "xiaohongshu")
        self.assertEqual(post.title, "标题")
        self.assertEqual(post.text, "正文内容")
        self.assertEqual(post.author, "作者")
        self.assertIn("abc123", post.url)
        self.assertIn("xsec_token=t0k3n", post.url)
        self.assertEqual(post.source_adapter, "xhs_api")
        self.assertEqual(post.keyword, "奶茶")
        self.assertEqual(post.extra["liked"], "1.2万")

    def test_to_post_wrapped_note_card(self):
        """带 note_card 包装时字段取内部卡片，id 缺失时回退顶层。"""
        item = {"note_card": {"title": "卡标题", "desc": "卡正文",
                              "interact_info": {"liked_count": 3}},
                "id": "outer-id"}
        post = self.src._to_post(item, "词")
        self.assertEqual(post.title, "卡标题")
        self.assertIn("outer-id", post.url)

    def test_to_post_display_title(self):
        """真实搜索卡片标题在 display_title，desc 缺失也不丢标题。"""
        item = {"id": "n1", "xsec_token": "tk",
                "note_card": {"display_title": "11月奶茶买一送一时间表",
                              "user": {"nickname": "作者甲"},
                              "interact_info": {"liked_count": "177",
                                                "shared_count": "153"}}}
        post = self.src._to_post(item, "奶茶")
        self.assertEqual(post.title, "11月奶茶买一送一时间表")
        self.assertEqual(post.author, "作者甲")
        self.assertEqual(post.extra["liked"], "177")
        self.assertEqual(post.extra["shared"], "153")

    def test_text_falls_back_to_title_survives_cleaner(self):
        """列表卡片无 desc 时正文回退标题，过清洗器不被当空文本删除。"""
        from collect import cleaner
        item = {"id": "n1", "xsec_token": "tk",
                "note_card": {"display_title": "只有标题的卡片",
                              "interact_info": {}}}
        post = self.src._to_post(item, "奶茶")
        self.assertEqual(post.text, "只有标题的卡片")
        out, stats = cleaner.clean_posts([post])
        self.assertEqual(len(out), 1)
        self.assertEqual(stats["empty_removed"], 0)

    def test_search_converts_items(self):
        """search 解析脚本输出并把 items 转成 Post。"""
        item = self._item()
        self.src._run = lambda kw, lim: _ok_stdout([item])
        posts = self.src.search("奶茶", platform="xhs", limit=20)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].title, "标题")

    def test_search_unsupported_platform_empty(self):
        """其他平台调用本源时静默返回空，交由对应源处理。"""
        self.src._run = lambda kw, lim: (_ for _ in ()).throw(
            AssertionError("不应调用"))
        self.assertEqual(self.src.search("词", platform="bili"), [])

    def test_search_login_expired_raises_friendly(self):
        """登录态失效时抛 SourceUnavailable，提示去账号面板重登。"""
        self.src._run = lambda kw, lim: SimpleNamespace(
            returncode=1,
            stdout='{"ok": false, "reason": "login_expired",'
                   ' "hint": "小红书登录态失效，请在账号面板重新登录"}',
            stderr="")
        with self.assertRaises(SourceUnavailable) as ctx:
            self.src.search("词", platform="xhs")
        self.assertIn("登录态失效", str(ctx.exception))
        self.assertNotIn("浏览器启动失败", str(ctx.exception))

    def test_search_api_error_friendly(self):
        """风控/错误原因转成可读提示，不回传异常原文。"""
        self.src._run = lambda kw, lim: SimpleNamespace(
            returncode=1,
            stdout='{"ok": false, "reason": "api_error", "hint": "被拦截"}',
            stderr="")
        with self.assertRaises(SourceUnavailable) as ctx:
            self.src.search("词", platform="xhs")
        self.assertIn("被拦截", str(ctx.exception))

    def test_parse_output_takes_last_json_line(self):
        """输出含日志时取最后一行 JSON。"""
        result = SimpleNamespace(
            returncode=0,
            stdout="[LOG] something\n" + '{"ok": true, "items": []}\n',
            stderr="")
        payload = self.src._parse_output(result)
        self.assertTrue(payload["ok"])

    def test_health_check(self):
        """脚本/解释器/档案齐全时健康检查通过；缺一即失败。"""
        self.assertTrue(self.src.health_check())
        (self.mc / "xhs_search_standalone.py").unlink()
        self.assertFalse(self.src.health_check())

    def test_registry(self):
        """xhs_api 已登记进源注册表，可按名创建。"""
        src = create_source("xhs_api", mc_dir=str(self.mc))
        self.assertIsInstance(src, XhsApiSource)
        self.assertEqual(src.name, "xhs_api")


if __name__ == "__main__":
    unittest.main()
