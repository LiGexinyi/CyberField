"""共享路径与默认值；仅声明配置，不创建目录或读取凭据。

保留原默认值。来源自己的分页/筛选规则仍留在对应适配器，避免误共用。
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
WEB_DIR = PROJECT_ROOT / "web"
COLLECT_DB = DATA_DIR / "collect.db"
ACCOUNT_STATE_FILE = DATA_DIR / "accounts.json"
MEDIACRAWLER_DIR = Path(r"D:\Projects\MediaCrawler")
MEDIACRAWLER_PYTHON = MEDIACRAWLER_DIR / ".venv" / "Scripts" / "python.exe"
LOGIN_SCRIPT = MEDIACRAWLER_DIR / "login_standalone.py"
# 知乎登录改用 CyberField 自建脚本（外部 MediaCrawler 的知乎二维码读取
# 在部分页面会超时崩溃，自建脚本直连 passport 扫码页并支持窗口内扫码兜底）。
ZHIHU_LOGIN_SCRIPT = PROJECT_ROOT / "tools" / "zhihu_login_standalone.py"
VERIFY_SCRIPT = MEDIACRAWLER_DIR / "verify_session.py"
# 小红书/知乎登录态搜索脚本（轻量：只取搜索列表，复用 MediaCrawler 客户端）。
XHS_SEARCH_SCRIPT = PROJECT_ROOT / "tools" / "xhs_search_standalone.py"
ZHIHU_SEARCH_SCRIPT = PROJECT_ROOT / "tools" / "zhihu_search_standalone.py"
XHS_JSONL_DIR = MEDIACRAWLER_DIR / "data" / "xhs" / "jsonl"
DEFAULT_PAGE_SIZE = 20
# 网页搜索主词每个平台的目标采集条数（多平台混合分页至少要凑出 10+ 页）。
SEARCH_COLLECT_PER_SOURCE = 80
SEARCH_PLATFORMS = ("xhs", "bili", "zhihu", "douban", "wb")
SEARCH_SOURCES = ("xhs_api", "bilibili_api", "zhihu_api", "douban_api", "weibo_api")
MAX_SEARCH_WORDS = 6
MAX_COMMENTS = 3
ENRICHMENT_WORKERS = 4
# 搜索缓存规则（阶段4）：TTL/容量/失败冷却，避免重复采集且缓存有界。
SEARCH_CACHE_TTL = 300           # 结果缓存有效期（秒），过期后再次访问自动重搜
SEARCH_CACHE_MAX_ENTRIES = 32    # 最多同时缓存的搜索词数
SEARCH_FAIL_RETRY_SECS = 10      # 失败结果冷却期（秒），冷却后再访问才重试
SEARCH_INFLIGHT_TIMEOUT = 120    # 等待同词并发搜索完成的最长秒数（防御性）
SEARCH_COLLECT_WORKERS = 3       # 一次搜索内并行采集的并发数（控制平台请求并发）
DEFAULT_LLM_BASE = "https://api.deepseek.com/v1"
DEFAULT_LLM_MODEL = "deepseek-chat"
