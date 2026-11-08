"""旧豆瓣修复入口：改为只读核对，禁止把导演和上映年填成发帖信息。"""
from collect import store

def backfill():
    """读取兼容视图；原始字段保留在 extra 中，不发请求、不修改数据库。"""
    rows = store.query_posts(platform="douban", limit=None)
    count = sum(r["record_type"] == "catalog_item" for r in rows)
    print(f"已识别 {count} 条影视条目。读取时隔离旧作者/日期；原始数据库未改动。")

if __name__ == "__main__":
    backfill()
