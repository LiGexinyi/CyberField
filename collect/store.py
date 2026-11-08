"""SQLite 存储：兼容旧库、只读查询，以及按采集时刻保存元数据快照。"""
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from collect.time_utils import normalize_time

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

def _connect(db_path):
    """仅写入时建表，附加表不覆盖旧记录。"""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(_SCHEMA)
    conn.execute("CREATE TABLE IF NOT EXISTS post_observations (id INTEGER PRIMARY KEY, post_id INTEGER NOT NULL, observed_at TEXT NOT NULL, keyword TEXT, record_type TEXT NOT NULL, extra_json TEXT NOT NULL)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_obs_post ON post_observations(post_id, id)")
    return conn


def save_posts(posts, db_path=DEFAULT_DB):
    """幂等保存帖子；每次入库独立记录互动快照，失败整批回滚。"""
    posts = list(posts)
    if any(not p.platform or not p.url or not p.url.strip() for p in posts):
        raise ValueError("入库记录必须具有平台和非空来源链接")
    conn = _connect(db_path)
    inserted = skipped = 0
    try:
        with conn:
            for p in posts:
                cur = conn.execute("INSERT OR IGNORE INTO collected_posts (keyword,platform,title,text,url,author,published_at,source_adapter) VALUES (?,?,?,?,?,?,?,?)", (p.keyword,p.platform,p.title,p.text,p.url,p.author,p.published_at,p.source_adapter))
                inserted += int(cur.rowcount == 1)
                skipped += int(cur.rowcount != 1)
                pid = conn.execute("SELECT id FROM collected_posts WHERE platform=? AND url=?", (p.platform,p.url)).fetchone()[0]
                # 使用 UTC 带时区时间；指标保存原值，不猜测单位或补零。
                conn.execute("INSERT INTO post_observations(post_id,observed_at,keyword,record_type,extra_json) VALUES (?,?,?,?,?)", (pid,datetime.now(timezone.utc).isoformat(timespec="microseconds"),p.keyword,p.record_type,json.dumps(p.extra,ensure_ascii=False,allow_nan=False)))
        return {"inserted": inserted, "skipped": skipped}
    finally:
        conn.close()


def export_rows(db_path=DEFAULT_DB):
    """只读导出兼容视图：修正旧豆瓣语义，但不改变磁盘原始数据。"""
    path = Path(db_path)
    if not path.exists():
        return []
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "collected_posts" not in tables:
            return []
        observations = {}
        if "post_observations" in tables:
            for row in conn.execute("SELECT * FROM post_observations ORDER BY id"):
                observations.setdefault(row["post_id"], []).append(dict(row))
        rows = []
        for raw in conn.execute("SELECT * FROM collected_posts"):
            row = dict(raw)
            history = observations.get(row.pop("id"), [])
            for observation in history:
                observation["extra"] = json.loads(observation.pop("extra_json"))
            row["observations"] = history
            row["extra"] = dict(history[-1]["extra"]) if history else {}
            row["record_type"] = history[-1]["record_type"] if history else "post"
            row["keywords"] = sorted({row.get("keyword") or ""} | {h["keyword"] or "" for h in history})
            if row["source_adapter"] == "douban_api":
                row["record_type"] = "catalog_item"
                # 历史字段仅保留为原值，不再参与发帖作者/时间统计。
                row["extra"].setdefault("legacy_author", row["author"])
                row["extra"].setdefault("legacy_published_at", row["published_at"])
                row["author"] = row["published_at"] = ""
            else:
                row["extra"].setdefault("published_at_raw", row["published_at"])
                row["published_at"] = normalize_time(row["published_at"])
            rows.append(row)
        return sorted(rows, key=lambda r: r["published_at"] or "", reverse=True)
    finally:
        conn.close()


def query_posts(keyword=None, platform=None, limit=50, db_path=DEFAULT_DB):
    """按字面关键词过滤；limit=None 返回全部，读取不建库。"""
    if limit is not None and (type(limit) is not int or limit <= 0):
        raise ValueError("limit 必须为正整数或 None")
    rows = export_rows(db_path)
    if keyword:
        needle = keyword.casefold()
        rows = [r for r in rows if needle in " ".join([*r["keywords"],r["title"] or "",r["text"] or ""]).casefold()]
    if platform:
        rows = [r for r in rows if r["platform"] == platform]
    return rows if limit is None else rows[:limit]


def stats(db_path=DEFAULT_DB):
    """统计样本分布；影视条目不计入发帖作者和时间范围。"""
    rows = export_rows(db_path)
    posts = [r for r in rows if r["record_type"] == "post"]
    dates = [r["published_at"] for r in posts if r["published_at"]]
    platforms = Counter(r["platform"] for r in rows)
    keywords = Counter(k for r in rows for k in r["keywords"] if k)
    authors = Counter((r["platform"], r["author"]) for r in posts if r["author"])
    return {"total":len(rows), "by_platform":[{"platform":k,"count":v} for k,v in platforms.most_common()], "by_keyword":[{"keyword":k,"count":v} for k,v in keywords.most_common()], "top_authors":[{"author":a,"platform":p,"count":v} for (p,a),v in authors.most_common(10)], "published_range":{"min":min(dates) if dates else None,"max":max(dates) if dates else None}}
