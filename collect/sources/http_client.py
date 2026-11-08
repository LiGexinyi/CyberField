"""轻量 HTTP 会话工具（纯标准库实现，无需第三方依赖）。

为「游客态公开接口」类适配器（B站 / 豆瓣等）提供统一请求能力：
1. 自动保存并携带 Cookie（模拟浏览器会话，如 B站 buvid3）；
2. 自动附加 User-Agent / Referer（部分接口要求 Referer 才放行）；
3. 自动解压 gzip 响应（B站接口返回 gzip）。

只用于访问各平台公开、免登录的数据接口；不绕过任何登录或验证码。
"""

import gzip
import http.cookiejar
import json
import urllib.parse
import urllib.request

# 默认浏览器 UA：部分接口要求真实浏览器标识，否则 403。
DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36")


class HttpSession:
    """带 Cookie 存储的 HTTP 会话。

    用法：
        session = HttpSession()
        session.get("https://www.bilibili.com/")          # 先访问主页拿 cookie
        data = session.get_json("https://api.bilibili.com/...",
                                params={...}, referer="https://www.bilibili.com/")
    """

    def __init__(self, ua: str = DEFAULT_UA, timeout: int = 20):
        """参数：
            ua       User-Agent 字符串
            timeout  单次请求超时秒数
        """
        # CookieJar：请求响应里 Set-Cookie 的 cookie 会自动保存并在后续请求携带。
        self._jar = http.cookiejar.CookieJar()
        self._ua = ua
        self._timeout = timeout
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._jar))

    def get_cookie(self, name: str) -> str | None:
        """读取当前会话里的某个 Cookie 值，没有返回 None（供访客激活校验用）。"""
        for c in self._jar:
            if c.name == name:
                return c.value
        return None

    def get(self, url: str, params: dict | None = None,
            referer: str | None = None, accept: str = "*/*") -> tuple[int, str]:
        """GET 请求，返回 (HTTP 状态码, 响应文本)。

        参数：
            url      目标地址（可含查询串）
            params   追加的查询参数（会自动 urlencode）
            referer  模拟从哪个页面跳转过来（部分接口强制校验）
            accept   Accept 头
        """
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        headers = {
            "User-Agent": self._ua,
            "Accept": accept,
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        if referer:
            headers["Referer"] = referer
        req = urllib.request.Request(url, headers=headers)
        with self._opener.open(req, timeout=self._timeout) as resp:
            body = resp.read()
            # gzip 响应解压后才是可读文本。
            if resp.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            return resp.status, body.decode("utf-8", errors="replace")

    def get_json(self, url: str, params: dict | None = None,
                 referer: str | None = None) -> dict:
        """GET 并把响应解析为 JSON 对象，失败抛 RuntimeError。"""
        status, text = self.get(
            url, params, referer,
            accept="application/json, text/plain, */*")
        if status != 200:
            raise RuntimeError(f"HTTP {status}: {url}")
        data = json.loads(text)
        if not isinstance(data, dict):
            raise RuntimeError(f"响应不是 JSON 对象: {url}")
        return data
