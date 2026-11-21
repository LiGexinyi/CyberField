"""登录态独立脚本搜索源的公共骨架（小红书 / 知乎共用）。

各适配器的差异只有：平台名、默认脚本路径、专用档案目录、超时和字段映射
（_to_post）。子进程调用、单行 JSON 输出解析、错误文案映射等通用流程集中
在本基类；新增同类登录态脚本源只需继承并给出类属性与 _to_post。

脚本协议：stdout 最后一行必须是 JSON 对象 {"ok": bool, "items": [...],
"reason": str, "hint": str}；ok=false 时本基类把 reason 映射成可读原因。
"""

import json
import subprocess
from pathlib import Path

from collect.post import Post, normalize_platform
from collect.sources.base_source import BaseSource, SourceUnavailable
from collect import settings


class ScriptSearchSource(BaseSource):
    """以子进程调用自建搜索脚本、解析单行 JSON 结果的登录态搜索源基类。

    子类需提供的类属性：
        platform         规范化平台名（如 xiaohongshu / zhihu）
        platform_label   中文平台名（用于错误提示文案）
        default_script   默认脚本路径（settings 中的 Path）
        profile_dir      MediaCrawler 专用档案目录名（如 xhs_user_data_dir）
        default_timeout  子进程默认超时秒数
    """

    platform = ""
    platform_label = ""
    default_script = Path()
    profile_dir = ""
    default_timeout = 60

    def __init__(self, mc_dir: str | None = None,
                 mc_python: str | None = None,
                 script: str | None = None,
                 profile: str | None = None,
                 timeout: int | None = None):
        """参数：
            mc_dir    MediaCrawler 仓库根目录
            mc_python MediaCrawler 的 Python 解释器
            script    自建搜索脚本路径（默认取子类 default_script）
            profile   平台专用档案目录（默认 browser_data/<profile_dir>）
            timeout   单次搜索子进程超时秒数（默认取子类 default_timeout）
        """
        self.mc_dir = Path(mc_dir or settings.MEDIACRAWLER_DIR)
        # 便携版显式指定内置解释器。自定义仓库仍跟随该仓库的虚拟环境。
        default_python = (settings.MEDIACRAWLER_PYTHON if mc_dir is None
                          else self.mc_dir / ".venv" / "Scripts" / "python.exe")
        self.mc_python = mc_python or str(default_python)
        self.script = Path(script or self.default_script)
        self.profile = Path(profile or self.mc_dir / "browser_data" / self.profile_dir)
        self.timeout = int(self.default_timeout if timeout is None else timeout)

    def health_check(self) -> bool:
        """脚本、解释器、专用档案齐全才算健康。"""
        return (self.script.exists() and Path(self.mc_python).exists()
                and self.profile.exists())

    def search(self, keyword: str, platform: str | None = None,
               limit: int = 20) -> list[Post]:
        """只服务本平台；调度器传了别的平台码时静默返回空，交由对应源处理。"""
        if normalize_platform(platform or self.platform) != self.platform:
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
        """调用子进程：脚本 + 专用档案 + 关键词 + 数量上限。"""
        return subprocess.run(
            [self.mc_python, str(self.script), "--profile", str(self.profile),
             "--keyword", keyword, "--limit", str(limit)],
            cwd=str(self.mc_dir), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=self.timeout,
        )

    @classmethod
    def _parse_output(cls, result):
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
                "hint": f"{cls.platform_label}搜索脚本无有效输出"
                        f"（退出码 {result.returncode}）"}

    @classmethod
    def _friendly(cls, payload: dict) -> str:
        """把脚本返回码转成对用户可读的原因；不回传异常原文以防夹带凭据。"""
        label = cls.platform_label
        reason = payload.get("reason") or "unknown"
        hint = payload.get("hint") or ""
        if reason.startswith("login_expired"):
            return f"{label}登录态失效，请在账号面板重新登录后重试"
        if reason.startswith("browser_missing"):
            return hint or "缺少浏览器"
        if reason.startswith("browser_launch_failed"):
            return f"{label}浏览器启动失败（可能残留窗口占用了档案），请关闭后重试"
        if reason.startswith("page_load_failed"):
            return f"{label}页面加载失败，请检查网络"
        if reason.startswith("api_error"):
            return f"{label}搜索被拦截或出错，请稍后重试"
        if reason.startswith("no_json_output"):
            return hint or f"{label}搜索脚本未返回结果"
        return hint or f"{label}搜索失败：{reason}"

    def _to_post(self, item: dict, keyword: str) -> Post:
        """把脚本输出的搜索项转成统一 Post；子类必须实现字段映射。"""
        raise NotImplementedError
