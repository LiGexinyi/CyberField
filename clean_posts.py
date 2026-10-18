"""CyberField 数据清洗模块：清洗采集到的帖子 CSV。

流程：读取 CSV -> 删除空文本 -> 按 platform + source_url 去重
     -> 按发布时间升序排序 -> 保存结果。
仅处理本地文件，不访问网络。
"""

import sys
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent


def clean_posts(input_path, output_path):
    """清洗帖子 CSV，返回包含各环节统计数量的字典。"""
    # keep_default_na=False：空文本读入为空字符串而非 NaN，行为更可控
    df = pd.read_csv(input_path, dtype=str, keep_default_na=False,
                     encoding="utf-8-sig")

    total_count = len(df)

    # 1. 删除空文本（仅含空白字符也视为空）
    df["text"] = df["text"].str.strip()
    df = df[df["text"] != ""]
    empty_removed = total_count - len(df)

    # 2. 按 platform + source_url 去重，保留首次出现的记录
    before_dedup = len(df)
    df = df.drop_duplicates(subset=["platform", "source_url"], keep="first")
    dup_removed = before_dedup - len(df)

    # 3. 按发布时间升序排序
    df["published_at"] = pd.to_datetime(df["published_at"])
    df = df.sort_values("published_at").reset_index(drop=True)

    df.to_csv(output_path, index=False, encoding="utf-8-sig")

    return {
        "total": total_count,
        "empty_removed": empty_removed,
        "dup_removed": dup_removed,
        "final": len(df),
    }


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # 兼容 Windows 中文控制台
    stats = clean_posts(BASE_DIR / "sample_posts.csv",
                        BASE_DIR / "cleaned_posts.csv")
    print(f"原始数量：{stats['total']}")
    print(f"删除空文本数量：{stats['empty_removed']}")
    print(f"去重数量：{stats['dup_removed']}")
    print(f"最终数量：{stats['final']}")
    print("已保存：cleaned_posts.csv")


if __name__ == "__main__":
    main()
