"""在独立的 Chrome 或 Edge 用户目录中打开平台官方登录页。"""
import argparse
import os
import subprocess
from pathlib import Path

PAGES = {"bili": "https://passport.bilibili.com/login", "wb": "https://weibo.com/login.php",
         "zhihu": "https://www.zhihu.com/signin", "xhs": "https://www.xiaohongshu.com/explore"}


def main():
    """等待用户关闭专用窗口，再由账号管理器验证真实登录状态。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", required=True, choices=PAGES)
    parser.add_argument("--profile", type=Path, required=True)
    args = parser.parse_args()
    for name in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        for rel in ("Google/Chrome/Application/chrome.exe", "Microsoft/Edge/Application/msedge.exe"):
            base = os.environ.get(name)
            if not base or not (exe := Path(base) / rel).is_file():
                continue
            proc = subprocess.Popen([str(exe), f"--user-data-dir={args.profile.resolve()}",
                                     "--no-first-run", "--no-default-browser-check", "--disable-background-mode",
                                     "--new-window", PAGES[args.platform]])
            print("WINDOW_OPEN", flush=True)
            if proc.wait() != 0:
                raise SystemExit("FATAL:专用浏览器异常退出")
            print("VERIFY_NOW", flush=True)
            return
    raise SystemExit("FATAL:请安装 Chrome 或 Edge 后重新登录")


if __name__ == "__main__":
    main()
