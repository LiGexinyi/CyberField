"""clean_posts 的简单测试：在临时目录中运行清洗流程并断言结果。

运行方式：python test_clean_posts.py
（不依赖 pytest，仅用标准库 + pandas；输出写入临时目录，不污染项目）
"""

import shutil
import sys
import tempfile
from pathlib import Path

import pandas as pd

from clean_posts import clean_posts

BASE_DIR = Path(__file__).resolve().parent


def test_clean_posts():
    tmp_dir = Path(tempfile.mkdtemp(prefix="cyberfield_test_"))
    try:
        output_path = tmp_dir / "cleaned_posts.csv"
        stats = clean_posts(BASE_DIR / "sample_posts.csv", output_path)

        # 1. 各环节数量符合预期：8 -> 删 1 条空文本 -> 去 1 条重复 -> 剩 6
        assert stats["total"] == 8, f"原始数量应为 8，实际为 {stats['total']}"
        assert stats["empty_removed"] == 1, \
            f"删除空文本数量应为 1，实际为 {stats['empty_removed']}"
        assert stats["dup_removed"] == 1, \
            f"去重数量应为 1，实际为 {stats['dup_removed']}"
        assert stats["final"] == 6, f"最终数量应为 6，实际为 {stats['final']}"

        df = pd.read_csv(output_path, dtype=str, keep_default_na=False,
                         encoding="utf-8-sig")

        # 2. 结果中不存在空文本
        assert (df["text"].str.strip() != "").all(), "结果中仍存在空文本"

        # 3. 结果中不存在 platform + source_url 重复
        assert not df.duplicated(subset=["platform", "source_url"]).any(), \
            "结果中仍存在重复链接"

        # 4. 结果按发布时间升序排列
        times = pd.to_datetime(df["published_at"])
        assert times.is_monotonic_increasing, "结果未按发布时间升序排列"

        # 5. 重复链接保留的是首次出现的那条（不含“转载补充版”）
        dup = df[df["source_url"] == "https://zhihu.example.com/question/3003"]
        assert len(dup) == 1, "重复链接应只保留一条"
        assert "转载补充版" not in dup.iloc[0]["text"], \
            "应保留首次出现的记录"

        print("所有断言通过 ✓")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # 兼容 Windows 中文控制台
    test_clean_posts()
