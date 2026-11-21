"""MediaCrawler 适配器。

MediaCrawler（github.com/NanmiCoder/MediaCrawler）是外部开源工具，支持
xhs / dy / ks / bili / wb / tieba / zhihu 七个平台的关键词搜索。

本适配器只做两件事：
1. 以子进程方式调用 MediaCrawler 的 main.py 执行搜索（登录态由 MediaCrawler
   自身管理，搜索关键词通过 --keywords 传入，JSONL 落盘）；
2. 读取 MediaCrawler 输出的 data/{platform}/jsonl/ 下的两种 JSONL：
   - search_contents_*.jsonl  笔记/正文 → 统一 Post
   - search_comments_*.jsonl  评论 → 筛选高质量评论（剔除 @ 拉人、按
     点赞/长度/讨论精选、每笔记限量）后转为 record_type="comment" 的 Post。

接口统一、不写任何爬虫逻辑；MediaCrawler 被下架或损坏时抛 SourceUnavailable，
由调度器跳过，不影响其他源。
"""

import json
import logging
import re
import subprocess
import threading
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from collect.num_utils import parse_count_int
from collect.post import Post, normalize_platform
from collect.sources.base_source import BaseSource, SourceUnavailable
from collect.time_utils import normalize_time
from collect import settings

logger = logging.getLogger(__name__)

# MediaCrawler 的 JSONL 输出目录跨运行共享，不能并发做“前后差分”，
# 否则并发任务会把别的任务新写入的行误判为本次新增。全局串行化该子进程调用。
_MC_RUN_LOCK = threading.Lock()

# 本适配器直接透传 MediaCrawler 的平台码（xhs / bili / wb / zhihu / dy / ks / tieba）。
_MC_PLATFORM_CODES = {
    "xhs", "bili", "wb", "zhihu", "dy", "ks", "tieba",
}

# ---- 评论筛选规则（评论是次要数据，只保留高质量、且每笔记限量）----
_AT_RE = re.compile(r"@[\w\u4e00-\u9fa5_-]{1,20}")  # @ 拉人看的行为
_MIN_LIKE = 100          # 点赞数（解析「万」后）>= 100
_MIN_LENGTH = 50         # 正文长度 >= 50 字
_MIN_DISCUSSION = 30     # 讨论（楼中楼）>= 30 条
_MAX_COMMENTS_PER_NOTE = 2  # 每条笔记最多保留的高质量评论数


def _parse_count(value) -> int:
    """'1.4万' → 14000；'0' → 0；无法解析返回 0。实现统一见 collect.num_utils。"""
    return parse_count_int(value)


