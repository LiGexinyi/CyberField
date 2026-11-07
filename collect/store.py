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
