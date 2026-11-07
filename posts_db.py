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
    会误伤字面内容。这里先把关键词里的 \\ % _ 三个字符加上转义前缀，
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
