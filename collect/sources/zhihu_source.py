"""知乎登录态搜索适配器（轻量：只取搜索列表，不抓逐条详情/评论）。

调用方式与小红书一致：以子进程跑 MediaCrawler venv 的
tools/zhihu_search_standalone.py（复用其 ZhiHuClient 签名客户端，不改外部
项目），登录态来自专用档案 browser_data/zhihu_user_data_dir。未登录 / 会话
失效时抛 SourceUnavailable（带可读原因），由调度器跳过，不影响其他源。
"""

import json
import subprocess
from pathlib import Path

from collect.post import Post, normalize_platform
from collect.sources.base_source import BaseSource, SourceUnavailable
from collect import settings


class ZhihuApiSource(BaseSource):
    name = "zhihu_api"
    platforms = ["zhihu"]

    def __init__(self, mc_dir: str | None = None,
                 mc_python: str | None = None,
                 script: str | None = None,
                 profile: str | None = None,
                 timeout: int = 90):
        """参数：
            mc_dir    MediaCrawler 仓库根目录
            mc_python MediaCrawler 的 Python 解释器
            script    自建搜索脚本路径（默认 tools/zhihu_search_standalone.py）
            profile   知乎专用档案目录（默认 browser_data/zhihu_user_data_dir）
            timeout   单次搜索子进程超时秒数
        """
        self.mc_dir = Path(mc_dir or settings.MEDIACRAWLER_DIR)
        self.mc_python = mc_python or str(self.mc_dir / ".venv" / "Scripts" / "python.exe")
        self.script = Path(script or settings.ZHIHU_SEARCH_SCRIPT)
        self.profile = Path(profile or self.mc_dir / "browser_data" / "zhihu_user_data_dir")
        self.timeout = int(timeout)

    def health_check(self) -> bool:
        return (self.script.exists() and Path(self.mc_python).exists()
                and self.profile.exists())

    def search(self, keyword: str, platform: str | None = None,
               limit: int = 20) -> list[Post]:
        # 只服务知乎平台；调度器传了别的平台码时静默返回空。
        if normalize_platform(platform or "zhihu") != "zhihu":
            return []
        if type(limit) is not int or limit <= 0:
            raise ValueError("limit 必须为正整数")
        payload = self._parse_output(self._run(keyword, limit))
        if not payload.get("ok"):
            raise SourceUnavailable(self._friendly(payload))
        items = payload.get("items") or []
        return [self._to_post(it, keyword) for it in items][:limit]

    # ---------------------------------------------------------------- 内部实现
    def _run(self, keyword: str, limit: int):
        return subprocess.run(
            [self.mc_python, str(self.script), "--profile", str(self.profile),
             "--keyword", keyword, "--limit", str(limit)],
            cwd=str(self.mc_dir), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=self.timeout,
        )

    @staticmethod
    def _parse_output(result):
        """解析脚本输出：取最后一行可解析的 JSON，失败返回可读错误。"""
        for line in reversed((result.stdout or "").splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                return data
        return {"ok": False, "reason": "no_json_output",
                "hint": f"知乎搜索脚本无有效输出（退出码 {result.returncode}）"}

    @staticmethod
    def _friendly(payload: dict) -> str:
        """把脚本返回码转成对用户可读的原因；不回传异常原文以防夹带凭据。"""
        reason = payload.get("reason") or "unknown"
        hint = payload.get("hint") or ""
        if reason.startswith("login_expired"):
            return "知乎登录态失效，请在账号面板重新登录后重试"
        if reason.startswith("browser_missing"):
            return hint or "缺少浏览器"
        if reason.startswith("browser_launch_failed"):
            return "知乎浏览器启动失败（可能残留窗口占用了档案），请关闭后重试"
        if reason.startswith("page_load_failed"):
            return "知乎页面加载失败，请检查网络"
        if reason.startswith("api_error"):
            return "知乎搜索被拦截或出错，请稍后重试"
        if reason.startswith("no_json_output"):
            return hint or "知乎搜索脚本未返回结果"
        return hint or f"知乎搜索失败：{reason}"

    def _to_post(self, item: dict, keyword: str) -> Post:
        """把搜索项转为统一 Post。搜索项来自脚本序列化的 ZhihuContent。"""
        title = str(item.get("title") or "")
        desc = str(item.get("desc") or "")
        return Post(
            platform="zhihu",
            title=title or desc[:40],
            text=desc or title,
            url=str(item.get("content_url") or ""),
            author=str(item.get("user_nickname") or ""),
            published_at=str(item.get("created_time") or 0),
            source_adapter=self.name,
            keyword=keyword,
            extra={
                "voteup": item.get("voteup_count"),
                "comment": item.get("comment_count"),
                "content_id": item.get("content_id"),
                "content_type": item.get("content_type"),
            },
        )
