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
import logging
import os
import shutil
import subprocess
import threading
import time
from collections import deque
from datetime import datetime
from collect import settings

logger = logging.getLogger(__name__)

_MC_DIR = settings.MEDIACRAWLER_DIR
_MC_PYTHON = settings.MEDIACRAWLER_PYTHON
_LOGIN_SCRIPT = settings.LOGIN_SCRIPT
_ZHIHU_LOGIN_SCRIPT = settings.ZHIHU_LOGIN_SCRIPT
_VERIFY_SCRIPT = settings.VERIFY_SCRIPT
_STATE_FILE = settings.ACCOUNT_STATE_FILE

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
     "search_mode": "登录态搜索", "note": "登录请关闭代理；登录后网页搜索含小红书"},
    {"platform": "zhihu", "label": "知乎", "login_supported": True,
     "search_mode": "登录态搜索", "note": "登录后网页搜索含知乎"},
    {"platform": "bili", "label": "B站", "login_supported": True,
     "search_mode": "游客模式", "note": "请在专用窗口内登录"},
    {"platform": "wb", "label": "微博", "login_supported": True,
     "search_mode": "游客模式", "note": "游客态易被拦截(432)"},
    {"platform": "douban", "label": "豆瓣", "login_supported": False,
     "search_mode": "游客模式", "note": "暂不支持登录"},
]

