"""clean_posts / clean_dataframe 的测试。

运行方式：python test_clean_posts.py
不依赖 pytest、不依赖项目里的 sample_posts.csv；测试数据全部自行构造。

覆盖内容：
  1. clean_dataframe 单元测试：正常清洗 / 全空文本 / 全部重复 / 带列名零行
  2. clean_posts 的 CSV 读写集成测试（使用临时目录，不污染项目）

注：完全空白文件（0 字节）当前会抛 pandas EmptyDataError，属现有行为，
本测试未覆盖，详见修改说明。
"""

import shutil  # 用于删除临时目录
import sys  # 用于设置控制台编码（让中文正常显示）
import tempfile  # 用于创建临时目录
from pathlib import Path  # 跨平台处理文件路径

import pandas as pd  # 构造测试数据、读取结果文件

# 借用清洗函数；注意不会触发 clean_posts.py 里的 main()。
from clean_posts import clean_posts, clean_dataframe

# 统一的数据列名（与 sample_posts.csv 保持一致）。
COLUMNS = ["platform", "text", "published_at", "source_url"]


def make_df(rows):
    """把"行数据列表"转成带统一列名的 DataFrame。"""
    return pd.DataFrame(rows, columns=COLUMNS)


def test_normal_cleaning():
    """正常清洗：空文本、重复、乱序同时存在。"""
    rows = [
        ["微博", "第一", "2024-05-02 10:00:00", "https://a.example.com/1"],
        ["知乎", "第二", "2024-05-01 09:00:00", "https://b.example.com/2"],
        # 与上一行 platform + source_url 相同 -> 应被去重
        ["知乎", "第二（转载）", "2024-05-03 11:00:00", "https://b.example.com/2"],
        # 全空格文本 -> 应被当作空文本删除
        ["微博", "   ", "2024-05-04 12:00:00", "https://c.example.com/3"],
        ["知乎", "第三", "2024-05-05 13:00:00", "https://d.example.com/4"],
    ]
    cleaned, stats = clean_dataframe(make_df(rows))

    # 统计数字：5 -> 删 1 空 -> 去 1 重复 -> 剩 3
    assert stats["total"] == 5, f"原始数量应为 5，实际为 {stats['total']}"
    assert stats["empty_removed"] == 1, f"删空应为 1，实际为 {stats['empty_removed']}"
    assert stats["dup_removed"] == 1, f"去重应为 1，实际为 {stats['dup_removed']}"
    assert stats["final"] == 3, f"最终应为 3，实际为 {stats['final']}"

    # 结果内容：无空文本、无重复、时间升序
    assert (cleaned["text"].str.strip() != "").all(), "结果中仍存在空文本"
    assert not cleaned.duplicated(subset=["platform", "source_url"]).any(), \
        "结果中仍存在重复"
    times = pd.to_datetime(cleaned["published_at"])
    assert times.is_monotonic_increasing, "结果未按发布时间升序"
    assert len(cleaned) == 3

    # 重复记录应保留首次出现的"第二"，而不是"第二（转载）"
    assert not (cleaned["text"] == "第二（转载）").any(), "重复应保留首次出现"
    return "正常清洗"


def test_all_empty_text():
    """全空文本：所有行 text 为空（含全空格），应全部被删除。"""
    rows = [
        ["微博", "", "2024-05-01 08:00:00", "https://a.example.com/1"],
        ["知乎", " ", "2024-05-02 09:00:00", "https://b.example.com/2"],
        ["小红书", "  ", "2024-05-03 10:00:00", "https://c.example.com/3"],
    ]
    cleaned, stats = clean_dataframe(make_df(rows))

    assert stats["total"] == 3, f"原始数量应为 3，实际为 {stats['total']}"
    assert stats["empty_removed"] == 3, f"删空应为 3，实际为 {stats['empty_removed']}"
    assert stats["dup_removed"] == 0, f"去重应为 0，实际为 {stats['dup_removed']}"
    assert stats["final"] == 0, f"最终应为 0，实际为 {stats['final']}"
    assert len(cleaned) == 0, "清洗后应为空表"
    return "全空文本"


def test_all_duplicated():
    """全部重复：所有行 platform + source_url 相同，应只剩首次出现的 1 行。"""
    rows = [
        ["微博", "甲", "2024-05-01 08:00:00", "https://a.example.com/1"],
        ["微博", "乙", "2024-05-02 09:00:00", "https://a.example.com/1"],
        ["微博", "丙", "2024-05-03 10:00:00", "https://a.example.com/1"],
    ]
    cleaned, stats = clean_dataframe(make_df(rows))

    assert stats["total"] == 3, f"原始数量应为 3，实际为 {stats['total']}"
    assert stats["empty_removed"] == 0, f"删空应为 0，实际为 {stats['empty_removed']}"
    assert stats["dup_removed"] == 2, f"去重应为 2，实际为 {stats['dup_removed']}"
    assert stats["final"] == 1, f"最终应为 1，实际为 {stats['final']}"
    assert len(cleaned) == 1
    assert cleaned.iloc[0]["text"] == "甲", "应保留首次出现的记录"
    return "全部重复"


