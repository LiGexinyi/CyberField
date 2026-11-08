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
from collections import Counter
from dataclasses import asdict
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
        if type(limit) is not int or limit <= 0:
            raise ValueError("limit 必须为正整数")
        # 比较运行前后的记录多重集合，追加同内容也算本次观察。
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
        return fresh[:limit]

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
                if not isinstance(rec, dict):
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
