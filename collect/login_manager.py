"""网页侧平台账号登录管理。

把 MediaCrawler 的扫码登录搬进网页工作台：
- start_login(platform)  起子进程跑 MediaCrawler 的 login_standalone.py，
                         实时捕获二维码 base64；
- poll_login(platform)   查询本次登录进度（starting / qr_ready / logged_in /
                         expired / failed / idle）；
- is_logged_in(platform) 按 browser_data 是否存在登录档案粗判；真正是否有效由
                         MediaCrawler 搜索时自行 pong 校验（失效会自动重登）。

安全约定：不保存任何账号密码；登录态只存于 MediaCrawler 的
browser_data/{platform}_user_data_dir（扫码会话），与本项目代码隔离。
"""

import subprocess
import threading
from pathlib import Path

_MC_DIR = Path(r"D:\Projects\MediaCrawler")
_MC_PYTHON = _MC_DIR / ".venv" / "Scripts" / "python.exe"
_LOGIN_SCRIPT = _MC_DIR / "login_standalone.py"

# 支持扫码登录的平台（与 MediaCrawler PlatformEnum 一致）
PLATFORMS = [
    ("xhs", "小红书"),
    ("zhihu", "知乎"),
    ("bili", "B站"),
    ("wb", "微博"),
]


class LoginManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._jobs: dict[str, dict] = {}  # platform -> job dict

    # ------------------------------------------------------------ 状态查询
    def browser_dir(self, platform: str) -> Path:
        return _MC_DIR / "browser_data" / f"{platform}_user_data_dir"

    def is_logged_in(self, platform: str) -> bool:
        """按登录档案是否存在且带 cookie 粗判（zhihu/bili/wb 同构）。"""
        cookie = self.browser_dir(platform) / "Default" / "Network" / "Cookies"
        try:
            return cookie.exists() and cookie.stat().st_size > 0
        except OSError:
            return False

    def accounts(self) -> list[dict]:
        return [{"platform": p, "label": label,
                 "logged_in": self.is_logged_in(p)}
                for p, label in PLATFORMS]

    # ------------------------------------------------------------ 登录流程
    def start_login(self, platform: str) -> dict:
        """启动一次扫码登录。同一平台已有在跑进程时先结束旧进程。"""
        with self._lock:
            old = self._jobs.get(platform)
            if old and old.get("proc") and old["proc"].poll() is None:
                self._kill(old["proc"])
            job = {"platform": platform, "proc": None, "qr": None,
                   "status": "starting", "lines": [], "error": None}
            self._jobs[platform] = job
        if not _LOGIN_SCRIPT.exists():
            job["status"] = "failed"
            job["error"] = f"缺少登录脚本：{_LOGIN_SCRIPT}"
            return job
        if not _MC_PYTHON.exists():
            job["status"] = "failed"
            job["error"] = f"缺少 MediaCrawler 解释器：{_MC_PYTHON}"
            return job
        cmd = [str(_MC_PYTHON), str(_LOGIN_SCRIPT),
               "--platform", platform, "--lt", "qrcode", "--type", "search"]
        try:
            proc = subprocess.Popen(
                cmd, cwd=str(_MC_DIR),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        except OSError as exc:
            job["status"] = "failed"
            job["error"] = str(exc)
            return job
        job["proc"] = proc
        threading.Thread(target=self._reader, args=(job,), daemon=True).start()
        return job

    def poll_login(self, platform: str) -> dict:
        """返回该平台最近一次登录任务的进度（不含 proc，避免给前端暴露句柄）。"""
        with self._lock:
            job = self._jobs.get(platform)
            if not job:
                return {"status": "idle"}
            return {"status": job["status"], "qr": job["qr"],
                    "error": job["error"]}

    def _reader(self, job: dict) -> None:
        """后台读 stdout：QR 行→存二维码；LOGGED_IN→登录成功。"""
        proc = job["proc"]
        try:
            for line in proc.stdout:  # bufsize=1 逐行读
                line = line.strip()
                job["lines"].append(line)
                if line.startswith("QR:"):
                    job["qr"] = line[3:]
                    job["status"] = "qr_ready"
                elif line == "LOGGED_IN":
                    job["status"] = "logged_in"
            proc.wait()
        except Exception as exc:  # 读管道异常也按失败处理
            job["error"] = str(exc)
        # 进程结束但没成功登录：出过码→过期；否则→失败
        if job["status"] != "logged_in":
            job["status"] = "expired" if job["qr"] else "failed"
            if not job["error"]:
                job["error"] = "登录超时或失败"

    @staticmethod
    def _kill(proc: subprocess.Popen) -> None:
        try:
            proc.kill()
        except Exception:
            pass