_LOGIN_READY_MARK = "LOGGED_IN"


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class AccountManager:
    """按平台串行接收操作，用任务代次阻止过期工作线程回写。"""
    def __init__(self):
        """初始化进程/线程跟踪及平台锁，不启动浏览器或网络请求。"""
        self._lock = threading.RLock()
        self._operations = {i["platform"]: threading.RLock() for i in PLATFORM_INFO if i["login_supported"]}
        self._generations = {}
        self._login_jobs = {}
        self._verify_procs = {}
        self._threads = set()
        self._state = {}
        self._closed = False
        self._load_state()

    def _default_state(self):
        """构造独立的默认状态。"""
        return {"state": "no_profile", "nickname": None, "last_verified_at": None, "error": None}

    def _load_state(self):
        """恢复持久化信息；进程重启后不能继续声称正在验证。"""
        try:
            data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return
            for info in PLATFORM_INFO:
                value = data.get(info["platform"])
                if isinstance(value, dict):
                    state = self._default_state()
                    state.update({k: value.get(k, state[k]) for k in state})
                    if state["state"] not in STATE_LABELS or state["state"] == "verifying":
                        state["state"] = "pending"
                    self._state[info["platform"]] = state
        except (OSError, ValueError):
            # 状态文件缺失/损坏按空状态启动，但必须留痕（不含凭据）。
            logger.warning("账号状态文件读取失败，按空状态启动", exc_info=True)

    def _save_state(self):
        """持锁写入临时文件后替换，避免半份状态文件。"""
        try:
            _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            temporary = _STATE_FILE.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(self._state, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(_STATE_FILE)
        except OSError:
            # 状态落盘失败不影响内存态，但要可排查（例如磁盘满/权限）。
            logger.warning("账号状态写入失败", exc_info=True)

    def accounts(self):
        """返回状态快照，不暴露进程、线程和会话凭据。"""
        with self._lock:
            return [{**info, **self._state.get(info["platform"], self._default_state()),
                     "state_label": STATE_LABELS.get(self._state.get(info["platform"], self._default_state())["state"], "待验证")}
                    for info in PLATFORM_INFO]

    def platform_state(self, platform):
        """读取单平台状态副本。"""
        with self._lock:
            state = self._state.get(platform, self._default_state())
            return {**state, "state_label": STATE_LABELS.get(state["state"], state["state"])}

    def _operation(self, platform):
        """仅允许已登记且支持登录的平台执行档案操作。"""
        if platform not in self._operations:
            raise ValueError("不支持的平台或登录操作")
        return self._operations[platform]

    def browser_dir(self, platform):
        """取得固定平台专用目录，拒绝任意路径输入。"""
        self._operation(platform)
        return _MC_DIR / "browser_data" / f"{platform}_user_data_dir"

    def _current(self, platform, generation):
        """调用方持锁判断任务是否仍有效。"""
        return not self._closed and self._generations.get(platform) == generation

    def _advance(self, platform):
        """使旧任务失效并停止其进程；调用方持平台操作锁。"""
        with self._lock:
            if self._closed:
                raise RuntimeError("账号服务已关闭")
            generation = self._generations.get(platform, 0) + 1
            self._generations[platform] = generation
            old = self._login_jobs.get(platform)
            processes = [self._verify_procs.get(platform)]
            if old:
                old["status"], old["qr"] = "cancelled", None
                old["superseded"] = True   # 标记已被新操作替换，迟到取消不再生效
                processes.append(old.get("proc"))
        for process in processes:
            if process is not None:
                self._kill(process)
        return generation

    def _start_thread(self, target, *args):
        """跟踪工作线程；调用方持锁，以免关闭遗漏刚启动任务。"""
        def run():
            """无论工作成功与否，都移除线程引用。"""
            try:
                target(*args)
            finally:
                with self._lock:
                    self._threads.discard(threading.current_thread())
        thread = threading.Thread(target=run, daemon=True)
        self._threads.add(thread)
        thread.start()

    def start_login(self, platform):
        """串行启动专用扫码登录；新操作使旧读管道任务失效。"""
        with self._operation(platform):
            with self._lock:
                previous = dict(self._state.get(platform, self._default_state()))
            generation = self._advance(platform)
            job = {"platform": platform, "generation": generation, "proc": None, "qr": None,
                   "qr_error": None, "status": "starting", "error": None, "prev_snapshot": previous}
            with self._lock:
                if not self._current(platform, generation):
                    raise RuntimeError("账号服务已关闭")
                self._login_jobs[platform] = job
                script = settings.PROJECT_ROOT / "tools" / "platform_login.py"
                if not script.exists() or not _MC_PYTHON.exists():
                    job.update(status="failed", error="缺少登录脚本或验证环境")
                    self._set_state(platform, "login_failed", None, job["error"])
                    return dict(job)
                cmd = [str(_MC_PYTHON), "-B", "-X", "utf8", str(script),
                       "--platform", platform, "--profile", str(self.browser_dir(platform))]
                try:
                    # 创建与登记在同一临界区，退出/关闭始终能找到进程。
                    job["proc"] = subprocess.Popen(
                        cmd,
                        cwd=str(_MC_DIR), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, encoding="utf-8", errors="replace", bufsize=1,
                        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
                except OSError:
                    job.update(status="failed", error="无法启动登录进程")
                    self._set_state(platform, "login_failed", None, job["error"])
                    return dict(job)
                self._start_thread(self._login_reader, job)
                return dict(job)

    def _login_reader(self, job):
        """仅允许当前登录任务更新二维码和认证结果。"""
        platform, generation, process = job["platform"], job["generation"], job["proc"]
        tail = deque(maxlen=15)   # 保留最近输出行，失败时从中提取可读原因
        try:
            for line in process.stdout:
                with self._lock:
                    if not self._current(platform, generation):
                        return
                    line = line.strip()
                    if line.startswith("QR:"):
                        job.update(qr=line[3:], status="qr_ready", qr_error=None)
                    elif line.startswith("QR_MISSING:"):
                        # 未能截取到二维码：浏览器窗口保留，可窗口内扫码完成登录。
                        job.update(status="qr_missing",
                                   qr_error=line[len("QR_MISSING:"):].strip()
                                   or "未能读取到二维码")
                    elif line == "WINDOW_OPEN":
                        job.update(status="window_open")
                    elif line in (_LOGIN_READY_MARK, "VERIFY_NOW"):
                        job["status"] = "logged_in"
                    else:
                        tail.append(line)   # 供失败诊断，不缓存二维码大段 base64
            code = process.wait()
        except Exception:
            logger.exception("登录输出读取线程异常（platform=%s）", platform)
            code = -1
        with self._lock:
            if not self._current(platform, generation):
                return
            success = code == 0 and job["status"] == "logged_in"
            if not success:
                reason = self._pick_login_failure(tail, job.get("qr_error"))
                job["status"] = "expired" if job.get("qr") else "failed"
                job["error"] = reason
                self._set_state(platform, "expired" if job.get("qr") else "login_failed",
                                None, reason)
        if success:
            # 获取平台锁前释放全局锁，避免与退出操作互相等待。
            self._begin_verify(platform, expected=generation)

    @staticmethod
    def _pick_login_failure(tail, qr_error):
        """从脚本输出尾部提取一条可读的登录失败原因。"""
        hints = ("fatal", "have not found", "not found", "login failed", "timeout",
                 "traceback", "error", "failed", "denied", "unavailable",
                 "异常", "超时", "扫码")
        for line in tail:
            low = line.lower()
            if any(h in low for h in hints):
                return line[:200]
        if qr_error:
            return f"未能读取二维码：{qr_error}"
        if tail:
            return tail[-1][:200]
        return "登录超时或失败"

    def poll_login(self, platform):
        """返回登录进度及验证状态，不返回进程句柄。"""
        with self._lock:
            state = self.platform_state(platform)
            job = self._login_jobs.get(platform)
            return {**state, "status": job["status"] if job else "idle",
                    "qr": job["qr"] if job else None,
                    "error": job["error"] if job else state["error"],
                    "qr_error": job.get("qr_error") if job else None}

    def cancel_login(self, platform):
        """取消进行中的登录；任务终态或已被新操作替换时取消无副作用。

        修复的迟到场景：
        - 原先已登录 → 发起重新登录 → 退出 → 迟到取消：退出已作废任务并删除
          档案，取消不再恢复旧登录快照（恢复会"复活"已退出的登录态）。
        - 登录与自动验证均已完成后的迟到取消：不再回写登录前快照。
        - 登录失败/过期后的取消仍按原行为恢复登录前快照（未建立登录态，
          恢复无害，历史行为保留）。
        """
        with self._operation(platform):
            with self._lock:
                job = self._login_jobs.get(platform)
                state = dict(self._state.get(platform, self._default_state()))
            if job is None or job.get("superseded") or job.get("status") == "cancelled":
                # 没有进行中的登录任务（从未开始 / 已被退出等新操作替换 / 已取消）。
                return {"ok": True, "platform": platform, "cancelled": False,
                        "note": "没有进行中的登录任务"}
            if job.get("status") == "logged_in" and state["state"] != "verifying":
                # 登录与自动验证均已完成，取消不再回写登录前快照。
                return {"ok": True, "platform": platform, "cancelled": False,
                        "note": "登录已完成，无需取消"}
            previous = dict(job["prev_snapshot"])
            generation = self._advance(platform)
            with self._lock:
                if self._current(platform, generation):
                    if previous["state"] == "verifying":
                        previous["state"] = "pending"
                    previous["error"] = "已取消登录"
                    self._state[platform] = previous
                    self._save_state()
            return {"ok": True, "platform": platform, "cancelled": True}

    def start_verify(self, platform):
        """开始新验证；同平台新任务使此前验证结果失效。"""
        return self._begin_verify(platform)

    def _begin_verify(self, platform, expected=None):
        """自动验证沿用登录代次，手动验证创建新代次。"""
        with self._operation(platform):
            if expected is None:
                generation = self._advance(platform)
            else:
                generation = expected
            with self._lock:
                if not self._current(platform, generation):
                    return {"ok": False, "platform": platform}
                self._set_state(platform, "verifying", None, None)
                self._start_thread(self._verify_worker, platform, generation)
            return {"ok": True, "platform": platform}

    def _verify_worker(self, platform, generation):
        """验证结果必须属于当前代次才可回写。"""
        try:
            result = self._run_verify(platform, generation)
        except Exception:
            # 兜底映射为 network，但内部 bug 必须在日志里可见。
            logger.exception("验证工作线程内部异常（platform=%s）", platform)
            result = {"kind": "network", "nickname": None, "error": "验证进程异常"}
        with self._lock:
            if self._current(platform, generation):
                self.apply_verify_result(platform, result.get("kind", "network"), result.get("nickname"), result.get("error"))

    def apply_verify_result(self, platform, kind, nickname, error):
        """统一映射验证结果；网络错误保留昵称并标记未知。"""
        with self._lock:
            mapped = {"ok": "logged_in", "missing": "no_profile", "invalid": "expired"}
            self._set_state(platform, mapped.get(kind, "unknown"), nickname,
                            None if kind == "ok" else error, verified=True)

    def _run_verify(self, platform, generation=None):
        """启动可跟踪验证进程，最多等待90秒并解析结构化输出。"""
        if not _VERIFY_SCRIPT.exists():
            return {"kind": "network", "error": "缺少验证脚本"}
        with self._lock:
            if generation is not None and not self._current(platform, generation):
                return {"kind": "cancelled"}
            process = subprocess.Popen(
                [str(_MC_PYTHON), str(_VERIFY_SCRIPT), "--platform", platform], cwd=str(_MC_DIR),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
            self._verify_procs[platform] = process
        try:
            output, _ = process.communicate(timeout=90)
        except subprocess.TimeoutExpired:
            self._kill(process)
            return {"kind": "network", "error": "验证超时（90s）"}
        finally:
            with self._lock:
                if self._verify_procs.get(platform) is process:
                    self._verify_procs.pop(platform, None)
        if process.returncode == 0:
            for line in (output or "").splitlines():
                if line.startswith("VERIFY:"):
                    try:
                        result = json.loads(line[len("VERIFY:"):])
                        if isinstance(result, dict):
                            return result
                    except ValueError:
                        break
        return {"kind": "network", "error": "验证脚本未返回有效结果"}

    def poll_verify(self, platform):
        """查询最近验证状态。"""
        return self.platform_state(platform)

    def logout(self, platform):
        """先使任务失效，再清理已确认路径内的专用档案。"""
        with self._operation(platform):
            generation = self._advance(platform)
            profile = self.browser_dir(platform)
            parent = (_MC_DIR / "browser_data").resolve()
            # 即使平台来自白名单，也检查最终路径，禁止跟随档案符号链接。
            if profile.is_symlink() or profile.resolve() != parent / f"{platform}_user_data_dir":
                raise ValueError("专用档案路径不安全")
            removed = False
            for _ in range(6):
                if not profile.exists():
                    removed = True
                    break
                shutil.rmtree(profile, ignore_errors=True)
                if not profile.exists():
                    removed = True
                    break
                time.sleep(1)
            with self._lock:
                if self._current(platform, generation):
                    self._set_state(platform, "no_profile" if removed else "pending", None,
                                    "已退出登录" if removed else "档案被占用，请稍后重试")
            return {"ok": removed, "platform": platform}

    def close(self, timeout=2.0):
        """使所有任务失效，停止本管理器拥有的进程；不删除登录档案。"""
        with self._lock:
            if not self._closed:
                self._closed = True
                for platform in self._generations:
                    self._generations[platform] += 1
                for job in self._login_jobs.values():
                    job.update(status="cancelled", qr=None)
                for state in self._state.values():
                    if state["state"] == "verifying":
                        state["state"] = "pending"
                if self._state:
                    self._save_state()
            processes = list(self._verify_procs.values()) + [j.get("proc") for j in self._login_jobs.values()]
            threads = list(self._threads)
        for process in processes:
            if process is not None:
                self._kill(process)
        deadline = time.monotonic() + max(0, timeout)
        for thread in threads:
            thread.join(timeout=max(0, deadline - time.monotonic()))
        return not any(thread.is_alive() for thread in threads)

    def _set_state(self, platform, state, nickname, error, verified=False):
        """更新状态；验证中和网络未知保留已知昵称。

        verified 仅由 apply_verify_result 传 True：只有真实验证结果才更新
        “最近验证时间”，登录失败/取消/退出等非验证操作不得冒充验证记录。
        """
        with self._lock:
            record = self._state.setdefault(platform, self._default_state())
            record["state"] = state
            if state not in ("unknown", "verifying") or nickname is not None:
                record["nickname"] = nickname
            record["error"] = error
            if verified:
                record["last_verified_at"] = _now_iso()
            self._save_state()

    @staticmethod
    def _kill(process):
        """只结束本管理器持有的子进程树并限时回收，不扫描全机浏览器。"""
        try:
            if process.poll() is not None:
                return
            # Windows停止脚本时连同其子进程结束，避免只杀Python留下专用浏览器。
            pid = getattr(process, "pid", None)
            if os.name == "nt" and type(pid) is int and pid > 0:
                try:
                    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   timeout=2, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                except (OSError, subprocess.TimeoutExpired):
                    logger.debug("taskkill 结束进程树失败", exc_info=True)
            if process.poll() is None:
                process.kill()
            process.wait(timeout=1)
        except (OSError, subprocess.TimeoutExpired):
            logger.debug("子进程回收失败", exc_info=True)
