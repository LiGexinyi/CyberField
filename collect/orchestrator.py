"""多源调度器：并行调所有启用源 → 合并 → 去重 → 入库。

容错约定：
- 单个源失败（SourceUnavailable）→ 记录原因、跳过该源，其余源照常；
- 结果按 (platform, url) 去重，保证"多源冗余"不会重复入库；
- 每条记录带 source_adapter 与 keyword，可追溯。
"""

import logging

from collect.sources.base_source import SourceUnavailable
from collect.sources import create_source

logger = logging.getLogger(__name__)


def collect(keyword: str,
            platforms: tuple = ("xhs",),
            limit: int = 20,
            source_names: tuple = ("mediacrawler",),
            source_kwargs: dict | None = None,
            save: bool = True):
    """执行一次多源采集。

    参数：
        keyword       搜索关键词
        platforms     MediaCrawler 平台码元组（xhs / bili / wb / zhihu ...）
        limit         每个平台最多采集条数
        source_names  启用的适配器名
        source_kwargs 传给适配器构造器的参数（如 mc_dir / mc_python）
        save          是否入库（默认入库）
    返回：
        (posts, errors, summary)
        posts  去重后的统一 Post 列表
        errors 各源失败原因列表
        summary 入库统计（save=False 时为 None）
    """
    errors: list[str] = []
    posts = []
    for name in source_names:
        try:
            src = create_source(name, **(source_kwargs or {}))
        except Exception as exc:  # 适配器构造失败，记录并跳过
            errors.append(f"{name}: 初始化失败 {exc}")
            continue
        if not src.health_check():
            errors.append(f"{name}: 健康检查失败（工具缺失或路径错误）")
            continue
        for platform in platforms:
            try:
                got = src.search(keyword, platform=platform, limit=limit)
                posts.extend(got)
                logger.info("[%s/%s] 命中 %d 条", src.name, platform, len(got))
            except SourceUnavailable as exc:
                errors.append(f"{src.name}/{platform}: {exc}")
            except Exception as exc:
                errors.append(f"{src.name}/{platform}: 意外异常 {exc}")

    # 按 (platform, url) 去重，保留首次出现。
    seen, uniq = set(), []
    for p in posts:
        key = (p.platform, p.url)
        if key not in seen:
            seen.add(key)
            uniq.append(p)

    summary = None
    if save and uniq:
        from collect import store
        summary = store.save_posts(uniq)

    return uniq, errors, summary
