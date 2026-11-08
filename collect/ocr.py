"""轻量 OCR 模块：识别小红书笔记图片里的文字。

小红书的观点输出常以图片承载（长图、总结图、表情包配字），
本模块用 RapidOCR（onnxruntime CPU 版）对笔记的图片做文字识别，
把识别结果作为 extra["ocr_text"] 附加到 Post，参与检索与分析。

设计：
    - 懒加载模型：未安装 rapidocr 或首次导入不阻塞主流程；
    - 按图片 URL 缓存识别结果：同一张图只识别一次（批量采集避免重复）；
    - 任何失败（下载 / 识别）都降级返回空列表，不中断采集。
"""

import threading
import urllib.request

# 图片防盗链需要的浏览器头。
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
    "Referer": "https://www.xiaohongshu.com/explore",
}

_engine = None
_engine_lock = threading.Lock()
# URL -> 识别结果缓存（同一张图只识别一次）。
_cache: dict[str, list[str]] = {}
_cache_lock = threading.Lock()
# 默认每笔记最多识别前几张图（观点长图一般在前面）。
_MAX_IMAGES = 3


def _get_engine():
    """懒加载 RapidOCR 引擎；未安装时抛 ImportError（由调用方降级）。"""
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                from rapidocr_onnxruntime import RapidOCR
                _engine = RapidOCR()
    return _engine


def download_image(url: str, timeout: int = 20) -> bytes:
    """下载图片（带防盗链请求头）。失败抛异常，由调用方降级。"""
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def ocr_bytes(data: bytes) -> list[str]:
    """识别图片字节中的文字，返回按行排好的非空文字列表。"""
    try:
        engine = _get_engine()
    except Exception:
        return []
    try:
        result, _ = engine(data)
    except Exception:
        return []
    if not result:
        return []
    return [str(item[1]).strip() for item in result
            if item and len(item) > 1 and str(item[1]).strip()]


def ocr_image_url(url: str) -> list[str]:
    """识别单张图片（带缓存）。失败降级返回空。"""
    with _cache_lock:
        if url in _cache:
            return list(_cache[url])
    try:
        data = download_image(url)
        lines = ocr_bytes(data)
    except Exception:
        lines = []
    with _cache_lock:
        _cache[url] = lines
    return list(lines)


def ocr_note_images(image_list_str: str, max_images: int = _MAX_IMAGES) -> list[str]:
    """对笔记的图片列表逐张 OCR，合并去重后的文字列表。"""
    urls = [u.strip() for u in (image_list_str or "").split(",") if u.strip()]
    lines: list[str] = []
    for u in urls[:max_images]:
        for t in ocr_image_url(u):
            if t not in lines:
                lines.append(t)
    return lines
