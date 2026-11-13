"""平台账号状态机与登录 / 验证 / 退出管理。

状态机（7 态，字段 state）：
    no_profile  未登录     无专用登录档案，或档案已被清除
    pending     待验证     有档案但尚未验证有效 / 上次验证被中断
    verifying   验证中     正在执行 verify_session.py
    logged_in   已登录     验证通过（会话有效，采集可用登录态）
    expired     已过期     验证明确失败（平台接口返回未登录）
    login_failed 登录失败  扫码登录流程失败
    unknown     状态未知   网络错误 / 平台风控 / 验证异常（≠失效）

原则：
- cookie 文件存在 ≠ 已登录；只有 verify_session.py 的 pong 校验通过才算
  logged_in。
- 网络错误映射为 unknown，绝不因网络错误把已登录降级为已过期。
- 状态持久化到 data/accounts.json（已被 .gitignore 排除），仅存状态/昵称/
  最近验证时间/错误文本，不存任何 cookie 值。
- 登录 / 验证 / 退出共用 MediaCrawler 的 browser_data/{platform}_user_data_dir
  专用档案，与日常浏览器隔离；退出只删该平台档案，不影响采集资料与其他平台。

本模块不保存、不打印、不返回任何凭据；二维码 base64 只在登录轮询接口中
临时返回给前端（展示后即弃）。
"""

import json
import os
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

_MC_DIR = Path(r"D:\Projects\MediaCrawler")
_MC_PYTHON = _MC_DIR / ".venv" / "Scripts" / "python.exe"
_LOGIN_SCRIPT = _MC_DIR / "login_standalone.py"
_VERIFY_SCRIPT = _MC_DIR / "verify_session.py"
_STATE_FILE = Path(__file__).resolve().parent.parent / "data" / "accounts.json"

STATE_LABELS = {
    "no_profile": "未登录",
    "pending": "待验证",
    "verifying": "验证中",
    "logged_in": "已登录",
    "expired": "已过期",
    "login_failed": "登录失败",
    "unknown": "状态未知",
}

# 平台元数据：登录支持情况 + 网页搜索模式（登录态不可用的明确标注）
PLATFORM_INFO = [
    {"platform": "xhs", "label": "小红书", "login_supported": True,
     "search_mode": "未接入网页搜索", "note": "登录请关闭代理"},
    {"platform": "zhihu", "label": "知乎", "login_supported": True,
     "search_mode": "未接入网页搜索", "note": ""},
    {"platform": "bili", "label": "B站", "login_supported": True,
     "search_mode": "游客模式", "note": "登录后可解锁 AI 总结"},
    {"platform": "wb", "label": "微博", "login_supported": True,
     "search_mode": "游客模式", "note": "游客态易被拦截(432)"},
    {"platform": "douban", "label": "豆瓣", "login_supported": False,
     "search_mode": "游客模式", "note": "暂不支持登录"},
]

