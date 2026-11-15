"""评论获取：B站接口和小红书本地JSONL，保留现有筛选与降级规则。

HTTP会话由搜索管道传入；本模块不负责搜索、模型调用或后台调度。
"""
import re
from collect import settings

_HOME_URL = "https://www.bilibili.com/"
_VIEW_API = "https://api.bilibili.com/x/web-interface/view"
_REPLY_API = "https://api.bilibili.com/x/v2/reply/main"


def fetch_comments(p, session, max_comments=settings.MAX_COMMENTS) -> list[str]:
    """尽力而为取热评：B站评论接口游客态不可用会跳过；小红书读已抓 JSONL。"""
    if p.platform == "bilibili":
        bvid = (p.extra or {}).get("bvid")
        if not bvid:
            return []
        try:
            view = session.get_json(
                _VIEW_API, params={"bvid": bvid}, referer=_HOME_URL)
            d = view.get("data") or {}
            cid = d.get("cid")
            if not cid:
                return []
            reply = session.get_json(
                _REPLY_API,
                params={"type": 1, "oid": cid, "mode": 3, "next": 0},
                referer=f"https://www.bilibili.com/video/{bvid}")
            reps = ((reply.get("data") or {}).get("replies")) or []
            return [(r.get("content") or {}).get("message", "").strip()
                    for r in reps[:max_comments]
                    if (r.get("content") or {}).get("message")]
        except Exception:
            return []
    if p.platform == "xiaohongshu":
        return xhs_comments_from_jsonl(p, max_comments=max_comments)
    return []


def xhs_comments_from_jsonl(p, max_comments=settings.MAX_COMMENTS, data_dir=None) -> list[str]:
    """从 MediaCrawler 已抓的评论 JSONL 里读该笔记的高赞评论（尽力而为）。"""
    import json
    from pathlib import Path
    note_id = str((p.extra or {}).get("note_id") or "")
    if not note_id:
        return []
    data_dir = Path(data_dir) if data_dir is not None else settings.XHS_JSONL_DIR
    if not data_dir.exists():
        return []
    hits = []
    for f in sorted(data_dir.glob("search_comments_*.jsonl"))[-2:]:
        try:
            for line in f.read_text(encoding="utf-8",
                                    errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if str(r.get("note_id") or "") != note_id:
                    continue
                hits.append(r)
        except OSError:
            continue
    hits.sort(key=lambda r: -_like_num(r.get("like_count")))
    return [(h.get("content") or "").strip() for h in hits[:max_comments]
            if (h.get("content") or "").strip()]


def _like_num(value) -> int:
    """'1.4万' → 14000；解析失败返回 0。"""
    try:
        s = str(value or "").replace(",", "")
        m = re.match(r"^([\d.]+)(万)?$", s)
        if not m:
            return 0
        return int(float(m.group(1)) * 10000) if m.group(2) else int(float(m.group(1)))
    except ValueError:
        return 0
