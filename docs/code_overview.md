# CyberField 项目代码全览

> 生成时间：2026-11-07
> 来源：D:\Projects\CyberField（主项目 + collect/ 多源采集框架）
> 用途：项目全部代码的整理归档，便于整体查看与评审

---

## 一、代码文件清单（12 个文件，共约 1638 行）

| 文件 | 行数 | 用途 | 验证状态 |
| --- | --- | --- | --- |
| `clean_posts.py` | 125 | 数据清洗：空文本/去重/时间排序 | ✅ 7 项测试通过 |
| `test_clean_posts.py` | 218 | clean_posts 的独立测试（不依赖样本数据） | ✅ 7/7 通过 |
| `posts_db.py` | 227 | SQLite 存储与关键词查询（自 cp2_B 合并） | ✅ 13 项测试通过 |
| `test_posts_db.py` | 400 | posts_db 的 13 项独立测试 | ✅ 13/13 通过 |
| `collect/__init__.py` | 14 | 采集模块说明与结构注释 | — |
| `collect/post.py` | 67 | 统一数据契约 Post + 平台名规范化 | ✅ 自测通过 |
| `collect/orchestrator.py` | 72 | 多源调度：调用→合并→去重→入库 | ✅ 自测通过 |
| `collect/store.py` | 130 | 采集库入库/查询/统计/导出 | ✅ 自测通过 |
| `collect/demo_cli.py` | 186 | 终端交互式 Demo（采集/浏览/统计/导出） | ✅ 全链路演示通过 |
| `collect/sources/__init__.py` | 17 | 适配器注册表（新源在此登记） | ✅ 自测通过 |
| `collect/sources/base_source.py` | 41 | BaseSource 抽象接口 + SourceUnavailable | ✅ 自测通过 |
| `collect/sources/mediacrawler_source.py` | 141 | MediaCrawler 适配器（子进程调用+JSONL解析） | ✅ 自测通过 |

**测试汇总：** 20/20 全部断言通过（posts_db 13 项 + clean_posts 7 项）。

## 二、模块架构

```
主项目（原有功能，未改动）
├── clean_posts.py ── CSV 清洗（空文本/去重/排序）
└── posts_db.py ──── SQLite 存储 + 关键词查询（4 字段 posts 表，独立于采集库）

collect/（增量新增，薄适配器层）
├── post.py ────────────────── 统一数据契约 Post
├── sources/base_source.py ─── BaseSource 接口 + SourceUnavailable 异常
├── sources/mediacrawler_source.py ─ MediaCrawler 适配器
├── sources/__init__.py ────── 适配器注册表（name -> 工厂）
├── orchestrator.py ────────── 多源调度 / 合并 / 去重 / 入库
├── store.py ───────────────── collect.db 的 collected_posts 表（9 字段）
└── demo_cli.py ────────────── 终端交互式 Demo 入口

数据流：
demo_cli / 任意调用 → orchestrator.collect(keyword)
    → 逐个源 search(keyword) → Post 列表
    → 按 (platform, url) 去重 → store.save_posts 入库
    → demo_cli 浏览 / 统计 / 导出
```

**设计要点：**
- 任一源失败（`SourceUnavailable`）→ 记录原因并跳过，其余源照常；
- 同一平台同一链接（`UNIQUE(platform, url)`）只存一份，多源冗余不会重复入库；
- 每条记录带 `source_adapter` 与 `keyword`，可追溯；
- 新增数据源只需：实现 `BaseSource` + 在注册表登记，旧源与上层入口不受影响；
- 采集库 `data/collect.db` 与主项目原 `posts.db`（posts 表）完全独立。

---

## 三、完整源码

### 1. `clean_posts.py`（125 行）

```python
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
```

### 2. `test_clean_posts.py`（218 行）

```python
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
```

### 3. `posts_db.py`（227 行，自 cp2_B 合并）

