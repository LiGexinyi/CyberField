"""数据契约与旧库兼容回归：临时目录位于项目内，不访问真实平台。"""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from collect import store
from collect.post import Post
from collect.time_utils import normalize_time
from collect.sources.douban_source import DoubanApiSource
from collect.sources.mediacrawler_source import MediaCrawlerSource

class DataTests(unittest.TestCase):
    """验证时间、条目语义、历史隔离及快照持久化。"""
    def setUp(self):
        """创建独立临时库，避免接触真实数据库。"""
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.root = Path(self.temp.name)
        self.db = self.root / "test.db"
    def tearDown(self):
        """删除本测试拥有的临时样例。"""
        self.temp.cleanup()
    def post(self, **changes):
        """生成完整的虚构帖子。"""
        fields = dict(platform="wb",title="100%",text="text",url="https://example.org/1",author="name",published_at="2026-11-08T00:00:00Z",source_adapter="fake",extra={"liked":3})
        fields.update(changes)
        return Post(**fields)
    def test_timestamps(self):
        """秒、毫秒、ISO时区和RFC时间对应同一瞬间。"""
        expected = "2023-11-15 06:13:20"
        for value in [1700000000,1700000000000,"2023-11-14T22:13:20Z","Wed, 15 Nov 2023 06:13:20 +0800"]:
            self.assertEqual(normalize_time(value), expected)
        for value in ["2026","yesterday","2026-02-30",None]:
            self.assertEqual(normalize_time(value), "")
    def test_catalog(self):
        """上映年和导演不作为帖子发布时间与作者。"""
        p=DoubanApiSource()._to_post({"target":{"id":1,"title":"movie","year":"2022","card_subtitle":"中国 / 剧情 / 导演"}},"x")
        self.assertEqual((p.author,p.published_at,p.record_type),("","","catalog_item"))
        self.assertEqual(p.extra["year"],"2022")
    def test_snapshots_and_keywords(self):
        """重复入库保留两份指标和两个搜索关键词。"""
        store.save_posts([self.post(keyword="first")],self.db)
        result=store.save_posts([self.post(keyword="second",extra={"liked":8})],self.db)
        self.assertEqual(result,{"inserted":0,"skipped":1})
        row=store.export_rows(self.db)[0]
        self.assertEqual([o["extra"]["liked"] for o in row["observations"]],[3,8])
        self.assertEqual(row["extra"]["liked"],8)
        self.assertEqual(len(store.query_posts(keyword="second",db_path=self.db)),1)
        self.assertEqual(len(store.query_posts(keyword="%",db_path=self.db)),1)
        self.assertEqual(len(store.query_posts(keyword="_",db_path=self.db)),0)
    def test_readonly_missing(self):
        """读取不存在的数据库不能生成空文件。"""
        self.assertEqual(store.export_rows(self.db),[])
        self.assertFalse(self.db.exists())
    def test_legacy_readonly(self):
        """旧豆瓣原值保留，分析视图剔除错误日期且不改库文件。"""
        conn=sqlite3.connect(self.db)
        conn.executescript(store._SCHEMA)
        conn.execute("INSERT INTO collected_posts(platform,url,author,published_at,source_adapter) VALUES ('douban','u','director','2022-01-01 00:00:00','douban_api')")
        conn.commit();conn.close()
        before=self.db.read_bytes()
        row=store.export_rows(self.db)[0]
        self.assertEqual(row["published_at"],"")
        self.assertEqual(row["extra"]["legacy_author"],"director")
        self.assertEqual(store.stats(self.db)["top_authors"],[])
        self.assertEqual(before,self.db.read_bytes())
        store.save_posts([self.post()],self.db)
        self.assertEqual(len(store.export_rows(self.db)),2)
    def test_atomic_metadata(self):
        """不可序列化元数据不能留下半批记录。"""
        with self.assertRaises(TypeError):
            store.save_posts([self.post(),self.post(url="other",extra={"bad":set()})],self.db)
        self.assertEqual(store.export_rows(self.db),[])
    def test_mc_fresh_only(self):
        """模拟追加 JSONL，仅返回本次新增，跳过非对象行。"""
        folder=self.root/"data/xhs/jsonl";folder.mkdir(parents=True)
        path=folder/"search_contents_test.jsonl"
        record={"source_keyword":"x","desc":"old","note_url":"old"}
        path.write_text(json.dumps(record)+"\n[]\n",encoding="utf-8")
        src=MediaCrawlerSource(mc_dir=str(self.root))
        def run(*args):
            """模拟外部工具成功追加记录。"""
            with path.open("a",encoding="utf-8") as f:
                f.write(json.dumps(dict(record,desc="new",note_url="new"))+"\n")
            return SimpleNamespace(returncode=0)
        with patch.object(src,"_run",side_effect=run):
            rows=src.search("x",limit=1)
        self.assertEqual([r.url for r in rows],["new"])
        with patch.object(src,"_run",return_value=SimpleNamespace(returncode=0)):
            self.assertEqual(src.search("x"),[])
    def test_mc_duplicate_observation(self):
        """追加与历史内容相同的行仍保留为新一次观察。"""
        src=MediaCrawlerSource(mc_dir=str(self.root));p=self.post()
        with patch.object(src,"load_results",side_effect=[[p],[p,p]]),patch.object(src,"_run",return_value=SimpleNamespace(returncode=0)):
            self.assertEqual(len(src.search("x")),1)

if __name__ == "__main__":
    unittest.main()
