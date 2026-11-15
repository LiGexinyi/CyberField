"""知乎登录态搜索适配器测试：假脚本输出协议，不访问真实平台/账号。"""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from collect.sources import create_source
from collect.sources.base_source import SourceUnavailable
from collect.sources.zhihu_source import ZhihuApiSource


def _ok_stdout(items):
    return SimpleNamespace(
        returncode=0,
        stdout=json.dumps({"ok": True, "items": items}, ensure_ascii=False) + "\n",
        stderr="")


class ZhihuApiSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.mc = base / "mc"
        self.mc.mkdir()
        (self.mc / ".venv" / "Scripts").mkdir(parents=True)
        (self.mc / ".venv" / "Scripts" / "python.exe").touch()
        (self.mc / "zhihu_search_standalone.py").touch()
        (self.mc / "browser_data").mkdir()
        (self.mc / "browser_data" / "zhihu_user_data_dir").mkdir()
        self.src = ZhihuApiSource(
            mc_dir=str(self.mc),
            mc_python=str(self.mc / ".venv" / "Scripts" / "python.exe"),
            script=str(self.mc / "zhihu_search_standalone.py"),
            timeout=30)

    def tearDown(self):
        self.tmp.cleanup()

    def _item(self, **changes):
        fields = dict(
            content_id="q1/a2", content_type="answer",
            content_url="https://www.zhihu.com/question/1/answer/2",
            title="奶茶会让人上瘾吗？",
            desc="关于奶茶成瘾性的一篇讨论。",
            voteup_count=3525, comment_count=407,
            created_time=1730000000, updated_time=1731000000,
            user_nickname="知友甲",
        )
        fields.update(changes)
        return fields

    def test_to_post_maps_fields(self):
        """搜索项正确映射为统一 Post，热度指标进 extra。"""
        post = self.src._to_post(self._item(), "奶茶")
        self.assertEqual(post.platform, "zhihu")
        self.assertEqual(post.title, "奶茶会让人上瘾吗？")
        self.assertEqual(post.text, "关于奶茶成瘾性的一篇讨论。")
        self.assertEqual(post.url, "https://www.zhihu.com/question/1/answer/2")
        self.assertEqual(post.author, "知友甲")
        self.assertEqual(post.source_adapter, "zhihu_api")
        self.assertEqual(post.keyword, "奶茶")
        self.assertEqual(post.extra["voteup"], 3525)
        self.assertEqual(post.extra["comment"], 407)
        self.assertEqual(post.extra["content_type"], "answer")

    def test_text_falls_back_to_title_survives_cleaner(self):
        """列表项无 desc 时正文回退标题，过清洗器不被当空文本删除。"""
        from collect import cleaner
        item = self._item(desc="", content_type="video")
        post = self.src._to_post(item, "奶茶")
        self.assertEqual(post.text, "奶茶会让人上瘾吗？")
        out, stats = cleaner.clean_posts([post])
        self.assertEqual(len(out), 1)
        self.assertEqual(stats["empty_removed"], 0)

    def test_search_converts_items(self):
        """search 解析脚本输出并把 items 转成 Post。"""
        self.src._run = lambda kw, lim: _ok_stdout([self._item()])
        posts = self.src.search("奶茶", platform="zhihu", limit=20)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].title, "奶茶会让人上瘾吗？")

    def test_search_honors_limit(self):
        """超过 limit 的条目被截断。"""
        items = [self._item(content_id=f"q{i}") for i in range(5)]
        self.src._run = lambda kw, lim: _ok_stdout(items)
        posts = self.src.search("词", platform="zhihu", limit=3)
        self.assertEqual(len(posts), 3)

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
                   ' "hint": "知乎登录态失效，请在账号面板重新登录"}',
            stderr="")
        with self.assertRaises(SourceUnavailable) as ctx:
            self.src.search("词", platform="zhihu")
        self.assertIn("登录态失效", str(ctx.exception))
        self.assertNotIn("浏览器启动失败", str(ctx.exception))

    def test_search_api_error_friendly(self):
        """风控/错误原因转成可读提示，不回传异常原文。"""
        self.src._run = lambda kw, lim: SimpleNamespace(
            returncode=1,
            stdout='{"ok": false, "reason": "api_error", "hint": "被拦截"}',
            stderr="")
        with self.assertRaises(SourceUnavailable) as ctx:
            self.src.search("词", platform="zhihu")
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
        (self.mc / "zhihu_search_standalone.py").unlink()
        self.assertFalse(self.src.health_check())

    def test_registry(self):
        """zhihu_api 已登记进源注册表，可按名创建。"""
        src = create_source("zhihu_api", mc_dir=str(self.mc))
        self.assertIsInstance(src, ZhihuApiSource)
        self.assertEqual(src.name, "zhihu_api")


if __name__ == "__main__":
    unittest.main()