```python
"""CyberField SQLite 存储与关键词查询模块。

功能：
- import_posts(csv_path, db_path)：把清洗后的帖子 CSV 导入本地 SQLite 数据库，
  以 platform + source_url 作为唯一键；重复导入不增加记录、不覆盖已有内容，
  返回本次新增的记录数。
- search_posts(db_path, keyword)：按正文（text）字面子串匹配查询，
  返回按发布时间升序排列的记录列表。
- 命令行入口：支持指定 CSV 路径、数据库路径和查询关键词。

数据库操作只使用标准库 sqlite3，CSV 读取沿用 pandas（与清洗模块同一套读取约定），
不新增第三方依赖，不访问网络。所有 SQL 均使用参数绑定，不拼接用户输入。
"""

import argparse  # 解析命令行参数
import sqlite3  # 标准库 SQLite 驱动
import sys  # 设置控制台输出编码，让中文在 Windows 下正常显示
from contextlib import closing  # 确保数据库连接被正确关闭
from pathlib import Path  # 跨平台处理文件路径

import pandas as pd  # 读取 CSV（与 clean_posts.py 保持同一套读取约定）

# BASE_DIR：当前文件所在的项目目录，与 clean_posts.py 保持一致。
BASE_DIR = Path(__file__).resolve().parent

# 数据库必需的列名（与清洗模块输出的列一致）。
REQUIRED_COLUMNS = ["platform", "text", "published_at", "source_url"]


def _like_pattern(keyword):
    """把关键词转成 SQL LIKE 子串匹配模式，% 和 _ 按普通字符处理。

    在 SQL LIKE 里，% 表示任意多个字符、_ 表示任意单个字符，
    会误伤字面内容。这里先把关键词里的 \ % _ 三个字符加上转义前缀，
    再在前后各拼一个 % 表示"子串匹配"。
    """
    escaped = (
        keyword.replace("\\", "\\\\")  # 先转义反斜杠本身，避免它吃掉后面的转义符
        .replace("%", "\\%")  # 字面的 % -> \%
        .replace("_", "\\_")  # 字面的 _ -> \_
    )
    return f"%{escaped}%"  # 前后加 %，表示"包含关键词"的子串匹配


def import_posts(csv_path, db_path):
    """导入清洗后的帖子 CSV 到 SQLite 数据库，返回本次新增的记录数。

    参数：
        csv_path : 清洗后 CSV 文件路径（含 platform/text/published_at/source_url 列）
        db_path  : SQLite 数据库文件路径（父目录不存在时会自动创建）
    返回：
        新增记录数（int）。重复导入同一批数据时返回 0。
    抛出：
        FileNotFoundError : CSV 文件不存在
        ValueError        : CSV 为空 / 缺少必要列 / 必要字段为空 /
                            published_at 无法解析为时间（整批拒绝写入）
    """
    # ---- 第 1 步：读取 CSV（与 clean_posts.py 完全相同的读取约定） ----
    # keep_default_na=False：空单元格读成 "" 而不是 NaN；
    # dtype=str：所有列按文本读入；encoding="utf-8-sig"：兼容带 BOM 的中文 CSV。
    try:
        df = pd.read_csv(csv_path, dtype=str, keep_default_na=False,
                         encoding="utf-8-sig")
    except FileNotFoundError:
        raise FileNotFoundError(f"CSV 文件不存在：{csv_path}")
    except pd.errors.EmptyDataError:
        raise ValueError(f"CSV 文件 {csv_path} 是空的，没有任何数据可导入")

    # ---- 第 2 步：校验必要列是否齐全，缺列直接报错 ----
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(
            f"CSV 缺少必要列：{missing}，应有列：{REQUIRED_COLUMNS}，整批未导入"
        )

    # ---- 第 3 步：逐行校验"必要字段非空 + 时间可解析" ----
    # 校验全部在写入之前完成：只要有一行非法，就整批拒绝，不留下部分记录。
    rows = []
    for idx, rec in df.iterrows():
        # 数据已按文本读入，统一 strip 后再判断是否为空。
        platform = str(rec["platform"]).strip()
        text = str(rec["text"]).strip()
        published_at = str(rec["published_at"]).strip()
        source_url = str(rec["source_url"]).strip()

        # 任一必要字段为空（含全空白）都算非法记录，明确报错。
        if not platform or not text or not published_at or not source_url:
            raise ValueError(
                f"第 {idx + 2} 行缺少必要字段（platform/text/published_at/"
                f"source_url 均不能为空），整批未导入"
            )

        # published_at 必须能解析成时间，才能保证跨批次按时间排序正确。
        # 解析失败视为非法记录，整批拒绝。
        try:
            parsed = pd.to_datetime(published_at)
        except Exception:
            raise ValueError(
                f"第 {idx + 2} 行 published_at 无法解析为时间："
                f"{published_at!r}，整批未导入"
            )
        # 统一规范化为 "YYYY-MM-DD HH:MM:SS" 文本存储，
        # 该格式的字典序 == 时间先后顺序，方便查询直接 ORDER BY 文本。
        rows.append((platform, text,
                     parsed.strftime("%Y-%m-%d %H:%M:%S"), source_url))

    # ---- 第 4 步：建库、建表，并在一个事务里导入 ----
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)  # 自动创建数据库父目录

    # closing：确保无论成功还是异常，连接都会被关闭（连接本身不会自动关）。
    with closing(sqlite3.connect(db_path)) as conn:
        try:
            cur = conn.cursor()
            # 唯一约束 (platform, source_url)：同一平台同一链接只存一份。
            cur.execute(
                """CREATE TABLE IF NOT EXISTS posts (
                       id INTEGER PRIMARY KEY AUTOINCREMENT,
                       platform    TEXT NOT NULL,
                       text        TEXT NOT NULL,
                       published_at TEXT NOT NULL,
                       source_url  TEXT NOT NULL,
                       UNIQUE (platform, source_url)
                   )"""
            )
            # INSERT OR IGNORE：命中唯一约束时跳过该行（不增加、不覆盖），
            # 未冲突则插入。rowcount 为 1 表示新插入，0 表示重复被忽略。
            inserted = 0
            for row in rows:
                cur.execute(
                    "INSERT OR IGNORE INTO posts "
                    "(platform, text, published_at, source_url) "
                    "VALUES (?, ?, ?, ?)",
                    row,
                )
                inserted += cur.rowcount
            conn.commit()  # 全部成功才提交，保证"失败不留部分记录"
        except Exception:
            conn.rollback()  # 任何一步出错都回滚整个事务
            raise

    return inserted


def search_posts(db_path, keyword):
    """按正文（text）关键词做字面子串查询，返回记录列表。

    参数：
        db_path : SQLite 数据库文件路径（必须已存在，查询不会创建空数据库）
        keyword : 查询关键词（不能为空或纯空白；单引号、% 、_ 按普通字符处理）
    返回：
        记录列表，每个元素是包含 id/platform/text/published_at/source_url
        的字典，按发布时间升序排列；无匹配时返回空列表。
    抛出：
        TypeError        : keyword 不是字符串
        ValueError       : keyword 为空或纯空白
        FileNotFoundError : 数据库文件不存在
    """
    if not isinstance(keyword, str):
        raise TypeError("关键词必须是字符串")
    keyword_stripped = keyword.strip()
    if not keyword_stripped:
        raise ValueError("关键词不能为空或纯空白")

    db_path = Path(db_path)
    # 查询不存在的数据库时明确报错，绝不自动创建空数据库。
    if not db_path.exists():
        raise FileNotFoundError(
            f"数据库不存在：{db_path}（查询不会自动创建空数据库）"
        )

    pattern = _like_pattern(keyword_stripped)  # 转义后的 LIKE 模式

    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row  # 让查询结果可以按列名访问
        cur = conn.cursor()
        # ESCAPE '\\'：声明上面模式里的 \ 是转义符。
        # 关键词通过参数 (?,) 绑定，单引号无需转义，也不会产生注入。
        # ORDER BY published_at：时间已规范化为统一文本格式，字典序即时间序。
        cur.execute(
            "SELECT id, platform, text, published_at, source_url "
            "FROM posts "
            "WHERE text LIKE ? ESCAPE '\\' "
            "ORDER BY published_at ASC, id ASC",
            (pattern,),
        )
        return [dict(row) for row in cur.fetchall()]


def main():
    """命令行入口：--csv 导入、--keyword 查询，两者可以同时提供。"""
    # 让 print 输出的中文在 Windows 控制台正常显示（与清洗模块一致）。
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="CyberField 帖子 SQLite 导入与关键词查询"
    )
    parser.add_argument("--csv", help="清洗后的 CSV 文件路径（提供时执行导入）")
    parser.add_argument("--db", required=True, help="SQLite 数据库文件路径")
    parser.add_argument("--keyword", help="查询关键词（提供时执行查询）")
    args = parser.parse_args()

    # 至少需要 --csv 或 --keyword 之一，否则没有可执行的任务。
    if not args.csv and args.keyword is None:
        parser.error("请提供 --csv（导入）或 --keyword（查询），或同时提供两者")

    try:
        if args.csv:
            inserted = import_posts(args.csv, args.db)
            print(f"已导入 {inserted} 条记录 → {args.db}")

        if args.keyword is not None:
            results = search_posts(args.db, args.keyword)
            for rec in results:
                print(f"[{rec['id']}] {rec['platform']} | {rec['published_at']} "
                      f"| {rec['text']} | {rec['source_url']}")
            print(f"共 {len(results)} 条匹配结果")
    except (ValueError, TypeError, FileNotFoundError) as exc:
        # 业务类错误给出清晰的中文提示并以非零码退出，不打印冗长堆栈。
        print(f"错误：{exc}", file=sys.stderr)
        sys.exit(1)


# 只有直接运行本文件时才执行 main()；
# 被测试文件 import 借用函数时不会自动执行。
if __name__ == "__main__":
    main()
```

