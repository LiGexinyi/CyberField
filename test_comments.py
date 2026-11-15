"""评论模块离线测试：固定JSONL样例验证过滤、排序和读取范围。"""
import json
import tempfile
import unittest
from pathlib import Path
from collect.comments import xhs_comments_from_jsonl
from collect.post import Post


class CommentsTests(unittest.TestCase):
    """使用临时文件，不读取MediaCrawler实际采集目录。"""
    def setUp(self):
        """创建本测试拥有的目录与虚构笔记。"""
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.post = Post(platform="xiaohongshu", title="note", text="text", url="https://example.invalid/note", author="", published_at="", source_adapter="fake", extra={"note_id": "note"})

    def write_rows(self, name, rows):
        """写入小样例，同时带一行损坏JSON验证原有跳过规则。"""
        text = "\n".join(json.dumps(r) for r in rows)
        (self.root / name).write_text(text + "\ninvalid-json\n", encoding="utf-8")

    def test_recent_files_matching_note_and_like_order(self):
        """只取最近两个文件、指定笔记，并按点赞数选前三条。"""
        self.write_rows("search_comments_01.jsonl", [{"note_id": "note", "content": "old ignored", "like_count": "99万"}])
        self.write_rows("search_comments_02.jsonl", [{"note_id": "note", "content": "third", "like_count": "100"}, {"note_id": "other", "content": "other ignored", "like_count": "50万"}])
        self.write_rows("search_comments_03.jsonl", [{"note_id": "note", "content": "first", "like_count": "1.4万"}, {"note_id": "note", "content": "second", "like_count": "1,000"}, {"note_id": "note", "content": "fourth", "like_count": "bad"}])
        self.assertEqual(xhs_comments_from_jsonl(self.post, data_dir=self.root), ["first", "second", "third"])

    def test_missing_directory_and_note_id(self):
        """不存在的目录和缺失笔记标识均返回空列表。"""
        self.assertEqual(xhs_comments_from_jsonl(self.post, data_dir=self.root / "missing"), [])
        self.post.extra = {}
        self.assertEqual(xhs_comments_from_jsonl(self.post, data_dir=self.root), [])


if __name__ == "__main__":
    unittest.main()
