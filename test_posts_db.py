"""posts_db 的 SQLite 存储与关键词查询测试。

运行方式：python test_posts_db.py
不依赖 pytest、不依赖项目里的 cleaned_posts.csv / sample_posts.csv；
测试数据全部自行构造，数据库使用临时目录中的临时文件，运行后自动清理。

覆盖内容：
  1. import_posts：首次导入新增数 / 重复导入新增 0 / 相同链接不同平台分别保存
  2. search_posts：关键词命中与时间升序 / 无匹配空列表 / 空与纯空白关键词报错
  3. 特殊字符：单引号、% 、_ 按普通字符处理（不会被 LIKE 通配符误伤）
  4. 非法输入整批拒绝：缺列 / 必要字段为空 / 非法时间，不留部分记录
  5. 边界行为：导入自动创建父目录 / 查询不存在的库报错且不创建文件 /
     空文件与仅表头文件
"""

import shutil  # 用于删除临时目录
import sys  # 用于设置控制台编码（让中文正常显示）
import sqlite3  # 查询数据库行数做核对
import tempfile  # 用于创建临时目录
from pathlib import Path  # 跨平台处理文件路径

import pandas as pd  # 构造测试 CSV

# 借用数据库模块；注意不会触发 posts_db.py 里的 main()。
from posts_db import import_posts, search_posts

# 统一的数据列名（与清洗模块输出保持一致）。
COLUMNS = ["platform", "text", "published_at", "source_url"]


def write_csv(path, rows):
    """把"行数据列表"写成带统一列名的 CSV（utf-8-sig，与项目读取约定一致）。"""
    df = pd.DataFrame(rows, columns=COLUMNS)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def count_rows(db_path):
    """读取数据库里的记录总数，用于核对导入结果。"""
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    finally:
        conn.close()