### 4. `test_posts_db.py`（400 行，13 项用例）

```python
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
```

### 5. `collect/__init__.py`（14 行）

```python
"""CyberField 多源采集模块。

设计：薄适配器层 + 统一数据契约（Post）。
每个数据源实现 BaseSource 接口（search(keyword) -> [Post]），
由 orchestrator 调度、store 统一入库；新增源不影响既有使用。

模块结构：
- post.py                  统一数据契约 Post 与平台名规范化
- sources/base_source.py   BaseSource 抽象接口 + 异常
- sources/mediacrawler_source.py  MediaCrawler 适配器
- orchestrator.py          多源调度 / 合并 / 去重
- store.py                 统一入库（collected_posts 表）与查询/统计
- demo_cli.py              终端交互式浏览试用入口
"""
```

### 6. `collect/post.py`（67 行）

```python
"""统一帖子数据契约（Post）与平台名规范化。

这是整个多源框架的核心约定：任何适配器产出的数据都必须转成 Post，
上层（调度、入库、统计、展示）只依赖这个结构，不关心具体源内部格式。
"""

from dataclasses import dataclass, field


# MediaCrawler 平台码 → 规范化平台名（后续新源也沿用同一套规范名）。
PLATFORM_NAME_MAP = {
    "xhs": "xiaohongshu",
    "bili": "bilibili",
    "wb": "weibo",
    "zhihu": "zhihu",
    "dy": "douyin",
    "ks": "kuaishou",
    "tieba": "tieba",
}

# 规范化平台名 → 人类可读中文名（用于展示）。
PLATFORM_LABELS = {
    "xiaohongshu": "小红书",
    "bilibili": "B站",
    "weibo": "微博",
    "zhihu": "知乎",
    "douyin": "抖音",
    "kuaishou": "快手",
    "tieba": "贴吧",
}


def normalize_platform(raw: str) -> str:
    """把各源的平台码统一成规范化平台名，未知原样返回。"""
    return PLATFORM_NAME_MAP.get(raw, raw)


def platform_label(name: str) -> str:
    """规范化平台名 → 中文标签，未知返回原名。"""
    return PLATFORM_LABELS.get(name, name)


@dataclass
class Post:
    """统一帖子记录。

    字段说明：
        platform      规范化平台名（xiaohongshu / bilibili / weibo / zhihu ...）
        title         帖子标题
        text          帖子正文 / 摘要
        url           原链接（溯源与去重依据）
        author        作者昵称（各源默认已脱敏）
        published_at  发布时间（尽量规范为 YYYY-MM-DD HH:MM:SS）
        source_adapter 数据来自哪个适配器（追溯来源）
        keyword       由哪个搜索关键词采到
        extra         平台附加数据（互动数等，统计时可选使用）
    """

    platform: str
    title: str
    text: str
    url: str
    author: str
    published_at: str
    source_adapter: str
    keyword: str = ""
    extra: dict = field(default_factory=dict)
```