_LOGIN_READY_MARK = "LOGGED_IN"


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class AccountManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._login_jobs: dict[str, dict] = {}
        self._verify_procs: dict[str, subprocess.Popen] = {}
        self._state: dict[str, dict] = {}
        self._load_state()

    # ------------------------------------------------------------ 状态存取
    def _default_state(self) -> dict:
        return {"state": "no_profile", "nickname": None,
                "last_verified_at": None, "error": None}

    def _load_state(self) -> None:
        try:
            if _STATE_FILE.exists():
                data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
                for plat in PLATFORM_INFO:
                    st = data.get(plat["platform"])
                    if isinstance(st, dict):
                        base = self._default_state()
                        base.update({k: st.get(k, base[k]) for k in base})
                        self._state[plat["platform"]] = base
        except (OSError, ValueError):
            pass

    def _save_state(self) -> None:
        try:
            _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            _STATE_FILE.write_text(
                json.dumps(self._state, ensure_ascii=False, indent=2),
                encoding="utf-8")
        except OSError:
            pass

    def accounts(self) -> list[dict]:
        with self._lock:
            out = []
            for info in PLATFORM_INFO:
                st = self._state.get(info["platform"], self._default_state())
                out.append({**info, "state": st["state"],
                            "state_label": STATE_LABELS.get(
                                st["state"], st["state"]),
                            "nickname": st["nickname"],
                            "last_verified_at": st["last_verified_at"],
                            "error": st["error"]})
            return out

    def platform_state(self, platform: str) -> dict:
        with self._lock:
            st = self._state.get(platform, self._default_state())
            return {**st, "state_label": STATE_LABELS.get(st["state"], st["state"])}

    # ------------------------------------------------------------ 专用档案
    def browser_dir(self, platform: str) -> Path:
        return _MC_DIR / "browser_data" / f"{platform}_user_data_dir"

    # ------------------------------------------------------------ 登录流程
    def start_login(self, platform: str) -> dict:
        with self._lock:
            old = self._login_jobs.get(platform)
            if old and old.get("proc") and old["proc"].poll() is None:
                self._kill(old["proc"])
            # 记住登录前的状态，取消时还原
            prev = self._state.get(platform, self._default_state())["state"]
            job = {"platform": platform, "proc": None, "qr": None,
                   "status": "starting", "lines": [], "error": None,
                   "prev_state": prev}
            self._login_jobs[platform] = job
        if not _LOGIN_SCRIPT.exists():
            job["status"] = "failed"
            job["error"] = f"缺少登录脚本：{_LOGIN_SCRIPT}"
            self._set_state(platform, "login_failed", None,
                            job["error"])
            return job
        if not _MC_PYTHON.exists():
            job["status"] = "failed"
            job["error"] = f"缺少 MediaCrawler 解释器：{_MC_PYTHON}"
            self._set_state(platform, "login_failed", None, job["error"])
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
            self._set_state(platform, "login_failed", None, str(exc))
            return job
        job["proc"] = proc
        threading.Thread(target=self._login_reader, args=(job,),
                         daemon=True).start()
        return job

    def _login_reader(self, job: dict) -> None:
        proc = job["proc"]
        try:
            for line in proc.stdout:
                line = line.strip()
                job["lines"].append(line)
                if line.startswith("QR:"):
                    job["qr"] = line[3:]
                    job["status"] = "qr_ready"
                elif line == _LOGIN_READY_MARK:
                    job["status"] = "logged_in"
            proc.wait()
        except Exception as exc:
            job["error"] = str(exc)
        if job["status"] == "logged_in":
            # 认证完成 → 自动触发真实验证（pong），结果决定 logged_in/pending 等
            self.start_verify(job["platform"])
        elif job["status"] == "cancelled":
            # 用户取消：状态还原已由 cancel_login 完成，reader 不再覆写
            return
        else:
            # 进程结束但未成功：出过码→过期；否则→失败
            if job["qr"]:
                job["status"] = "expired"
                self._set_state(job["platform"], "expired", None,
                                "登录超时，二维码已过期")
            else:
                job["status"] = "failed"
                self._set_state(job["platform"], "login_failed", None,
                                job.get("error") or "登录失败")

    def poll_login(self, platform: str) -> dict:
        with self._lock:
            job = self._login_jobs.get(platform)
            st = self._state.get(platform, self._default_state())
            base = {"state": st["state"],
                    "state_label": STATE_LABELS.get(st["state"], st["state"]),
                    "nickname": st["nickname"],
                    "last_verified_at": st["last_verified_at"]}
            if not job:
                return {"status": "idle", "qr": None, "error": None, **base}
            return {"status": job["status"], "qr": job["qr"],
                    "error": job["error"], **base}

    def cancel_login(self, platform: str) -> dict:
        with self._lock:
            job = self._login_jobs.get(platform)
            prev = "no_profile"
            if job:
                prev = job.get("prev_state") or "no_profile"
                if job.get("proc") and job["proc"].poll() is None:
                    self._kill(job["proc"])
                job["status"] = "cancelled"
        # 取消登录：还原到登录前的已知状态（若是已登录则保持）
        self._set_state(platform, prev if prev in STATE_LABELS else "no_profile",
                        None, "已取消登录")
        return {"ok": True, "platform": platform}

    # ------------------------------------------------------------ 验证流程
    def start_verify(self, platform: str) -> dict:
        """后台执行真实有效性验证（verify_session.py），先置为验证中。"""
        self._set_state(platform, "verifying", None, None)
        threading.Thread(target=self._verify_worker, args=(platform,),
                         daemon=True).start()
        return {"ok": True, "platform": platform}

    def _verify_worker(self, platform: str) -> None:
        try:
            result = self._run_verify(platform)
        except Exception as exc:
            result = {"kind": "network", "valid": False,
                      "nickname": None, "error": f"验证进程异常：{exc}"}
        self.apply_verify_result(platform, result.get("kind", "network"),
                                 result.get("nickname"), result.get("error"))

    def apply_verify_result(self, platform: str, kind: str, nickname, error):
        """把 verify_session 结果映射到状态（纯逻辑，供单测直接调用）。

        ok→已登录 / missing→未登录 / invalid→已过期 / network→状态未知
        （网络错误保留原昵称，不降级为失效）。
        """
        if kind == "ok":
            self._set_state(platform, "logged_in", nickname, None)
        elif kind == "missing":
            self._set_state(platform, "no_profile", None, error)
        elif kind == "invalid":
            self._set_state(platform, "expired", None, error)
        else:
            with self._lock:
                old = self._state.get(platform, self._default_state())
                keep = (old.get("nickname")
                        if old.get("state") == "logged_in" else nickname)
            self._set_state(platform, "unknown", keep, error)

    def _run_verify(self, platform: str) -> dict:
        if not _VERIFY_SCRIPT.exists():
            return {"kind": "network", "valid": False, "nickname": None,
                    "error": f"缺少验证脚本：{_VERIFY_SCRIPT}"}
        cmd = [str(_MC_PYTHON), str(_VERIFY_SCRIPT),
               "--platform", platform]
        proc = subprocess.Popen(
            cmd, cwd=str(_MC_DIR),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        with self._lock:
            self._verify_procs[platform] = proc
        try:
            out, _ = proc.communicate(timeout=90)
        except subprocess.TimeoutExpired:
            self._kill(proc)
            return {"kind": "network", "valid": False, "nickname": None,
                    "error": "验证超时（90s）"}
        finally:
            with self._lock:
                self._verify_procs.pop(platform, None)
        for line in (out or "").splitlines():
            if line.startswith("VERIFY:"):
                try:
                    return json.loads(line[len("VERIFY:"):])
                except ValueError:
                    break
        return {"kind": "network", "valid": False, "nickname": None,
                "error": "验证脚本未返回有效结果"}

    def poll_verify(self, platform: str) -> dict:
        return self.platform_state(platform)

    # ------------------------------------------------------------ 退出登录
    def logout(self, platform: str) -> dict:
        """仅清除该平台专用档案；不动采集资料与其他平台。"""
        with self._lock:
            job = self._login_jobs.get(platform)
            if job and job.get("proc") and job["proc"].poll() is None:
                self._kill(job["proc"])
            vproc = self._verify_procs.get(platform)
            if vproc and vproc.poll() is None:
                self._kill(vproc)
        profile = self.browser_dir(platform)
        removed = False
        for _ in range(6):  # 最多等 6s（chromium 可能短暂占用）
            if not profile.exists():
                removed = True
                break
            shutil.rmtree(profile, ignore_errors=True)
            if not profile.exists():
                removed = True
                break
            time.sleep(1)
        if removed:
            self._set_state(platform, "no_profile", None, "已退出登录")
        else:
            self._set_state(platform, "pending", None,
                            "档案删除失败（可能被占用），请稍后重试")
        return {"ok": removed, "platform": platform}

    # ------------------------------------------------------------ 内部工具
    def _set_state(self, platform: str, state: str, nickname, error) -> None:
        with self._lock:
            st = self._state.setdefault(platform, self._default_state())
            st["state"] = state
            if state != "unknown" or nickname is not None:
                st["nickname"] = nickname
            st["error"] = error
            st["last_verified_at"] = _now_iso()
            self._save_state()

    @staticmethod
    def _kill(proc: subprocess.Popen) -> None:
        try:
            proc.kill()
        except Exception:
            pass
