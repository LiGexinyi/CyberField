"""CyberField 多源采集模块。

设计：薄适配器层 + 统一数据契约（Post）。
每个数据源实现 BaseSource 接口（search(keyword) -> [Post]），
由 orchestrator 调度、store 统一入库；新增源不影响既有使用。

模块结构：
- post.py                  统一数据契约 Post 与平台名规范化
- sources/base_source.py   BaseSource 抽象接口 + 异常
- sources/http_client.py   轻量 HTTP 会话（标准库，Cookie/Referer/gzip）
- sources/mediacrawler_source.py  MediaCrawler 适配器（需登录）
- sources/bilibili_source.py     B站游客态搜索适配器（免登录）
- sources/douban_source.py       豆瓣移动端 rexxar 搜索适配器（免登录）
- sources/weibo_source.py        微博访客激活搜索适配器（免登录）
- orchestrator.py          多源调度 / 合并 / 去重
- store.py                 统一入库（collected_posts 表）与查询/统计
- demo_cli.py              终端交互式浏览试用入口
"""