### 7. `collect/orchestrator.py`（72 行）

```python
"""多源调度器：并行调所有启用源 → 合并 → 去重 → 入库。

容错约定：
- 单个源失败（SourceUnavailable）→ 记录原因、跳过该源，其余源照常；
- 结果按 (platform, url) 去重，保证"多源冗余"不会重复入库；
- 每条记录带 source_adapter 与 keyword，可追溯。
"""

import logging

from collect.sources.base_source import SourceUnavailable
from collect.sources import create_source

logger = logging.getLogger(__name__)


def collect(keyword: str,
            platforms: tuple = ("xhs",),
            limit: int = 20,
            source_names: tuple = ("mediacrawler",),
            source_kwargs: dict | None = None,
            save: bool = True):
    """执行一次多源采集。

    参数：
        keyword       搜索关键词
        platforms     MediaCrawler 平台码元组（xhs / bili / wb / zhihu ...）
        limit         每个平台最多采集条数
        source_names  启用的适配器名
        source_kwargs 传给适配器构造器的参数（如 mc_dir / mc_python）
        save          是否入库（默认入库）
    返回：
        (posts, errors, summary)
        posts  去重后的统一 Post 列表
        errors 各源失败原因列表
        summary 入库统计（save=False 时为 None）
    """
    errors: list[str] = []
    posts = []
    for name in source_names:
        try:
            src = create_source(name, **(source_kwargs or {}))
        except Exception as exc:  # 适配器构造失败，记录并跳过
            errors.append(f"{name}: 初始化失败 {exc}")
            continue
        if not src.health_check():
            errors.append(f"{name}: 健康检查失败（工具缺失或路径错误）")
            continue
        for platform in platforms:
            try:
                got = src.search(keyword, platform=platform, limit=limit)
                posts.extend(got)
                logger.info("[%s/%s] 命中 %d 条", src.name, platform, len(got))
            except SourceUnavailable as exc:
                errors.append(f"{src.name}/{platform}: {exc}")
            except Exception as exc:
                errors.append(f"{src.name}/{platform}: 意外异常 {exc}")

    # 按 (platform, url) 去重，保留首次出现。
    seen, uniq = set(), []
    for p in posts:
        key = (p.platform, p.url)
        if key not in seen:
            seen.add(key)
            uniq.append(p)

    summary = None
    if save and uniq:
        from collect import store
        summary = store.save_posts(uniq)

    return uniq, errors, summary
```

### 8. `collect/store.py`（130 行）

