"""多源调度器：依次调用所有启用源 → 合并 → 去重 → 清洗 →（可选）入库。

容错约定：
- 单个源失败（SourceUnavailable）→ 记录原因、跳过该源，其余源照常；
- 结果按 (platform, url) 去重，保证"多源冗余"不会重复入库；
- 清洗（collect.cleaner）删除空文本并再兜底去重后，才决定是否入库；
- 每条记录带 source_adapter 与 keyword，可追溯。
"""

import logging

from collect.sources.base_source import SourceUnavailable
from collect.sources import create_source

logger = logging.getLogger(__name__)


def collect(keyword: str,
            platforms: tuple = ("xhs",),
            limit: int = 20,
            source_names: tuple | None = None,
            source_kwargs: dict | None = None,
            save: bool = True,
            clean: bool = True):
    """执行一次多源采集。

    参数：
        keyword       搜索关键词
        platforms     平台码元组（MediaCrawler 码 xhs/bili/wb/zhihu/douban ...）
        limit         每个平台最多采集条数
        source_names  启用的适配器名元组；None 表示全部已注册源
        source_kwargs 传给适配器构造器的参数（如 mc_dir / mc_python）
        save          是否入库（默认入库；False = 浏览器模式，用完即弃）
        clean         是否清洗后再返回（默认清洗：删空文本 + 兜底去重 + 排序）
    返回：
        (posts, errors, summary)
        posts  去重+清洗后的统一 Post 列表
        errors 各源失败原因列表
        summary 入库/清洗统计；save=False 时只含清洗统计
    """
    if not isinstance(keyword, str) or not keyword.strip():
        raise ValueError("关键词不能为空")
    if type(limit) is not int or limit <= 0:
        raise ValueError("limit 必须为正整数")
    keyword = keyword.strip()
    # 默认启用全部已注册源：新源登记进 AVAILABLE_SOURCES 后自动参与调度。
    if source_names is None:
        from collect.sources import AVAILABLE_SOURCES
        source_names = tuple(AVAILABLE_SOURCES.keys())
    errors: list[str] = []
    posts = []
    for name in source_names:
        try:
            src = create_source(name, **(source_kwargs or {}))
        except Exception as exc:  # 适配器构造失败，记录并跳过
            errors.append(f"{name}: 初始化失败 {exc}")
            continue
        try:
            healthy = src.health_check()
        except Exception as exc:
            errors.append(f"{name}: 健康检查异常 {exc}")
            continue
        if not healthy:
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

    # 先过滤空正文再去重，避免空记录抢占有效记录的链接。
    from collect import cleaner
    if clean:
        uniq, cstats = cleaner.clean_posts(posts)
        clean_stats = {k: cstats[k] for k in ("empty_removed", "dup_removed")}
    else:
        uniq, seen = [], set()
        for p in posts:
            key = (p.platform, p.url) if p.url else id(p)
            if key not in seen:
                seen.add(key)
                uniq.append(p)
        clean_stats = {"empty_removed": 0, "dup_removed": len(posts) - len(uniq)}
    # 多个适配器合并后仍遵守每平台数量上限。
    counts, bounded = {}, []
    for p in uniq:
        if counts.get(p.platform, 0) < limit:
            bounded.append(p)
            counts[p.platform] = counts.get(p.platform, 0) + 1
    uniq = bounded

    summary = {"inserted": 0, "skipped": 0, **clean_stats}
    if save and uniq:
        from collect import store
        saved = store.save_posts(uniq)
        summary["inserted"] = saved["inserted"]
        summary["skipped"] = saved["skipped"]

    return uniq, errors, summary
