"""采集回归测试：使用内存假源，不联网、不写真实数据库。"""
import unittest
from unittest.mock import patch
from collect import orchestrator, cleaner
from collect.post import Post


def make_post(text="valid", url="u"):
    """构造独立测试记录。"""
    return Post(platform="weibo", title="t", text=text, url=url, author="", published_at="", source_adapter="fake")


class FakeSource:
    """替代联网适配器。"""
    name = "fake"
    def health_check(self):
        """返回可用状态。"""
        return True
    def search(self, *args, **kwargs):
        """提供空正文和有效重复项。"""
        return [make_post(""), make_post(), make_post()]


class RegressionTests(unittest.TestCase):
    """验证数据保留、统计与异常隔离。"""
    def test_empty_before_duplicate(self):
        """有效正文不能被前面的空正文挤掉。"""
        with patch.object(orchestrator, "create_source", return_value=FakeSource()):
            rows, errors, stats = orchestrator.collect("x", source_names=("fake",), save=False)
        self.assertEqual(len(rows), 1)
        self.assertEqual(stats["empty_removed"], 1)
        self.assertEqual(stats["dup_removed"], 1)
    def test_health_failure(self):
        """健康检查异常应被记录。"""
        source = FakeSource()
        with patch.object(source, "health_check", side_effect=RuntimeError("failed")), patch.object(orchestrator, "create_source", return_value=source):
            rows, errors, _ = orchestrator.collect("x", source_names=("fake",), save=False)
        self.assertEqual(rows, [])
        self.assertEqual(len(errors), 1)
    def test_missing_links(self):
        """浏览结果中无链接记录不能相互吞并。"""
        rows, _ = cleaner.clean_posts([make_post("one", ""), make_post("two", "")])
        self.assertEqual(len(rows), 2)
    def test_bad_limit(self):
        """非法条数应在调用源之前拒绝。"""
        for limit in (0, -1, True):
            with self.assertRaises(ValueError):
                orchestrator.collect("x", limit=limit, save=False)
    def test_blank_keyword(self):
        """空关键词不能发起采集。"""
        with self.assertRaises(ValueError):
            orchestrator.collect(" ", save=False)

if __name__ == "__main__":
    unittest.main()