```python
"""统一采集入库与查询 / 统计。

与主项目原有 posts_db.py（4 字段的 posts 表）互不影响：
采集数据存入独立数据库 collect.db 的 collected_posts 表，
字段更全（标题 / 作者 / 关键词 / 来源适配器），支持后续分析扩展。
"""

import sqlite3
from pathlib import Path

# 采集库默认位置：项目根 data/collect.db（与清洗数据同目录；随代码增量新增，不触碰现有库）。
DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "collect.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS collected_posts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword        TEXT,                 -- 由哪个关键词采到
    platform       TEXT NOT NULL,        -- 规范化平台名
    title          TEXT,
    text           TEXT,
    url            TEXT,
    author         TEXT,
    published_at   TEXT,
    source_adapter TEXT,                 -- 数据来源适配器
    fetched_at     TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE (platform, url)               -- 同一平台同一链接只存一份
);
CREATE INDEX IF NOT EXISTS idx_cp_keyword      ON collected_posts (keyword);
CREATE INDEX IF NOT EXISTS idx_cp_platform     ON collected_posts (platform);
CREATE INDEX IF NOT EXISTS idx_cp_published_at ON collected_posts (published_at);
"""


def _connect(db_path: Path | str):
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    return conn


def save_posts(posts, db_path=DEFAULT_DB):
    """把统一 Post 列表幂等入库，返回 {"inserted":.., "skipped":..}。"""
    conn = _connect(db_path)
    try:
        inserted = skipped = 0
        for p in posts:
            cur = conn.execute(
                "INSERT OR IGNORE INTO collected_posts "
                "(keyword, platform, title, text, url, author, "
                " published_at, source_adapter) VALUES (?,?,?,?,?,?,?,?)",
                (p.keyword, p.platform, p.title, p.text, p.url,
                 p.author, p.published_at, p.source_adapter),
            )
            if cur.rowcount == 1:
                inserted += 1
            else:
                skipped += 1
        conn.commit()
        return {"inserted": inserted, "skipped": skipped}
    finally:
        conn.close()


def query_posts(keyword: str | None = None, platform: str | None = None,
                limit: int = 50, db_path=DEFAULT_DB):
    """按关键词 / 平台过滤查询，按发布时间排序，返回 dict 列表。"""
    conn = _connect(db_path)
    try:
        sql = ("SELECT keyword, platform, title, text, url, author, "
               "published_at, source_adapter, fetched_at "
               "FROM collected_posts WHERE 1=1")
        params: list = []
        if keyword:
            sql += " AND (keyword LIKE ? OR title LIKE ? OR text LIKE ?)"
            params += [f"%{keyword}%"] * 3
        if platform:
            sql += " AND platform = ?"
            params.append(platform)
        sql += " ORDER BY published_at DESC, id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        cols = ["keyword", "platform", "title", "text", "url", "author",
                "published_at", "source_adapter", "fetched_at"]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


def stats(db_path=DEFAULT_DB):
    """统计概览：总量 / 平台分布 / 关键词分布 / 作者 TOP / 互动合计。"""
    conn = _connect(db_path)
    try:
        total = conn.execute("SELECT COUNT(*) FROM collected_posts").fetchone()[0]
        by_platform = conn.execute(
            "SELECT platform, COUNT(*) c FROM collected_posts GROUP BY platform "
            "ORDER BY c DESC").fetchall()
        by_keyword = conn.execute(
            "SELECT COALESCE(NULLIF(keyword,''), '(未知)') k, COUNT(*) c "
            "FROM collected_posts GROUP BY k ORDER BY c DESC").fetchall()
        top_authors = conn.execute(
            "SELECT author, COUNT(*) c FROM collected_posts "
            "WHERE author != '' GROUP BY author ORDER BY c DESC LIMIT 10").fetchall()
        time_range = conn.execute(
            "SELECT MIN(published_at), MAX(published_at) "
            "FROM collected_posts WHERE published_at != ''").fetchone()
        return {
            "total": total,
            "by_platform": [dict(platform=r[0], count=r[1]) for r in by_platform],
            "by_keyword": [dict(keyword=r[0], count=r[1]) for r in by_keyword],
            "top_authors": [dict(author=r[0], count=r[1]) for r in top_authors],
            "published_range": {"min": time_range[0], "max": time_range[1]},
        }
    finally:
        conn.close()


def export_rows(db_path=DEFAULT_DB):
    """导出全部记录（供 CSV / JSON 序列化）。"""
    conn = _connect(db_path)
    try:
        cols = ["keyword", "platform", "title", "text", "url", "author",
                "published_at", "source_adapter", "fetched_at"]
        rows = conn.execute(
            "SELECT keyword, platform, title, text, url, author, "
            "published_at, source_adapter, fetched_at FROM collected_posts "
            "ORDER BY published_at DESC").fetchall()
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()
```

### 9. `collect/demo_cli.py`（186 行）