class MediaCrawlerSource(BaseSource):
    name = "mediacrawler"
    platforms = ["xiaohongshu", "bilibili", "weibo", "zhihu",
                 "douyin", "kuaishou", "tieba"]

    def __init__(self, mc_dir: str = str(settings.MEDIACRAWLER_DIR),
                 mc_python: str | None = None,
                 login: str = "qrcode",
                 ocr: bool = False):
        """参数：
            mc_dir    MediaCrawler 仓库根目录
            mc_python MediaCrawler 的 Python 解释器（默认 .venv/Scripts/python.exe）
            login     登录方式 qrcode / cookie（首次需扫码）
            ocr       是否对笔记图片做 OCR（识别观点文字，慢约 1 秒/图）
        """
        self.mc_dir = Path(mc_dir)
        self.mc_python = mc_python or str(self.mc_dir / ".venv" / "Scripts" / "python.exe")
        self.login = login
        self.ocr = ocr

    # ---------------------------------------------------------------- 对外接口
    def search(self, keyword: str, platform: str | None = None,
               limit: int = 20) -> list[Post]:
        platform = platform or "xhs"
        code = self._resolve_code(platform)
        if code is None:
            return []  # 不支持的平台，静默返回空
        if type(limit) is not int or limit <= 0:
            raise ValueError("limit 必须为正整数")
        # 比较运行前后的记录多重集合，追加同内容也算本次观察。
        # 差分必须串行：JSONL 目录是跨任务共享的，并发运行会互相污染“新增”。
        with _MC_RUN_LOCK:
            before = Counter(self._fingerprint(p) for p in self.load_results(keyword, code))
            result = self._run(keyword, code, limit)
            if result.returncode != 0:
                tail = (result.stdout or "")[-500:] + (result.stderr or "")[-500:]
                raise SourceUnavailable(
                    f"MediaCrawler 退出码 {result.returncode}，尾部输出：{tail.strip()}")
            fresh = []
            for post in self.load_results(keyword=keyword, platform_code=code):
                key = self._fingerprint(post)
                if before[key]:
                    before[key] -= 1
                else:
                    fresh.append(post)
        # limit 只约束笔记；筛选后的评论按笔记附带返回，不占用笔记额度。
        notes = [p for p in fresh if p.record_type != "comment"][:limit]
        comments = [p for p in fresh if p.record_type == "comment"]
        return notes + comments

    @staticmethod
    def _fingerprint(post):
        """稳定序列化用于排除运行前已有记录；相同文件重写保守视作旧记录。"""
        return json.dumps(asdict(post), ensure_ascii=False, sort_keys=True)

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
        """读取 JSONL 落盘结果并规范化为 Post 列表（不触发抓取，可单独用于复查）。

        返回笔记 Post + 筛选后的评论 Post；keyword 只用于过滤（笔记与评论都带
        source_keyword，未带该字段时视为匹配本次关键词）。
        """
        posts: list[Post] = []
        note_urls: dict[str, str] = {}
        for path in self._jsonl_paths(platform_code, kind="contents"):
            for rec in self._read_jsonl(path):
                if keyword is not None and rec.get("source_keyword") is not None \
                        and str(rec.get("source_keyword")).strip() != keyword:
                    continue
                post = self._to_post(rec, platform_code, keyword)
                posts.append(post)
                if rec.get("note_url"):
                    note_urls[str(rec.get("note_id"))] = str(rec.get("note_url"))
        # 评论：读评论 JSONL，按笔记分组筛选高质量评论。
        comments: list[Post] = []
        for path in self._jsonl_paths(platform_code, kind="comments"):
            recs = list(self._read_jsonl(path))
            if keyword is not None:
                recs = [r for r in recs if str(r.get("source_keyword") or "").strip()
                        in ("", keyword)]
            comments.extend(self._comment_posts(recs, platform_code, keyword,
                                                note_urls))
        # 评论总量不超过笔记的 1/3（评论是补充数据，笔记为主）。
        cap = max(3, len(posts) // 3)
        if len(comments) > cap:
            comments.sort(key=lambda p: (p.extra.get("like") or 0,
                                         len(p.text)), reverse=True)
            comments = comments[:cap]
        posts.extend(comments)
        # JSONL 跨运行累积：按 (platform, url) 去重，避免重复入库。
        seen: set[tuple[str, str]] = set()
        uniq: list[Post] = []
        for post in posts:
            key = (post.platform, post.url) if post.url else id(post)
            if key not in seen:
                seen.add(key)
                uniq.append(post)
        return uniq

    @staticmethod
    def _read_jsonl(path: Path):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            logger.debug("JSONL 读取失败：%s", path, exc_info=True)
            return
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict):
                yield rec

    def _comment_posts(self, recs: list[dict], code: str, keyword: str | None,
                       note_urls: dict[str, str]) -> list[Post]:
        """从评论记录里筛出高质量评论（剔除 @ 拉人、点赞/长度/讨论达标、限量）。"""
        grouped: dict[str, list[dict]] = {}
        for rec in recs:
            content = (rec.get("content") or "").strip()
            if not content or _AT_RE.search(content):
                continue  # 空评论 / @ 拉人看的无效评论
            liked = _parse_count(rec.get("like_count"))
            sub = int(rec.get("sub_comment_count") or 0)
            if not (liked >= _MIN_LIKE or len(content) >= _MIN_LENGTH
                    or sub >= _MIN_DISCUSSION):
                continue
            note_id = str(rec.get("note_id") or "")
            grouped.setdefault(note_id, []).append(rec)
        posts: list[Post] = []
        for note_id, items in grouped.items():
            # 质量分排序：点赞*2 + 内容长度 + 讨论数，取每笔记前 N 条。
            items.sort(
                key=lambda r: (_parse_count(r.get("like_count")) * 2
                               + len(r.get("content") or "")
                               + int(r.get("sub_comment_count") or 0)),
                reverse=True)
            for rec in items[:_MAX_COMMENTS_PER_NOTE]:
                posts.append(self._to_comment_post(rec, code, keyword,
                                                   note_urls.get(note_id, "")))
        return posts

    def _jsonl_paths(self, code: str, kind: str = "contents"):
        data_dir = self.mc_dir / "data" / code / "jsonl"
        if not data_dir.exists():
            return []
        pattern = f"search_{kind}_*.jsonl"
        return sorted(data_dir.glob(pattern))

    def _to_post(self, rec: dict, code: str, keyword: str | None) -> Post:
        title = rec.get("title") or rec.get("desc") or ""
        text = rec.get("desc") or ""
        url = rec.get("note_url") or rec.get("url") or ""
        tags = rec.get("tag_list") or ""
        extra: dict = {
            "liked": rec.get("liked_count"),
            "collected": rec.get("collected_count"),
            "comment": rec.get("comment_count"),
            "share": rec.get("share_count"),
            "note_id": rec.get("note_id"),
            "tags": tags.split(",") if tags else [],
            "type": rec.get("type"),
        }
        if self.ocr:
            # 识别图片里的观点文字；结果独立存字段，不污染原文。
            from collect import ocr
            lines = ocr.ocr_note_images(rec.get("image_list") or "")
            if lines:
                extra["ocr_text"] = lines
        return Post(
            platform=normalize_platform(code),
            title=title,
            text=text,
            url=url,
            author=rec.get("nickname") or rec.get("author") or "",
            published_at=normalize_time(rec.get("time")),
            source_adapter=self.name,
            keyword=str(rec.get("source_keyword") or keyword or ""),
            extra=extra,
        )

    def _to_comment_post(self, rec: dict, code: str, keyword: str | None,
                         note_url: str) -> Post:
        content = (rec.get("content") or "").strip()
        note_id = str(rec.get("note_id") or "")
        # url 带评论 id 保证同一笔记的多条评论互不冲突、也与笔记去重键不同。
        base = note_url or f"https://www.xiaohongshu.com/explore/{note_id}"
        return Post(
            platform=normalize_platform(code),
            title="",
            text=content,
            url=f"{base}#comment-{rec.get('comment_id') or note_id}",
            author=rec.get("nickname") or "",
            published_at=normalize_time(rec.get("create_time")),
            source_adapter=self.name,
            keyword=str(rec.get("source_keyword") or keyword or ""),
            record_type="comment",
            extra={
                "note_id": note_id,
                "like": _parse_count(rec.get("like_count")),
                "discussion": int(rec.get("sub_comment_count") or 0),
                "parent_comment_id": rec.get("parent_comment_id") or "",
            },
        )
