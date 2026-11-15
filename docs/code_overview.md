# CyberField 当前代码架构

更新：2026-11-13。本文为模块索引，源代码是实现依据；历史整份代码快照可从Git查看，不再在文档重复维护。

## 调用关系
```text
web/app.js → web_app.Handler → SearchPipeline公开接口
                              ├─ orchestrator → sources → Post → cleaner
                              ├─ comments → HTTP或本地JSONL
                              ├─ llm → 可选模型接口
                              └─ analysis → 样本统计
账号面板 → web_app → AccountManager → 外部MediaCrawler登录/验证脚本
终端/批量 → orchestrator → 可选store → SQLite
```

网页搜索缓存位于服务内存；当前不自动入库。账号状态管理与实际游客态采集是独立链路，显示登录成功不代表网页搜索已经使用该会话。前端与HTTP响应保持兼容。

## 模块索引
| 文件 | 职责 |
|---|---|
| `collect/settings.py` | 共享路径和默认值；导入无文件操作 |
| `collect/__init__.py` | CyberField 多源采集模块。 |
| `collect/account_manager.py` | 平台账号状态机与登录 / 验证 / 退出管理。 |
| `collect/analysis.py` | 样本统计纯函数：输入Post列表，返回现有图表使用的字典。 |
| `collect/backfill_douban.py` | 旧豆瓣修复入口：改为只读核对，禁止把导演和上映年填成发帖信息。 |
| `collect/batch_collect.py` | 批量采集工具：多关键词 × 多源 → 清洗 → 可选入库，一次跑出大样本。 |
| `collect/cleaner.py` | 采集数据的清洗模块（浏览器模式核心）。 |
| `collect/comments.py` | 评论获取：B站接口和小红书本地JSONL，保留现有筛选与降级规则。 |
| `collect/demo_cli.py` | CyberField 多源采集 Demo —— 终端交互式浏览试用（无图形界面）。 |
| `collect/llm.py` | LLM 客户端：OpenAI 兼容接口（默认 DeepSeek），用于内容总结与关键词扩展。 |
| `collect/ocr.py` | 轻量 OCR 模块：识别小红书笔记图片里的文字。 |
| `collect/orchestrator.py` | 多源调度器：依次调用所有启用源 → 合并 → 去重 → 清洗 →（可选）入库。 |
| `collect/post.py` | 统一帖子数据契约（Post）与平台名规范化。 |
| `collect/search_pipeline.py` | 搜索引擎式搜索管道：模糊扩展 → 多源搜索 → 评论增强 → LLM 总结 → 分析统计。 |
| `collect/sources/__init__.py` | 数据源适配器注册表。新增源时： |
| `collect/sources/base_source.py` | 数据源抽象接口（BaseSource）。 |
| `collect/sources/bilibili_source.py` | B站游客态搜索适配器。 |
| `collect/sources/douban_source.py` | 豆瓣游客态搜索适配器。 |
| `collect/sources/http_client.py` | 轻量 HTTP 会话工具（纯标准库实现，无需第三方依赖）。 |
| `collect/sources/mediacrawler_source.py` | MediaCrawler 适配器。 |
| `collect/sources/weibo_source.py` | 微博游客态搜索适配器（访客激活流程，免登录）。 |
| `collect/sources/xhs_source.py` | 小红书登录态搜索适配器（复用专用档案）。 |
| `collect/sources/zhihu_source.py` | 知乎登录态搜索适配器（复用专用档案）。 |
| `collect/store.py` | SQLite 存储：兼容旧库、只读查询，以及按采集时刻保存元数据快照。 |
| `collect/time_utils.py` | 统一时间：秒/毫秒时间戳和带时区日期转为北京时间；未知时间留空。 |
| `collect/web_app.py` | 搜索引擎式研究工作台：python -m collect.web_app；默认仅监听 127.0.0.1。 |

## 其他入口与工程文件
- clean_posts.py：DataFrame/CSV清洗；posts_db.py：旧四字段SQLite导入与检索。
- web/index.html/style.css：页面与样式；app.js：搜索与初始化；accounts.js：账号面板；analysis.js：统计图表；dom.js：安全DOM工具。
- tools/check_web_ui.py：可选Playwright离线浏览器验收，不是应用运行依赖。
- test_search_web.py/test_comments.py：本轮HTTP契约、搜索行为与评论读取回归。
- test_collect_data.py/test_collect_regressions.py/test_account_manager.py：数据、采集与账号测试。
- test_clean_posts.py/test_posts_db.py：原工具的显式run_all测试入口。
- README.md：启动命令与当前完成状态；AGENTS.md：开发约定；requirements.txt：直接依赖。
- data/：运行数据；ai-records/：交互记录；.venv/：本机环境，均不属于业务代码。

## 阅读顺序
先看web_app的路由，再看SearchPipeline公开接口及run_search；按需深入orchestrator与具体适配器。评论与统计分别读comments和analysis，账号单独读account_manager。重构边界、49项验收结果及待修问题见refactor_2026-11-13.md。

## 阶段4更新
搜索管道管理明确任务状态并提供close；账号使用每平台操作锁与任务代次防止旧结果回写。web_app关闭时清理两个后台管理器，前端读取新增总结状态字段。test_task_lifecycle.py新增11项回归；当前共60项离线检查通过。在途HTTP仍等待原有超时，不宣称可以立即终止。

## 阶段5更新
知乎登录态搜索（zhihu_api）加入网页搜索；多平台混合分页（每页 B站/小红书/知乎/微博/豆瓣共存，平台内热门前置）；主词完成即先发布第1页再补扩展词。test_zhihu_source新增10项、test_search_web增补4项，当前共94项离线检查通过。