```python
"""CyberField 多源采集 Demo —— 终端交互式浏览试用（无图形界面）。

用法（在主项目根目录）：
    python -m collect.demo_cli
    # 或
    python collect/demo_cli.py

菜单：
    [1] 采集新关键词   调用 MediaCrawler 真实搜索（首次需扫码登录）
    [2] 浏览本地库     查看已采集帖子（可按关键词/平台过滤）
    [3] 统计概览       平台分布 / 关键词分布 / 作者 TOP / 时间范围
    [4] 导出 CSV/JSON  导出本地库全部记录
    [5] 退出
    也可以直接输入一个关键词，等价于执行 [1]。

说明：本次 Demo 接入的第一个源是 MediaCrawler（外部开源工具），
将来新增源只需在 collect/sources/ 注册新适配器，本入口不变。
"""

import json
import sys
from pathlib import Path

# 允许两种启动方式：python -m collect.demo_cli 与 python collect/demo_cli.py
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

sys.stdout.reconfigure(encoding="utf-8")

from collect import orchestrator, store                      # noqa: E402
from collect.post import platform_label                      # noqa: E402

BANNER = r"""
 _  _ ___   _ _    _____ _           _   _
| || | __| | | |__| __  | |__  ___ _| |_| |
| __ | _|  | | / /| __ -| '_ \/ -_) | | . |
|_||_|_|   |_|_\_\|_____|_.__/\___|_\_|___|
  多源采集 Demo · 终端试用版（首个源：MediaCrawler）
"""

MENU = """
  [1] 采集新关键词    [2] 浏览本地库    [3] 统计概览
  [4] 导出 CSV/JSON   [5] 退出
  直接输入关键词 = 执行采集。输入 ? 查看帮助。"""


def _fmt_el(s: str, width: int) -> str:
    """按显示宽度截断字符串（中文按 2 个显示宽度计）。"""
    s = s.replace("\n", " ").replace("\r", " ").strip()
    w = 0
    out = []
    for ch in s:
        w += 2 if ord(ch) > 127 else 1
        if w > width - 1:
            out.append("…")
            break
        out.append(ch)
    return "".join(out)


def _print_table(rows: list[dict], limit: int = 30):
    """打印帖子列表：平台 | 作者 | 时间 | 标题 | 链接。"""
    if not rows:
        print("  （无记录）")
        return
    show = rows[:limit]
    print(f"  {len(rows)} 条记录，显示前 {min(limit, len(rows))} 条：")
    for r in show:
        title = _fmt_el(r.get("title") or "(无标题)", 30)
        author = _fmt_el(r.get("author") or "-", 12)
        time = _fmt_el(r.get("published_at") or "-", 19)
        url = _fmt_el(r.get("url") or "", 46)
        print(f"    [{platform_label(r.get('platform') or r['platform'])}] "
              f"{author} | {time}")
        print(f"      {title}")
        print(f"      {url}")
    if len(rows) > limit:
        print(f"  …其余 {len(rows) - limit} 条未显示（浏览命令可缩小过滤范围）")


def cmd_collect():
    keyword = input("  请输入关键词：").strip()
    if not keyword:
        return
    platforms = input("  平台（默认 xhs；逗号分隔可多平台，如 xhs,bili）：").strip() or "xhs"
    limit_s = input("  每平台条数（默认 20）：").strip()
    limit = int(limit_s) if limit_s.isdigit() else 20
    plist = [p.strip() for p in platforms.split(",") if p.strip()]

    print(f"\n  正在调用 MediaCrawler 搜索「{keyword}」（平台 {plist}，每平台 {limit} 条）…")
    print("  ⚠ 首次使用会弹出 Chrome 窗口，请扫码登录；后续自动复用登录态。\n")
    posts, errors, summary = orchestrator.collect(keyword, platforms=tuple(plist), limit=limit)
    if errors:
        print("  部分源不可用（已自动跳过，不影响其他源）：")
        for e in errors:
            print(f"    ✗ {e}")
    print(f"\n  采集完成：命中 {len(posts)} 条")
    if summary:
        print(f"  入库：新增 {summary['inserted']} 条，跳过重复 {summary['skipped']} 条")
    _print_table([p.__dict__ for p in posts])


def cmd_browse():
    kw = input("  过滤关键词（回车跳过）：").strip() or None
    pl = input("  过滤平台（回车跳过，如 xiaohongshu/bilibili）：").strip() or None
    limit_s = input("  显示条数（默认 30）：").strip()
    limit = int(limit_s) if limit_s.isdigit() else 30
    rows = store.query_posts(keyword=kw, platform=pl, limit=200)
    _print_table(rows, limit=limit)


def cmd_stats():
    s = store.stats()
    print(f"\n  本地库总条数：{s['total']}")
    print("  ── 平台分布 ──")
    for item in s["by_platform"]:
        print(f"    {platform_label(item['platform'])}：{item['count']} 条")
    print("  ── 关键词分布 ──")
    for item in s["by_keyword"]:
        print(f"    「{item['keyword']}」：{item['count']} 条")
    print("  ── 作者 TOP 10（按条数） ──")
    if s["top_authors"]:
        for i, item in enumerate(s["top_authors"], 1):
            print(f"    {i}. {item['author']}：{item['count']} 条")
    else:
        print("    （暂无作者数据）")
    if s["published_range"]["min"]:
        print("  ── 发布时间范围 ──")
        print(f"    {s['published_range']['min']}  ~  {s['published_range']['max']}")


def cmd_export():
    rows = store.export_rows()
    out_dir = Path(__file__).resolve().parent.parent / "data" / "export"
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "collected_posts.csv"
    json_path = out_dir / "collected_posts.json"
    if rows:
        import csv
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print(f"\n  已导出 {len(rows)} 条记录：")
    print(f"    CSV : {csv_path}")
    print(f"    JSON: {json_path}")


def main():
    print(BANNER)
    while True:
        print(MENU)
        choice = input("  > ").strip()
        if choice == "1":
            cmd_collect()
        elif choice == "2":
            cmd_browse()
        elif choice == "3":
            cmd_stats()
        elif choice == "4":
            cmd_export()
        elif choice == "5" or choice.lower() in ("q", "quit", "exit"):
            print("  再见 👋")
            break
        elif choice == "?":
            print("  直接输入关键词 = 执行采集 [1]；菜单项如上。")
        elif choice:
            # 直接输入关键词 → 等价于采集
            keyword = choice
            platforms = "xhs"
            print(f"\n  正在调用 MediaCrawler 搜索「{keyword}」（默认平台 {platforms}）…")
            posts, errors, summary = orchestrator.collect(keyword, platforms=(platforms,))
            if errors:
                for e in errors:
                    print(f"    ✗ {e}")
            print(f"  命中 {len(posts)} 条；入库新增 "
                  f"{summary['inserted'] if summary else 0} 条，"
                  f"重复 {summary['skipped'] if summary else 0} 条")
            _print_table([p.__dict__ for p in posts])
        print()


if __name__ == "__main__":
    main()
```

