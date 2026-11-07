"""CyberField 数据清洗模块：清洗采集到的帖子数据。

流程：读取 CSV -> 删除空文本 -> 按 platform + source_url 去重
     -> 按发布时间升序排序 -> 保存结果。
仅处理本地文件，不访问网络。

本模块提供两个层次：
- clean_dataframe(df)   ：纯函数，只清洗 DataFrame，不碰文件（便于单元测试）
- clean_posts(in, out)  ：文件级入口，读 CSV -> 清洗 -> 写 CSV（命令行使用）
"""

import sys  # 用于设置控制台输出编码，让中文在 Windows 下正常显示
from pathlib import Path  # 跨平台安全地拼接、处理文件路径

import pandas as pd  # pandas：处理表格数据（DataFrame）的核心工具

# BASE_DIR：当前文件所在的项目目录。
# 通过 __file__（本文件路径）.parent（上一级目录）得到，
# 这样无论从哪里运行本程序，都能准确找到项目里的数据文件。
BASE_DIR = Path(__file__).resolve().parent


def clean_dataframe(df):
    """清洗帖子 DataFrame，返回 (清洗后的 DataFrame, 统计字典)。

    清洗规则（与原有业务一致，未做任何扩展）：
        1. 删除空文本（strip 后为空也算空）；
        2. 按 platform + source_url 原值去重，保留首次出现的记录；
        3. 按 published_at 升序排序。

    参数：
        df : 含 platform / text / published_at / source_url 列的 DataFrame
    返回：
        (cleaned_df, stats)
        cleaned_df : 清洗后的 DataFrame
        stats      : {"total", "empty_removed", "dup_removed", "final"}
    """
    total_count = len(df)  # 记录原始行数，供后面统计使用
    df = df.copy()  # 复制一份，避免改动调用方传入的原始数据

    # ---- 第 1 步：删除空文本 ----
    # 注意：NaN != "" 在 pandas 里结果为 True，所以真正的缺失值
    # （None / NaN / pd.NA）如果不处理会被当成"非空"而保留。
    # 先 fillna("") 把缺失值统一填成空字符串，再转字符串并 strip 首尾空白，
    # 这样"空字符串 / 全空格 / 缺失值"三类都会被识别为空文本。
    df["text"] = df["text"].fillna("").astype(str).str.strip()
    # 布尔索引：逐行判断 text 是否不等于 ""，只保留 True 的行（即去掉空文本）。
    df = df[df["text"] != ""]
    empty_removed = total_count - len(df)  # 原始数 - 剩余数 = 删掉的空文本数

    # ---- 第 2 步：按 platform + source_url 去重 ----
    before_dedup = len(df)
    # subset：只依据这两列判断重复；keep="first"：重复时保留第一次出现的记录。
    df = df.drop_duplicates(subset=["platform", "source_url"], keep="first")
    dup_removed = before_dedup - len(df)  # 去重前行数 - 去重后行数 = 去重数量

    # ---- 第 3 步：按发布时间升序排序 ----
    # 先把"看起来像时间"的文字转成真正的日期时间类型，才能正确比较先后。
    df["published_at"] = pd.to_datetime(df["published_at"])
    # sort_values：按该列升序排序；reset_index 让行号重新从 0 连续编号。
    df = df.sort_values("published_at").reset_index(drop=True)

    # 把统计结果打包成字典返回，供主函数打印或测试程序校验。
    stats = {
        "total": total_count,
        "empty_removed": empty_removed,
        "dup_removed": dup_removed,
        "final": len(df),
    }
    return df, stats


def clean_posts(input_path, output_path):
    """清洗帖子 CSV 文件，返回包含各环节统计数量的字典（接口保持不变）。

    参数：
        input_path  : 原始 CSV 文件路径
        output_path : 清洗后 CSV 的保存路径
    返回：
        字典 {"total", "empty_removed", "dup_removed", "final"}
    """
    # ---- 读取原始数据 ----
    # keep_default_na=False：让空单元格读入为 ""（空字符串）而不是 NaN，
    # 这样后面判断"是否为空"更直观可控。
    # dtype=str：所有列按文本读入，避免时间等字段被自动转成其他类型。
    # encoding="utf-8-sig"：兼容带 BOM 标记的中文 CSV 文件。
    try:
        df = pd.read_csv(input_path, dtype=str, keep_default_na=False,
                         encoding="utf-8-sig")
    except pd.errors.EmptyDataError:
        # 友好处理：完全空白文件（0 字节或仅有 BOM）没有可读数据。
        # 打印清晰的中文提示，并按"0 条帖子"继续，不让程序崩溃。
        print(f"警告：输入文件 {input_path} 是空的，"
              "没有可清洗的数据，已按空数据处理。")
        df = pd.DataFrame(columns=["platform", "text",
                                   "published_at", "source_url"])

    # 清洗逻辑统一交给 clean_dataframe 处理（保持单一职责）。
    cleaned_df, stats = clean_dataframe(df)

    # ---- 保存结果 ----
    # index=False：不把行号写进文件；编码与读取时保持一致。
    cleaned_df.to_csv(output_path, index=False, encoding="utf-8-sig")

    return stats


def main():
    # 让 print 输出的中文在 Windows 控制台正常显示（解决乱码问题）。
    sys.stdout.reconfigure(encoding="utf-8")
    # 调用清洗函数：读 data/sample_posts.csv，清洗结果存到 data/cleaned_posts.csv。
    stats = clean_posts(BASE_DIR / "data" / "sample_posts.csv",
                        BASE_DIR / "data" / "cleaned_posts.csv")
    # f-string：把字典里的统计数字直接嵌进字符串打印。
    print(f"原始数量：{stats['total']}")
    print(f"删除空文本数量：{stats['empty_removed']}")
    print(f"去重数量：{stats['dup_removed']}")
    print(f"最终数量：{stats['final']}")
    print("已保存：cleaned_posts.csv")


# 只有直接运行本文件时才执行 main()；
# 被其他文件 import 借用函数时不会自动执行（例如测试文件只用 clean_posts）。
if __name__ == "__main__":
    main()