def test_missing_text():
    """真正缺失值（None / NaN / pd.NA）：应全部作为空文本删除。"""
    rows = [
        ["微博", "正常", "2024-05-01 08:00:00", "https://a.example.com/1"],
        ["知乎", None, "2024-05-02 09:00:00", "https://b.example.com/2"],
        ["小红书", pd.NA, "2024-05-03 10:00:00", "https://c.example.com/3"],
        ["微博", float("nan"), "2024-05-04 11:00:00", "https://d.example.com/4"],
        ["知乎", "保留", "2024-05-05 12:00:00", "https://e.example.com/5"],
    ]
    cleaned, stats = clean_dataframe(make_df(rows))

    assert stats["total"] == 5, f"原始数量应为 5，实际为 {stats['total']}"
    assert stats["empty_removed"] == 3, f"删空应为 3，实际为 {stats['empty_removed']}"
    assert stats["dup_removed"] == 0, f"去重应为 0，实际为 {stats['dup_removed']}"
    assert stats["final"] == 2, f"最终应为 2，实际为 {stats['final']}"
    assert len(cleaned) == 2, "缺失值行应被删除，只剩 2 行"
    # 只有两条正常文本被保留
    assert "正常" in cleaned["text"].tolist(), "应保留正常文本"
    assert "保留" in cleaned["text"].tolist(), "应保留正常文本"
    return "缺失值删除"


def test_empty_header_only():
    """带列名零行：只有列名没有数据行，应正常返回全 0 统计、不报错。"""
    df = pd.DataFrame(columns=COLUMNS)
    cleaned, stats = clean_dataframe(df)

    assert stats == {"total": 0, "empty_removed": 0, "dup_removed": 0, "final": 0}, \
        f"零行统计应为全 0，实际为 {stats}"
    assert len(cleaned) == 0, "清洗后应为空表"
    assert list(cleaned.columns) == COLUMNS, "零行输入应保留列结构"
    return "带列名零行"


def test_csv_integration():
    """集成测试：真实 CSV 读写链路（读文件 -> 清洗 -> 写文件 -> 读回核对）。"""
    tmp_dir = Path(tempfile.mkdtemp(prefix="cyberfield_test_"))
    try:
        input_path = tmp_dir / "input.csv"
        output_path = tmp_dir / "output.csv"
        # 测试自造输入 CSV（不依赖项目里的 sample_posts.csv）
        input_path.write_text(
            "platform,text,published_at,source_url\n"
            "微博,第一,2024-05-02 10:00:00,https://a.example.com/1\n"
            "知乎,第二,2024-05-01 09:00:00,https://b.example.com/2\n"
            "知乎,第二（转载）,2024-05-03 11:00:00,https://b.example.com/2\n"
            "微博,,2024-05-04 12:00:00,https://c.example.com/3\n",
            encoding="utf-8",
        )

        stats = clean_posts(input_path, output_path)
        assert stats["total"] == 4, f"原始数量应为 4，实际为 {stats['total']}"
        assert stats["empty_removed"] == 1, f"删空应为 1，实际为 {stats['empty_removed']}"
        assert stats["dup_removed"] == 1, f"去重应为 1，实际为 {stats['dup_removed']}"
        assert stats["final"] == 2, f"最终应为 2，实际为 {stats['final']}"

        # 读回输出文件，核对实际内容
        out = pd.read_csv(output_path, dtype=str, keep_default_na=False,
                          encoding="utf-8-sig")
        assert list(out.columns) == COLUMNS, \
            f"输出列应为 {COLUMNS}，实际为 {list(out.columns)}"
        assert len(out) == 2, f"输出行数应为 2，实际为 {len(out)}"
        assert (out["text"].str.strip() != "").all(), "输出中仍存在空文本"
        assert not out.duplicated(subset=["platform", "source_url"]).any(), \
            "输出中仍存在重复"
        times = pd.to_datetime(out["published_at"])
        assert times.is_monotonic_increasing, "输出未按时间升序"
        # 内容核对：保留首次出现的"第二"，空文本行被删除
        assert "第二（转载）" not in out["text"].tolist(), "不应保留重复记录"
        assert "第一" in out["text"].tolist(), "应包含第一"
        assert "第二" in out["text"].tolist(), "应包含第二（首次出现）"
        return "CSV 读写集成"
    finally:
        # 无论测试成功还是失败，都清理掉临时文件夹。
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_empty_file_friendly():
    """完全空白文件（0 字节）：应友好处理，不崩溃，返回全 0 并写出表头文件。"""
    tmp_dir = Path(tempfile.mkdtemp(prefix="cyberfield_test_"))
    try:
        input_path = tmp_dir / "blank.csv"
        input_path.write_bytes(b"")  # 0 字节文件
        output_path = tmp_dir / "out.csv"
        stats = clean_posts(input_path, output_path)
        assert stats == {"total": 0, "empty_removed": 0, "dup_removed": 0, "final": 0}, \
            f"空文件统计应为全 0，实际为 {stats}"
        # 输出文件应存在且仅含表头
        out = pd.read_csv(output_path, dtype=str, keep_default_na=False,
                          encoding="utf-8-sig")
        assert len(out) == 0, "空文件输出应为 0 行"
        assert list(out.columns) == COLUMNS, \
            f"输出列应为 {COLUMNS}，实际为 {list(out.columns)}"
        return "空文件友好处理"
    finally:
        # 无论测试成功还是失败，都清理掉临时文件夹。
        shutil.rmtree(tmp_dir, ignore_errors=True)


def run_all():
    """依次运行所有用例，逐个报告结果。"""
    cases = [
        test_normal_cleaning,
        test_all_empty_text,
        test_missing_text,
        test_all_duplicated,
        test_empty_header_only,
        test_csv_integration,
        test_empty_file_friendly,
    ]
    for fn in cases:
        name = fn()
        print(f"[通过] {name}")
    print("全部断言通过 ✓")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # 中文显示兼容
    run_all()