### 10. `collect/sources/__init__.py`（17 行）

```python
"""数据源适配器注册表。新增源时：
1. 在本目录新建一个 *_source.py 实现 BaseSource；
2. 在下方 AVAILABLE_SOURCES 里登记，即可被 demo 使用，旧源不受影响。
"""

from collect.sources.base_source import BaseSource, SourceUnavailable
from collect.sources.mediacrawler_source import MediaCrawlerSource

# 已登记的适配器（name -> 工厂）。以后加 zhihu_mcp / weibo_mcp 等就在这里追加。
AVAILABLE_SOURCES: dict[str, type[BaseSource]] = {
    MediaCrawlerSource.name: MediaCrawlerSource,
}


def create_source(name: str, **kwargs) -> BaseSource:
    """按名称创建适配器实例，未知名称抛 KeyError。"""
    return AVAILABLE_SOURCES[name](**kwargs)
```

### 11. `collect/sources/base_source.py`（41 行）

```python
"""数据源抽象接口（BaseSource）。

所有源适配器必须继承 BaseSource 并实现 search()。
上层（orchestrator / demo）只依赖本接口，不感知具体源。
"""

from abc import ABC, abstractmethod

from collect.post import Post


class SourceUnavailable(Exception):
    """源不可用（未登录 / 被风控 / 工具损坏 / 已下架）。

    调度器捕获此异常后跳过该源，继续用其他源，保证"一个挂了不影响另一个"。
    """


class BaseSource(ABC):
    """数据源适配器接口。

    子类需声明：
        name       适配器名（写入 source_adapter 字段，用于追溯）
        platforms  该源支持的规范化平台名列表
    """

    name: str = "base"
    platforms: list[str] = []

    @abstractmethod
    def search(self, keyword: str, platform: str | None = None,
               limit: int = 20) -> list[Post]:
        """搜索关键词，返回统一 Post 列表。

        失败时抛 SourceUnavailable（带可读原因），不要静默返回空。
        平台不支持时返回空列表即可。
        """

    def health_check(self) -> bool:
        """源是否可用（工具存在、登录态有效等）。默认 True，子类按需重写。"""
        return True
```

### 12. `collect/sources/mediacrawler_source.py`（141 行）