def test_first_import():
    """首次导入 6 条清洗结果：新增 6 条，总数 6。"""
    tmp = Path(tempfile.mkdtemp(prefix="cyberfield_db_test_"))
    try:
        rows = [
            ["微博", "牛来！这个梗也太上头了吧", "2024-05-03 08:30:00",
             "https://weibo.example.com/p/1001"],
            ["小红书", "放生前额叶是什么梗？评论区笑不活了", "2024-05-01 21:15:00",
             "https://xhs.example.com/note/2002"],
            ["知乎", "如何看待「奥德赛」一词突然走红网络？", "2024-05-02 10:05:00",
             "https://zhihu.example.com/question/3003"],
            ["微博", "奥德赛文学大赏正式开始", "2024-05-04 18:20:00",
             "https://weibo.example.com/p/1007"],
            ["小红书", "今日份快乐源泉：牛来梗图合集", "2024-05-05 09:40:00",
             "https://xhs.example.com/note/2006"],
            ["知乎", "从语言社会学角度看网络热梗的生命周期", "2024-05-06 14:00:00",
             "https://zhihu.example.com/question/3008"],
        ]
        csv_path = tmp / "six.csv"
        db_path = tmp / "posts.db"
        write_csv(csv_path, rows)

        inserted = import_posts(csv_path, db_path)
        assert inserted == 6, f"首次导入应新增 6 条，实际为 {inserted}"
        assert count_rows(db_path) == 6, "库中记录总数应为 6"
        return "首次导入新增全部记录"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_reimport_no_change():
    """再次导入同一批数据：新增 0，总数不变，且不覆盖已有内容。"""
    tmp = Path(tempfile.mkdtemp(prefix="cyberfield_db_test_"))
    try:
        rows = [
            ["微博", "第一条", "2024-05-01 08:00:00", "https://a.example.com/1"],
            ["知乎", "第二条", "2024-05-02 09:00:00", "https://b.example.com/2"],
        ]
        csv_path = tmp / "input.csv"
        db_path = tmp / "posts.db"
        write_csv(csv_path, rows)

        # 首次导入 2 条
        assert import_posts(csv_path, db_path) == 2
        # 再次导入同一批（内容不变）-> 0 新增
        assert import_posts(csv_path, db_path) == 0, "重复导入应新增 0"
        assert count_rows(db_path) == 2, "重复导入后总数应仍为 2"

        # 修改 text 再导入：因 platform + source_url 相同，应被忽略、不覆盖原内容
        changed = [["微博", "被篡改的文本", "2024-05-01 08:00:00",
                    "https://a.example.com/1"]]
        changed_csv = tmp / "changed.csv"
        write_csv(changed_csv, changed)
        assert import_posts(changed_csv, db_path) == 0, "同键记录应被忽略"
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.execute("SELECT text FROM posts WHERE source_url = ?",
                               ("https://a.example.com/1",))
            assert cur.fetchone()[0] == "第一条", "已有内容不应被覆盖"
        finally:
            conn.close()
        return "重复导入不增加不覆盖"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_same_url_different_platform():
    """相同来源链接、不同平台的记录可以分别保存。"""
    tmp = Path(tempfile.mkdtemp(prefix="cyberfield_db_test_"))
    try:
        rows = [
            ["微博", "微博版本", "2024-05-01 08:00:00", "https://same.example.com/x"],
            ["小红书", "小红书版本", "2024-05-02 09:00:00", "https://same.example.com/x"],
        ]
        csv_path = tmp / "input.csv"
        db_path = tmp / "posts.db"
        write_csv(csv_path, rows)

        assert import_posts(csv_path, db_path) == 2, "不同平台应各存一条"
        assert count_rows(db_path) == 2
        platforms = {r["platform"] for r in search_posts(db_path, "版本")}
        assert platforms == {"微博", "小红书"}, f"两个平台都应被保存，实际 {platforms}"
        return "相同链接不同平台分别保存"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_search_order():
    """关键词查询：命中多条时按发布时间升序返回。"""
    tmp = Path(tempfile.mkdtemp(prefix="cyberfield_db_test_"))
    try:
        rows = [
            ["微博", "奥德赛文学大赏正式开始", "2024-05-04 18:20:00",
             "https://weibo.example.com/p/1007"],
            ["知乎", "如何看待「奥德赛」一词突然走红网络？", "2024-05-02 10:05:00",
             "https://zhihu.example.com/question/3003"],
            ["小红书", "今日份快乐源泉：牛来梗图合集", "2024-05-05 09:40:00",
             "https://xhs.example.com/note/2006"],
        ]
        csv_path = tmp / "input.csv"
        db_path = tmp / "posts.db"
        write_csv(csv_path, rows)
        import_posts(csv_path, db_path)

        results = search_posts(db_path, "奥德赛")
        assert len(results) == 2, f"应命中 2 条，实际 {len(results)}"
        times = [r["published_at"] for r in results]
        assert times == sorted(times), f"结果应按时间升序，实际 {times}"
        assert results[0]["source_url"] == "https://zhihu.example.com/question/3003", \
            "发布时间较早的知乎记录应排在前面"
        assert results[1]["source_url"] == "https://weibo.example.com/p/1007"
        # 返回结构应包含全部字段
        for key in ("id", "platform", "text", "published_at", "source_url"):
            assert key in results[0], f"返回记录缺少字段 {key}"
        return "关键词查询与时间升序"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_search_no_match():
    """无匹配关键词：返回空列表，不报错。"""
    tmp = Path(tempfile.mkdtemp(prefix="cyberfield_db_test_"))
    try:
        rows = [["微博", "牛来！这个梗也太上头了吧", "2024-05-03 08:30:00",
                 "https://a.example.com/1"]]
        csv_path = tmp / "input.csv"
        db_path = tmp / "posts.db"
        write_csv(csv_path, rows)
        import_posts(csv_path, db_path)

        assert search_posts(db_path, "根本不存在的梗") == [], "无匹配应返回空列表"
        return "无匹配返回空列表"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_search_blank_keyword():
    """空关键词或纯空白关键词：明确报错。"""
    tmp = Path(tempfile.mkdtemp(prefix="cyberfield_db_test_"))
    try:
        rows = [["微博", "第一条", "2024-05-01 08:00:00", "https://a.example.com/1"]]
        csv_path = tmp / "input.csv"
        db_path = tmp / "posts.db"
        write_csv(csv_path, rows)
        import_posts(csv_path, db_path)

        for bad in ("", "   ", "\t"):
            try:
                search_posts(db_path, bad)
                raise AssertionError(f"关键词 {bad!r} 应报错却未报错")
            except ValueError:
                pass  # 符合预期
        return "空/纯空白关键词报错"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_search_special_chars():
    """单引号、% 、_ 都按普通字符处理，不会被 LIKE 通配符误伤。"""
    tmp = Path(tempfile.mkdtemp(prefix="cyberfield_db_test_"))
    try:
        rows = [
            ["微博", "I'm 100% sure，这句有单引号和百分号", "2024-05-01 08:00:00",
             "https://a.example.com/1"],
            ["知乎", "under_score 下划线测试", "2024-05-02 09:00:00",
             "https://b.example.com/2"],
            ["小红书", "完全无关的普通内容", "2024-05-03 10:00:00",
             "https://c.example.com/3"],
        ]
        csv_path = tmp / "input.csv"
        db_path = tmp / "posts.db"
        write_csv(csv_path, rows)
        import_posts(csv_path, db_path)

        # 单引号：作为普通字符参与子串匹配
        results = search_posts(db_path, "'")
        assert len(results) == 1 and "I'm" in results[0]["text"], \
            "单引号应作为普通字符匹配"
        results = search_posts(db_path, "I'm")
        assert len(results) == 1, "含单引号的关键词应命中"

        # % ：若被当成通配符会命中全部 3 条；正确行为是只命中字面含 % 的那条
        results = search_posts(db_path, "%")
        assert len(results) == 1 and "%" in results[0]["text"], \
            "% 应作为普通字符匹配，而不是通配符"
        results = search_posts(db_path, "100%")
        assert len(results) == 1 and "100%" in results[0]["text"], "100% 应字面命中"

        # _ ：若被当成通配符会误伤其他文本；正确行为是只命中字面含 _ 的那条
        results = search_posts(db_path, "_")
        assert len(results) == 1 and "under_score" in results[0]["text"], \
            "_ 应作为普通字符匹配，而不是通配符"

        # 普通子串仍可命中
        assert len(search_posts(db_path, "普通内容")) == 1
        return "单引号/%/_ 普通字符处理"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_import_missing_column():
    """缺必要列：明确报错，且不创建数据库、不写入任何记录。"""
    tmp = Path(tempfile.mkdtemp(prefix="cyberfield_db_test_"))
    try:
        # 缺 text 列
        df = pd.DataFrame(
            [["微博", "2024-05-01 08:00:00", "https://a.example.com/1"]],
            columns=["platform", "published_at", "source_url"],
        )
        csv_path = tmp / "bad.csv"
        db_path = tmp / "posts.db"
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")

        try:
            import_posts(csv_path, db_path)
            raise AssertionError("缺列应报错却未报错")
        except ValueError:
            pass
        assert not db_path.exists(), "缺列报错后不应创建数据库文件"
        return "缺必要列整批拒绝"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_import_empty_field():
    """必要字段为空：整批拒绝，即使前面有合法记录也不写入部分数据。"""
    tmp = Path(tempfile.mkdtemp(prefix="cyberfield_db_test_"))
    try:
        rows = [
            ["微博", "合法记录", "2024-05-01 08:00:00", "https://a.example.com/1"],
            ["知乎", "   ", "2024-05-02 09:00:00", "https://b.example.com/2"],
        ]
        csv_path = tmp / "input.csv"
        db_path = tmp / "posts.db"
        write_csv(csv_path, rows)

        try:
            import_posts(csv_path, db_path)
            raise AssertionError("空字段应报错却未报错")
        except ValueError:
            pass
        assert not db_path.exists() or count_rows(db_path) == 0, \
            "整批拒绝时不应留下部分记录"
        return "空字段整批拒绝"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_import_invalid_time():
    """非法发布时间：整批拒绝，不留下部分记录。"""
    tmp = Path(tempfile.mkdtemp(prefix="cyberfield_db_test_"))
    try:
        rows = [
            ["微博", "合法记录", "2024-05-01 08:00:00", "https://a.example.com/1"],
            ["知乎", "另一条", "这不是时间", "https://b.example.com/2"],
        ]
        csv_path = tmp / "input.csv"
        db_path = tmp / "posts.db"
        write_csv(csv_path, rows)

        try:
            import_posts(csv_path, db_path)
            raise AssertionError("非法时间应报错却未报错")
        except ValueError:
            pass
        assert not db_path.exists() or count_rows(db_path) == 0, \
            "非法记录应整批拒绝，不得写入部分数据"
        return "非法时间整批拒绝"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_import_creates_parent_dir():
    """导入时自动创建数据库的父目录。"""
    tmp = Path(tempfile.mkdtemp(prefix="cyberfield_db_test_"))
    try:
        rows = [["微博", "第一条", "2024-05-01 08:00:00", "https://a.example.com/1"]]
        csv_path = tmp / "input.csv"
        db_path = tmp / "nested" / "deep" / "dir" / "posts.db"
        write_csv(csv_path, rows)

        assert import_posts(csv_path, db_path) == 1, "导入应成功"
        assert db_path.exists(), "数据库文件应已创建"
        assert db_path.parent.exists(), "父目录应被自动创建"
        return "导入自动创建父目录"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_search_missing_db():
    """查询不存在的数据库：明确报错，且不创建空数据库文件。"""
    tmp = Path(tempfile.mkdtemp(prefix="cyberfield_db_test_"))
    try:
        db_path = tmp / "not_there.db"
        try:
            search_posts(db_path, "任意关键词")
            raise AssertionError("查询不存在的库应报错却未报错")
        except FileNotFoundError:
            pass
        assert not db_path.exists(), "查询不应创建空数据库文件"
        return "查询不存在库报错且不创建文件"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_empty_csv_files():
    """空 CSV 文件报错；仅表头（零数据行）的 CSV 正常导入 0 条。"""
    tmp = Path(tempfile.mkdtemp(prefix="cyberfield_db_test_"))
    try:
        blank_path = tmp / "blank.csv"
        blank_path.write_bytes(b"")  # 0 字节文件
        db_path = tmp / "posts.db"
        try:
            import_posts(blank_path, db_path)
            raise AssertionError("空 CSV 应报错却未报错")
        except ValueError:
            pass
        assert not db_path.exists(), "空 CSV 报错后不应创建数据库文件"

        # 仅表头、零数据行 -> 新增 0，正常返回
        header_path = tmp / "header_only.csv"
        header_path.write_text("platform,text,published_at,source_url\n",
                               encoding="utf-8-sig")
        assert import_posts(header_path, db_path) == 0, "零行 CSV 应新增 0"
        return "空文件报错 / 仅表头导入 0 条"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_all():
    """依次运行所有用例，逐个报告结果。"""
    cases = [
        test_first_import,
        test_reimport_no_change,
        test_same_url_different_platform,
        test_search_order,
        test_search_no_match,
        test_search_blank_keyword,
        test_search_special_chars,
        test_import_missing_column,
        test_import_empty_field,
        test_import_invalid_time,
        test_import_creates_parent_dir,
        test_search_missing_db,
        test_empty_csv_files,
    ]
    for fn in cases:
        name = fn()
        print(f"[通过] {name}")
    print("全部断言通过 ✓")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # 中文显示兼容
    run_all()