```python
"""MediaCrawler 适配器。

MediaCrawler（github.com/NanmiCoder/MediaCrawler）是外部开源工具，支持
xhs / dy / ks / bili / wb / tieba / zhihu 七个平台的关键词搜索。

本适配器只做两件事：
1. 以子进程方式调用 MediaCrawler 的 main.py 执行搜索（登录态由 MediaCrawler
   自身管理，搜索关键词通过 --keywords 传入，JSONL 落盘）；
2. 读取 MediaCrawler 输出的 data/{platform}/jsonl/search_contents_*.jsonl，
   把每条记录规范化为统一 Post。

接口统一、不写任何爬虫逻辑；MediaCrawler 被下架或损坏时抛 SourceUnavailable，
由调度器跳过，不影响其他源。
"""

import json
import subprocess
from pathlib import Path

from collect.post import Post, normalize_platform
from collect.sources.base_source import BaseSource, SourceUnavailable

# 本适配器直接透传 MediaCrawler 的平台码（xhs / bili / wb / zhihu / dy / ks / tieba）。
_MC_PLATFORM_CODES = {
    "xhs", "bili", "wb", "zhihu", "dy", "ks", "tieba",
}


class MediaCrawlerSource(BaseSource):
    name = "mediacrawler"
    platforms = ["xiaohongshu", "bilibili", "weibo", "zhihu",
                 "douyin", "kuaishou", "tieba"]

    def __init__(self, mc_dir: str = r"D:\Projects\MediaCrawler",
                 mc_python: str | None = None,
                 login: str = "qrcode"):
        """参数：
            mc_dir    MediaCrawler 仓库根目录
            mc_python MediaCrawler 的 Python 解释器（默认 .venv/Scripts/python.exe）
            login     登录方式 qrcode / cookie（首次需扫码）
        """
        self.mc_dir = Path(mc_dir)
        self.mc_python = mc_python or str(self.mc_dir / ".venv" / "Scripts" / "python.exe")
        self.login = login

    # ---------------------------------------------------------------- 对外接口
    def search(self, keyword: str, platform: str | None = None,
               limit: int = 20) -> list[Post]:
        platform = platform or "xhs"
        code = self._resolve_code(platform)
        if code is None:
            return []  # 不支持的平台，静默返回空
        result = self._run(keyword, code, limit)
        if result.returncode != 0:
            tail = (result.stdout or "")[-500:] + (result.stderr or "")[-500:]
            raise SourceUnavailable(
                f"MediaCrawler 退出码 {result.returncode}，尾部输出：{tail.strip()}")
        return self.load_results(keyword=keyword, platform_code=code)

    def health_check(self) -> bool:
        return (self.mc_dir / "main.py").exists() and Path(self.mc_python).exists()

    # ---------------------------------------------------------------- 内部实现
    def _resolve_code(self, platform: str) -> str | None:
        """平台参数可能是规范化名（xiaohongshu）或 MediaCrawler 码（xhs），都能识别。"""
        rev = {normalize_platform(c): c for c in _MC_PLATFORM_CODES}
        if platform in _MC_PLATFORM_CODES:
            return platform
        return rev.get(platform)

    def _run(self, keyword: str, code: str, limit: int):
        # MediaCrawler 每次搜索最少抓 20 条（小红书一页 20），clamp 到合理值。
        count = max(int(limit), 20)
        cmd = [
            self.mc_python,
            str(self.mc_dir / "main.py"),
            "--platform", code,
            "--lt", self.login,
            "--type", "search",
            "--keywords", keyword,
            "--save_data_option", "jsonl",
            "--crawler_max_notes_count", str(count),
        ]
        # timeout 给足：搜索 + 逐条详情，一般 1~3 分钟。
        return subprocess.run(
            cmd, cwd=str(self.mc_dir),
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=300,
        )

    def load_results(self, keyword: str | None = None,
                     platform_code: str = "xhs") -> list[Post]:
        """读取 JSONL 落盘结果并规范化为 Post 列表（不触发抓取，可单独用于复查）。"""
        posts: list[Post] = []
        for path in self._jsonl_paths(platform_code):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if keyword is not None:
                    rec_kw = str(rec.get("source_keyword") or "").strip()
                    if rec_kw != keyword:
                        continue
                posts.append(self._to_post(rec, platform_code, keyword))
        return posts

    def _jsonl_paths(self, code: str):
        data_dir = self.mc_dir / "data" / code / "jsonl"
        if not data_dir.exists():
            return []
        return sorted(data_dir.glob("search_contents_*.jsonl"))

    def _to_post(self, rec: dict, code: str, keyword: str | None) -> Post:
        title = rec.get("title") or rec.get("desc") or ""
        text = rec.get("desc") or ""
        url = rec.get("note_url") or rec.get("url") or ""
        return Post(
            platform=normalize_platform(code),
            title=title,
            text=text,
            url=url,
            author=rec.get("nickname") or rec.get("author") or "",
            published_at=str(rec.get("time") or ""),
            source_adapter=self.name,
            keyword=str(rec.get("source_keyword") or keyword or ""),
            extra={
                "liked": rec.get("liked_count"),
                "collected": rec.get("collected_count"),
                "comment": rec.get("comment_count"),
                "share": rec.get("share_count"),
                "note_id": rec.get("note_id"),
            },
        )
```

---

## 四、运行方式速查

```powershell
# 测试（20 项）
python test_clean_posts.py   # 7 项
python test_posts_db.py      # 13 项

# Demo 终端试用（主项目根目录）
python -m collect.demo_cli

# MediaCrawler 真实搜索（workdir 必须是 MediaCrawler 目录）
D:\Projects\MediaCrawler\.venv\Scripts\python.exe -B main.py `
  --platform xhs --lt qrcode --type search --keywords "奥德赛" `
  --save_data_option jsonl --crawler_max_notes_count 20
```
