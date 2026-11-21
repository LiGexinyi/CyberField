# CyberField

## 快速入门

**[下载 CyberField Windows 便携版（64 位）](https://github.com/LiGexinyi/CyberField/releases/download/windows-2026.11.22/CyberField-Windows-x64.zip)**

1. 将 ZIP 完整解压，双击 `Start-CyberField.cmd`，工作台会在默认浏览器中打开。
2. 搜索关键词。需要登录平台时，点右上角，选平台并在 Chrome 或 Edge 专用窗口登录。登录后关闭专用窗口，工作台会验证状态。
3. 使用 AI 时，在「数据分析 → AI 分析」里选择服务商并填写自己的模型名和 API Key。

适用于 Windows 10/11 64 位，内置 Python 和依赖。平台登录、在线搜索和 AI 分析需要联网。

**网络热梗采集与传播演化研究工具**  
*An Open-Source-Oriented Toolkit for Online Meme Collection and Evolution Research*

CyberField 是一个面向中文互联网的网络文化数据采集与本地研究工具，旨在帮助研究者系统收集、整理和追踪网络热梗、流行话题及亚文化现象，为研究其传播机制、演化过程和社会文化意义提供可追溯的原始资料。

目前保留两条流程：Web搜索工作台通过扩词、多源搜索、评论增强展示临时结果（不写库）；终端和批量采集入口可选择写入SQLite。平台账号支持专用会话的登录、验证、取消和退出；网页搜索默认用B站、豆瓣、微博游客态来源，已登录小红书/知乎时自动加入小红书、知乎登录态搜索，结果按平台混合分页（每页同时出现各平台内容，越靠前越热）。搜索组织、评论获取、样本统计现已分模块管理；深度情绪、语义演化与真实群体识别尚未实现。

## 1. 项目背景

网络热梗与流行话题往往在不同互联网社区中迅速产生、传播、变形和衍生。例如“牛来”“奥德赛”“大水理论”“放生前额叶”等网络现象，其流行过程除了涉及内容本身，也可能反映特定群体的社会情绪、审美倾向和文化心理。

然而，相关内容广泛分布在微博、小红书、知乎等平台，存在信息碎片化、历史记录难以检索、跨平台数据格式不统一等问题，给长期观察和溯源研究带来困难。

CyberField 希望建立一个以**大规模网络文本采集、本地资料管理和传播过程追踪**为核心的工具，减少研究者在搜索、整理和归档资料上花费的时间。

项目主要负责数据采集、清洗、组织和呈现，具体的文化解释和社会学分析由研究者自主完成。

## 2. 项目目标

CyberField 的主要目标包括：

1. **网络数据采集**：围绕指定热梗或话题，从允许访问的数据来源持续获取相关公开文本。
2. **跨平台资料整合**：统一管理来自微博、小红书、知乎等平台的资料。
3. **本地数据归档**：保留帖子文本、发布时间、平台、原始链接及必要的采集元数据。
4. **热梗溯源与传播追踪**：寻找可核实的早期传播记录，观察话题的扩散、衍生和语义变化。
5. **检索与可视化**：支持关键词检索、时间筛选、传播时间线及相关表达统计。
6. **人工田野研究支持**：提供文本浏览、收藏、人工标签与研究笔记功能。

系统将区分“当前样本中最早检索到的记录”与“能够确认的真实起源”，避免因数据不完整而得出过度确定的溯源结论。

## 3. 功能模块

| 模块 | 主要功能 | 状态 |
|---|---|---|
| 数据导入与清洗 | CSV 读取、空文本过滤、去重、时间排序 | 基础版本已完成 |
| 本地数据库 | SQLite 存储（posts 表 + collected_posts 表）与关键词查询 | 已完成 |
| 多源采集框架 | `collect/` 薄适配器、统一 Post 契约、调度容错去重 | 已完成（MediaCrawler + B站/豆瓣游客态） |
| 数据导出 | CSV、JSON 导出 | 已完成 |
| 数据采集 | 真实平台接入（合规源优先）、增量更新 | B站/豆瓣/微博已接入；小红书等攻坚中 |
| 分析引擎 | 时间线梗演化、群体画像、话题共现、讨论度/热度、态度分析 | 规划中（三周计划） |
| 平台账号管理 | 专用会话登录、验证、取消、退出及状态面板 | 已有基础实现；未接入网页采集登录态，无多用户注册系统 |
| Web工作台 | 实时搜索、分页、来源跳转、可选总结和样本统计 | 基础版；会话结果不入库，深度模型未接入 |
| 话题管理 | 管理研究主题、关键词和衍生表达 | 规划中 |
| 传播追踪 | 早期记录、话题时间线及传播趋势 | 规划中 |
| 田野笔记 | 人工标注、收藏与研究记录 | 规划中 |

本项目优先保证数据采集的可靠性、来源可追溯性和本地资料的长期可用性，不以自动生成社会学结论为核心功能。

## 4. 技术栈

| 技术 | 用途 | 状态 |
|---|---|---|
| Python 3.13 | 主要开发语言 | 已使用 |
| Pandas | 数据导入、清洗、去重和排序 | 已使用 |
| SQLite + FTS5 | 本地数据存储与全文检索 | 已使用（FTS5 规划中） |
| collect/ 适配器 | 多源采集（统一 Post 契约 + 调度） | 已使用 |
| MediaCrawler | 外部采集工具（xhs/dy/ks/bili/wb/tieba/zhihu） | 已接入 |
| 游客态公开接口 | B站搜索 API、豆瓣移动端 rexxar API、微博访客激活（免登录） | 已接入 |
| jieba | 中文分词与分析 | 规划中 |
| transformers | 中文预训练情感模型 | 规划中 |
| 原生HTML/CSS/JavaScript + Python标准库HTTP | 当前Web工作台 | 已使用；未使用FastAPI/ECharts |
| JWT + cryptography | 用户会话与凭据加密 | 规划中 |
| LLM（Ollama / OpenAI 兼容） | 深度分析扩展 | 预留 |
| Git | 项目版本管理 | 已使用 |
| OpenCode | AI 辅助编程与调试 | 已使用 |

项目采用模块化设计，将数据采集、数据清洗、本地存储和可视化相互分离，以便后续扩展不同数据来源。

## 5. 数据来源与隐私原则

项目重点关注微博、小红书和知乎等中文互联网平台，并保留扩展其他公开数据源的可能性。

数据获取以官方授权接口、符合访问规则的公开内容及合法获得的数据集为基础，不绕过登录权限、验证码或其他访问控制。

项目默认将原始采集数据存储在本地，尽量减少不必要的个人信息采集。代码仓库不保存 API Key、Cookie、Token、真实采集数据库及其他敏感资料。

对于需要公开展示或分享的研究材料，将根据数据来源、使用许可及隐私风险进行必要处理。

## 6. 本地安装与运行

### 6.1 环境要求

- Windows
- Python 3.13
- Git
- 项目当前直接依赖：Pandas 3.0.6

推荐在项目目录下使用独立虚拟环境 `.venv`。

### 6.2 安装依赖

如果已创建 `.venv`，在项目目录的 PowerShell 中执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

如果是首次在其他电脑配置项目，可先使用 Python 3.13 创建虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 6.3 运行数据清洗程序

```powershell
.\.venv\Scripts\python.exe clean_posts.py
```

程序读取 `data/sample_posts.csv`，执行空文本过滤、重复记录删除及发布时间排序，结果保存为 `data/cleaned_posts.csv`。

### 6.4 运行离线测试

```powershell
.\.venv\Scripts\python.exe -B -m unittest test_search_web test_comments test_collect_data test_collect_regressions test_account_manager test_task_lifecycle test_zhihu_source test_xhs_source test_llm
.\.venv\Scripts\python.exe -B test_clean_posts.py
.\.venv\Scripts\python.exe -B test_posts_db.py
node test_frontend_order.mjs
node --test test_frontend_dom.mjs test_frontend_accounts.mjs
```

当前常用离线回归共 133 项：Python unittest 96 项、CSV 清洗 9 项、旧存储 14 项、前端 node:test 14 项（DOM 工具与账号状态矩阵）。测试使用虚构帖子、模拟网络/模型及临时目录，不运行真实采集或账号登录。

### 6.5 运行多源采集 Demo（终端）

```powershell
.\.venv\Scripts\python.exe -m collect.demo_cli
```

终端交互菜单：采集新关键词（可多平台；**B站/豆瓣/微博游客态免登录**，MediaCrawler 平台需首次扫码）、浏览本地库、统计概览、导出 CSV/JSON。采集数据存于 `data/collect.db`，导出到 `data/export/`。目标架构与分析规划见 `docs/roadmap.md`。

## 7. 当前项目结构

```text
CyberField/
├── README.md / AGENTS.md / requirements.txt
├── clean_posts.py / posts_db.py    # 旧CSV与SQLite接口，保留兼容
├── test_*.py                      # 离线回归与HTTP契约测试
├── collect/
│   ├── web_app.py                 # HTTP路由与序列化，不读取私有缓存
│   ├── search_pipeline.py         # 搜索组织、公开查询接口与缓存
│   ├── settings.py                # 共享路径与默认值
│   ├── comments.py                # 评论获取，复用调用方HTTP会话
│   ├── analysis.py                # 样本统计纯函数
│   ├── account_manager.py         # 专用账号状态与登录/验证/退出
│   ├── orchestrator.py            # 来源调度、容错、清洗与限量
│   ├── post.py / time_utils.py    # 统一契约与时间
│   ├── cleaner.py / store.py      # Post清洗与可选存储
│   ├── llm.py / ocr.py            # 可选模型总结与图片识别
│   ├── demo_cli.py / batch_collect.py
│   ├── backfill_douban.py         # 旧豆瓣记录只读核对
│   └── sources/                   # B站/豆瓣/微博/小红书/知乎/MediaCrawler适配器
├── web/                           # 原生ES模块，无构建步骤
│   ├── index.html / style.css      # 页面结构与样式
│   ├── app.js                     # 搜索、分页与初始化
│   ├── accounts.js                # 账号面板与扫码轮询
│   ├── analysis.js                # 分析请求与图表
│   ├── order.mjs                  # 请求身份门卫（防旧响应覆盖最新结果）
│   └── dom.js                     # 安全DOM与链接工具
├── docs/                          # 架构全览与重构记录
├── ai-records/                    # 交互导出，不属于运行代码
├── data/                          # 本地数据，不提交Git
└── .venv/                         # 本地环境，不提交Git
```

Web数据流：页面 → HTTP路由 → SearchPipeline公开方法 → orchestrator → 适配器 → Post清洗合并 → 内存结果；后台评论由comments模块获取，总结由llm模块生成，统计由analysis模块计算。终端可选入库流程继续通过store执行。

边界、兼容入口和下一轮问题见 `docs/refactor_2026-11-13.md`。`docs/code_overview.md`只维护模块职责与调用关系，不再内嵌会过时的整份源代码。

## 8. 当前完成进度与后续安排

- [x] CSV清洗、SQLite导入/检索、采集库与互动快照
- [x] Post类型、时间规范化、来源调度与异常隔离
- [x] B站/豆瓣/微博游客态来源和外部MediaCrawler适配器
- [x] Web扩词搜索、分页、来源跳转、评论与可选LLM总结
- [x] 平台账号面板、专用会话登录/验证/取消/退出基础实现
- [x] 评论与统计模块拆分，Web层通过公开接口读取搜索结果
- [x] 新增HTTP契约及评论读取回归，本轮49项离线检查通过
- [x] 总结任务终态、关闭入口及账号任务代次隔离（离线回归通过）
- [x] 共享路径及搜索、分页、评论和模型默认配置集中管理
- [ ] 登录态接入实际采集（阶段3 网页搜索并入登录会话，待后续）
- [x] 搜索缓存 TTL/容量/失败重试与同词并发去重（阶段4）
- [ ] 搜索覆盖与各源数量口径核验（初步原因已记录，待真实网络核验）
- [x] HTTP 请求体与参数校验、热度计数解析、模型空内容防护（阶段2）
- [x] 账号取消绑定任务：退出后迟到取消不再恢复登录态；前端失败有反馈（阶段3）
- [x] 前端按搜索、账号、图表和DOM工具拆分
- [x] 前端请求身份门卫：乱序响应不覆盖用户最后一次有效操作
- [x] 分析口径名称纠正：高频短语 / 平台与作者（阶段5，API 键不变）
- [ ] UI视觉与交互的后续改进
- [ ] 语义、情绪、真实群体观点与演化分析及人工评估
- [ ] 定时任务、多用户系统、人工标签与田野笔记


---

# 9. 开发日志（Development Log）

本节按时间顺序记录项目实际开发进展。**后续新进展只追加到末尾，保留已有记录**，并尽可能附上对应的 Git 提交编号。

## 2026-10-18 · 项目初始化

**Git 提交：** `4c3f719` — `Initial commit`

完成内容：

- 创建 `D:\Projects\CyberField` 项目目录。
- 初始化本地 Git 仓库。
- 创建基础 `README.md`。
- 完成第一次 Git 提交。

项目正式开始版本管理。

## 2026-10-18 · 项目目标与功能规划

**Git 提交：** `5f474be` — `Document CyberField project proposal`

完成内容：

- 明确 CyberField 的研究定位。
- 将项目核心确定为网络热梗数据采集、本地归档和传播演化研究。
- 确定微博、小红书、知乎为主要目标平台。
- 明确人工研究与程序自动化采集的分工。
- 编写完整的项目介绍、功能规划和技术栈说明。

此阶段主要完成项目设计，尚未开发实际数据采集模块。

## 2026-10-18 · 首个数据处理模块

**Git 提交：** `a61b394` — `Add CSV cleaning module and gitignore`

使用 OpenCode 辅助完成首次 Python 编程实践。

新增文件：

- `clean_posts.py`
- `test_clean_posts.py`
- `sample_posts.csv`
- `.gitignore`

实现功能：

- CSV 数据读取；
- 空文本过滤；
- 根据 `platform + source_url` 组合去重；
- 按 `published_at` 升序排序；
- 输出清洗统计并保存结果；
- 通过测试程序验证基本功能。

测试使用 8 条虚构网络帖子，实际运行结果：

```text
原始数量：8
删除空文本数量：1
去重数量：1
最终数量：6
已保存：cleaned_posts.csv
```

测试结果：

```text
所有断言通过 ✓
```

开发过程中还处理了 Windows 中文控制台输出编码问题。

同时建立 `.gitignore`，排除 Python 缓存、环境文件、密钥配置和本地数据文件，并验证了主要忽略规则。

## 2026-10-18 · 独立开发环境与依赖管理

**Git 提交：** `94a20ea` — `Add Python dependency requirements`

使用 OpenCode 辅助完成 Python 环境整理。

完成内容：

- 基于 Miniconda 的 Python 3.13.13，在项目内创建 `.venv` 虚拟环境；
- 在独立环境中安装 Pandas 3.0.6；
- 创建 `requirements.txt`，记录项目直接依赖；
- 使用独立环境重新运行数据清洗程序与测试；
- 确认原有功能正常，全部测试断言通过；
- 确认 `.venv/` 被 `.gitignore` 正确排除。

本次环境配置没有修改原有清洗代码。

---

## 2026-10-27 · 清洗逻辑重构与测试独立化

**Git 提交：** `a1ac4bc` — `Refactor cleaning logic and improve independent tests`

使用 OpenCode 辅助完成本轮代码改进。

### 本次目标
- 让测试不再依赖可随时编辑的 `sample_posts.csv`，改为自行构造数据；
- 拆分"清洗逻辑"与"文件读写"，便于单独测试和后续复用；
- 修复真正缺失值（None / NaN / pd.NA）未被删除的问题。

### 完成内容
- `clean_posts.py`：新增纯函数 `clean_dataframe(df)`，负责空文本删除、按 `platform + source_url` 原值去重、按发布时间升序排序；`clean_posts(input_path, output_path)` 接口、返回约定与命令行用法保持不变；
- 修复空文本判定：改用 `fillna("").astype(str).str.strip()` 统一处理空字符串、全空格与缺失值，避免 `NaN != ""` 判定为 True 导致缺失值被保留；
- `test_clean_posts.py`：测试数据全部自行构造，不再依赖 `sample_posts.csv`；新增用例覆盖正常清洗、全空文本、缺失值（None/NaN/pd.NA）、全部重复、带列名零行，并保留一个临时目录内的 CSV 读写集成测试；
- 完全空白文件（0 字节）当前仍会触发 `pandas.errors.EmptyDataError`，属既有行为，暂未新增处理。

### 测试与验证

```powershell
.\.venv\Scripts\python.exe test_clean_posts.py
# [通过] 正常清洗 / 全空文本 / 缺失值删除 / 全部重复 / 带列名零行 / CSV 读写集成
# 全部断言通过 ✓

.\.venv\Scripts\python.exe clean_posts.py
# 原始数量：8 / 删除空文本数量：1 / 去重数量：1 / 最终数量：6
```

### 下一步
- 确认完全空白文件是否需要新增友好处理；
- 设计统一的网络帖子数据结构并建立 SQLite 本地资料库。

---

## 2026-10-27 · 空文件友好处理与项目约定更新

**Git 提交：** `a1ac4bc` — `Refactor cleaning logic and improve independent tests`（与上一日志同属本次提交）

### 本次目标
- 让程序读取完全空白文件时不崩溃，给出清晰提示；
- 确立"每次修改都更新 README 当天日志"的项目约定；
- 调整 `.gitignore`，忽略课程材料与 AGENTS.md。

### 完成内容
- `clean_posts.py`：捕获 `pandas.errors.EmptyDataError`，对完全空白文件（0 字节或仅有 BOM）打印中文警告，并按"0 条帖子"继续处理（返回全 0 统计、写出仅含表头的文件），不再崩溃；
- `test_clean_posts.py`：新增"空文件友好处理"用例（0 字节文件 → 全 0 统计 + 表头输出）；
- `AGENTS.md`：新增约定——每次代码修改都要在 README 当天开发日志中追加记录；AGENTS.md 已加入 `.gitignore`（本地生效，不随仓库分发）；
- `.gitignore`：新增忽略 `AGENTS.md` 及课程演示材料（`*.pdf` / `*.pptx` / `*.ppt`）。

### 测试与验证

```powershell
.\.venv\Scripts\python.exe test_clean_posts.py
# 7 个用例全部 [通过]，含新增"空文件友好处理"

.\.venv\Scripts\python.exe clean_posts.py
# 原始数量：8 / 删除空文本数量：1 / 去重数量：1 / 最终数量：6
```

### 下一步
- 设计统一的网络帖子数据结构并建立 SQLite 本地资料库。

---

## 2026-10-27 · AGENTS.md 恢复随仓库分发并完成首轮提交

**Git 提交：** `a1ac4bc` — `Refactor cleaning logic and improve independent tests`（本次提交）

### 本次目标
- 让 AGENTS.md（AI 开发守则）随仓库分发，保证换环境后约定仍在；
- 将当前工作区的代码改进整理为一次 Git 提交。

### 完成内容
- `.gitignore`：移除 `AGENTS.md` 忽略规则，AGENTS.md 恢复纳入版本管理；
- `AGENTS.md`：同步更新说明文字（不再忽略，随仓库分发）；
- 提交涵盖：`clean_posts.py`（新增 `clean_dataframe`、缺失值修复、空文件友好处理）、`test_clean_posts.py`（测试独立化 + 7 个用例）、`README.md`（开发日志）、`.gitignore`（忽略课程材料）。

### 测试与验证
- 测试结果不变：7 个用例全部通过 ✓；
- 命令行结果不变：8 / 1 / 1 / 6。

## 2026-11-03 · A/B 分支实现评估合并 + 多源采集框架（MediaCrawler 接入）

**执行方：** OpenCode 辅助；本轮未执行 Git 提交/推送。

### 本次目标
- 评估 checkpoint2-a / checkpoint2-b 两份 SQLite 实现，将更优者合并进主项目；
- 建立"多源采集"薄适配器框架（统一数据契约 + 容错调度 + 独立入库）；
- 接入第一个外部源 MediaCrawler（真实搜索），提供终端交互式浏览 demo。

### A/B 评估结论与合并
- 逐行对比两份 `posts_db.py`：**cp2_B 整体更优**——时间字段统一规范化为 `YYYY-MM-DD HH:MM:SS`（排序正确）、事务 + 整批校验（失败不留部分记录）、自带命令行入口、字段 NOT NULL 强约束、13 项测试；
- cp2_A 的特色（多关键词 AND/OR 查询、逐行容错、导入统计字典）暂记为后续增强项，本轮不强融；
- 采用"复制实现文件"方式完成合并（两分支实现均为未跟踪文件，git merge 带不来内容）：将 cp2_B 的 `posts_db.py` + `test_posts_db.py` 复制进主项目；
- 主项目验证：`test_posts_db.py` 13 项测试全部通过，退出码 0；CLI 查询行为正常。

### 多源采集框架（增量新增 `collect/` 目录，未修改既有文件）
- `collect/post.py`：统一数据契约 Post + 平台名规范化/中文标签；
- `collect/sources/base_source.py`：源接口（search/health_check）+ SourceUnavailable 异常；
- `collect/sources/mediacrawler_source.py`：MediaCrawler 适配器（子进程调用 + JSONL 解析为 Post）；
- `collect/sources/__init__.py`：适配器注册表（新增源只在此登记，不影响旧源）；
- `collect/orchestrator.py`：多源调度——逐个调用、失败跳过、按 (platform, url) 去重；
- `collect/store.py`：独立采集库 `data/collect.db` 的 collected_posts 表（含标题/作者/关键词/来源适配器），不触碰现有 posts 表；
- `collect/demo_cli.py`：终端交互式浏览（采集/浏览/统计/导出）。

### MediaCrawler 外部工具部署
- 仓库克隆至 `D:\Projects\MediaCrawler`（独立 venv，Python 3.13.13）；
- 依赖安装完成：`requirements.txt` 中 `pandas==2.2.3` 放宽为 `pandas>=2.2.3`（Python 3.13 无 2.2.3 预编译包，实装 pandas 3.1.0）；
- 配置调整：`config/base_config.py` 的 `CDP_CONNECT_EXISTING` 改为 False（让 MediaCrawler 自动启动 Chrome，免手动开调试端口）；
- 真实搜索需首次扫码登录（登录态由 MediaCrawler 自动保存）。

### 测试与验证
- 采集框架自测（含样例数据）：save / stats / query 全部正常；
- MediaCrawler `--help` 验证通过（注意：必须以 MediaCrawler 目录为工作目录运行，否则相对路径 `libs/douyin.js` 报错）；
- 真实搜索验证：进行中（扫码登录后补充结果）。

### 已知问题与下一步
- 待办：真实搜索结果入库验证；
- 后续增强：cp2_A 多关键词 AND/OR 查询、zhihu-search / weibo-mcp 等更多源接入（架构已支持，新增适配器即可）；
- 数据隐私：MediaCrawler 输出已对作者昵称脱敏、创作者 ID 匿名化，符合项目数据来源与隐私原则。

---

## 2026-11-07 · 项目目录轻度整理与代码全览

**执行方：** OpenCode 辅助；本轮未执行 Git 提交/推送。

### 本次整理（代码仅两处路径微调）
- 删除全部 `__pycache__` 缓存（含 .venv 内字节码缓存，运行时会自动重建）；
- 数据文件归位：`sample_posts.csv`、`cleaned_posts.csv` 移入新建 `data/` 目录；
- 采集数据归位：`collect/data/` 下的 `collect.db` 与 `export/` 一并移入根 `data/`，`collect/` 包内只保留代码；
- 课程材料归位：`第02讲-提示词工程基础.pdf` 移入 `docs/`；
- 新增 `docs/code_overview.md`：全部代码全览（12 文件、约 1638 行，含完整源码与架构说明）；
- 微调：`store.py` 采集库路径与 `demo_cli.py` 导出路径改为根 `data/`（共两行）；
- README 第 7 节"项目文件结构"同步更新。

### 验证
- `test_posts_db.py`（13 项）+ `test_clean_posts.py`（7 项）= 20/20 全部通过 ✓；
- collect demo_cli 统计正常（在库 18 条），导出写入 `data/export/`。 

### 已知说明
- （本次已解决）`clean_posts.py` 命令行路径已同步改为 `data/`，见下一条日志。

---

## 2026-11-07 · 三周开发计划与目标架构规划

**执行方：** OpenCode 辅助；本轮未执行 Git 提交/推送。

### 规划背景
在现有 `collect/` 框架基础上，规划三周（2026-11-07 → 11-28）内建成「多源采集 + 分析 + Web 可视化」研究平台。

### 目标架构（详见 `docs/roadmap.md`）
- **多平台采集**：先打通合规源（知乎官方 API、微博访客模式、B站），后续扩展全部平台（小红书等攻坚项）；
- **分析引擎**：时间线梗演化、群体画像、话题共现、每天讨论度 / 火的时间、态度分析（HuggingFace 中文预训练情感模型）；
- **Web 可视化**：FastAPI + ECharts 本地仪表盘；
- **用户管理**：注册 / 登录 + 平台账号凭据加密存储（用户自备各平台登录账号，Cookie 仅本人可见）；
- **LLM 扩展预留**：`LLMProvider` 抽象接口（本地 Ollama / OpenAI 兼容 API 可切换），后续做梗演化叙事、态度提炼、趋势预测。

### 本次配套整合
- `clean_posts.py` 命令行入口数据路径改为 `data/`（与数据归位保持一致，读 `data/sample_posts.csv`、写 `data/cleaned_posts.csv`）；
- README 总体介绍（功能模块、技术栈、运行方式）同步新架构；
- `AGENTS.md` 新增「变更沟通与文档同步约定」：每次修改须在回复中明确说明改了什么，并同步 README / docs。

### 验证
- `test_clean_posts.py` / `test_posts_db.py` 20 项全部通过 ✓；
- `clean_posts.py` 命令行直接运行验证通过：原始 8 → 删空 1 → 去重 1 → 最终 6。

---

## 2026-11-08 · 接入 B站 / 豆瓣 / 微博游客态公开接口

**执行方：** OpenCode 辅助；本轮未执行 Git 提交/推送（保持本地）。

### 本次目标
按三周计划第 1 周「先打通简单合规的源」，接入 B站、豆瓣、微博三个免登录源，
让 `collect/` 框架具备真实可用的多平台采集能力。

### 完成内容
- 新增 `collect/sources/http_client.py`：轻量 HTTP 会话（纯标准库，自动携带
  Cookie / Referer / gzip 解压，可读取 Cookie 供访客激活校验），**零新增依赖**；
- 新增 `collect/sources/bilibili_source.py`（`bilibili_api`）：直连 B站公开搜索
  API（先访问主页拿游客 Cookie 再请求），返回视频的标题 / UP主 / 发布时间 / 播放量；
- 新增 `collect/sources/douban_source.py`（`douban_api`）：豆瓣官方 API 已停，
  改用移动端公开搜索接口 `m.douban.com/rexxar/api/v2/search/movie`（游客态），
  返回书影音条目标题 / 简介 / 评分 / 链接（条目无作者与时间，统计已兼容空值）；
- 新增 `collect/sources/weibo_source.py`（`weibo_api`）：微博移动端搜索接口需要
  访客 Cookie，实现「访客激活流程」（genvisitor 拿 tid → incarnate 换发
  SUB/SUBP → 带 Cookie 搜索），解析普通卡片与 card_group 卡片组的微博并按
  mid 去重，返回正文 / 作者 / 时间 / 转发评论点赞数；
- 注册进 `collect/sources/__init__.py`；`post.py` 增加豆瓣平台标签；
- `orchestrator.collect` 默认启用**全部已注册源**；demo_cli 支持多平台/多源选择，
  直接输入关键词默认走 B站 + 豆瓣 + 微博（免登录快速演示）；
- 去重兼容：豆瓣条目 url 缺失时用 subject id 构造唯一链接。

### 调研结论
- 豆瓣 `www.douban.com/j/search` 已被风控（403），官方 API 自 2020 年停开；
  移动端 rexxar API 游客态可用（参考开源 astron-douban-mcp 的接口思路）。
- B站公开搜索 API 游客态可用（需先访问主页拿 buvid3 Cookie）。
- 微博 weibo.com 返回 Sina Visitor System，需访客 Cookie 放行；激活流程参考
  astron-weibo-mcp / yt-dlp，域名必须用 `visitor.passport.weibo.cn`。
- 知乎 `search_v3` 游客态返回 400（需要签名参数），暂无法免登录接入；
  后续可用 MediaCrawler 知乎（扫码）或官方 API 资质。

### 测试与验证
- 真实采集「奥德赛」：B站 20 + 豆瓣 20 + 微博 9，共新增 49 条真实数据，
  幂等去重、统计 / 关键词查询正常；
- 库内总计 67 条，平台分布展示正确（B站 24 / 豆瓣 20 / 微博 11 /
  小红书 9 / 抖音 3）。

### 补充：demo_cli 结果分页显示（同日晚些时候）
- `collect/demo_cli.py` 的 `_print_table` 新增 `pageable` 开关：开启后结果超一页
  （默认每页 30 条）时进入交互分页——**回车 = 下一页，q = 返回，数字 = 跳到第 N 条**；
- 采集、浏览、直接输入关键词三处调用均开启翻页，不再只显示前 30 条；
- 验证：构造 36 条数据分别测试「回车翻页至第 31~36 条」「输入 33 跳页」、
  「关闭翻页保持旧提示」，均符合预期；未触碰采集逻辑。

### 补充：项目背景介绍文档（同日晚些时候）
- 新增 `docs/项目背景介绍.md`：供用户把完整上下文发给任意 AI 协作讨论
  「后续数据处理」，涵盖项目目标 / 技术状态 / Post 数据结构与库表 schema /
  数据现状（83 条真实数据、字段质量差异、extra 未入库） / 已调研开源工具 /
  7 个待议点 / 讨论约束；
- 内容与当前代码、README、roadmap 核对一致，纯文档新增，未改代码。

### 修复：豆瓣条目补全作者与发布时间
- 排查发现豆瓣搜索接口返回的 `target.year` 即首播 / 上映年份，`card_subtitle`
  含「地区 / 类型... / 导演 / 主演...」，此前未提取导致 author / published_at 为空；
- `collect/sources/douban_source.py`：新增 `_parse_year`（4 位年份 → 规范时间）与
  `_parse_subtitle`（按类型词表区分类型段与导演/主演段），author 取导演、extra
  增加 year/director/actors；
- 新增 `collect/backfill_douban.py`：`python -m collect.backfill_douban` 用
  subject_id 调详情接口回填历史记录的 author / published_at；
- 执行回填：32 条豆瓣历史记录全部补上时间，21 条补上作者（其余为详情接口
  导演列表为空，属正常数据缺失），无失败；
- 验证：解析单元测试（多种 subtitle 格式）+ 真实搜索「奶龙」+ 回填前后对比，
  均符合预期。

### 新增：清洗模块 + 浏览器模式 + B站翻页扩容
- 新增 `collect/cleaner.py`：采集数据的内存级清洗（删空文本 → 按 platform+url
  去重 → 时间升序排序，空时间排最后），对齐旧 `clean_posts.py` 规则但作用于
  Post 列表、纯标准库零依赖；
- `collect/orchestrator.py`：`collect()` 新增 `clean=True`（默认清洗后再返回/
  入库）与 `save` 参数（`save=False` = 浏览器模式，只展示不写库）；summary
  恒为字典（含 inserted/skipped/empty_removed/dup_removed），不再可能为 None；
- `collect/sources/bilibili_source.py`：B站搜索按页翻页（每页约 20 条，上限
  8 页≈160 条）直到凑满 limit，解决"一页 20 条"上限；
- `collect/demo_cli.py`：直接输入关键词改为**浏览器模式**（清洗后展示、不入库、
  用完即弃）；菜单 [1] 采集询问"入库？(y/回车=浏览器模式)"；展示清洗统计。
- 验证：清洗单元测试（空文本/去重/排序边界）+ 浏览器模式确认库条数不变 +
  B站 limit=45 实返 41 条（>20 证明翻页生效）+ demo 全流程交互正常；
- 现状说明：微博游客态不稳定（3 次重试 0/0/4），暂不翻页；仅 B站扩容。
  （注意：当时判断"豆瓣接口限死约 10~20 条"是**误判**，实为关键词结果太少，
  后续验证已修正并给豆瓣加上翻页，见下一条日志。）

### 新增：豆瓣翻页（修正"豆瓣限死"误判）
- 实测发现豆瓣 `search/movie` 接口的 `start` 偏移**分页有效**：「猫」关键词
  逐页 start=0/20/40... 每页 20 条、累计可到 100+ 条。此前误判"限死约 10~20
  条"是因为测试词「奶龙」在豆瓣结果本来就只有 12 条；
- `collect/sources/douban_source.py`：`search()` 按 start 偏移翻页凑够 limit，
  每页 count=20、页间 0.8s 延迟；翻页上限 3 页（约 60 条）；
- **need_login 降级**：实测连续快速请求豆瓣会返回 `{"code":103,"msg":"need_login"}`
  （403，接口级保护，触发后需长时间冷却）。翻页中一旦触发 403，保留已拿到页
  降级返回，不让整次采集失败——单页用户至少拿到第一页；
- 验证：mock 逻辑测试 5 项全过（单页1次请求/翻3页60条/第2页403降级20条/
  首页403抛异常/不满一页提前停）+ 真实验证「猫」limit=60 实返 60 条、
  「奶龙」行为不变；
- 现状更新：B站翻页（上限 8 页）+ 豆瓣翻页（上限 3 页、降级保护）；微博
  游客态仍无解（单页 4~6 条、翻页被拒），需登录态（MediaCrawler 扫码）突破。

---

## 后续开发记录

今后每完成一个相对独立的功能、重要修复或开发阶段，在本节末尾按如下格式追加：

```markdown
## YYYY-MM-DD · 本次开发内容

**Git 提交：** `提交编号` — `提交说明`

### 本次目标
简要说明希望解决的问题。

### 完成内容
- 新增功能或文件
- 主要实现方式
- 修复的问题

### 测试与验证
记录实际运行命令、测试结果及未解决问题。

### 下一步
列出后续准备开展的工作。
```

---

## 10. 项目说明

CyberField 最初作为清华大学《AI 编程进阶：方法与实践》课程的个人项目启动。

开发过程中使用 ChatGPT 辅助需求讨论、技术学习和任务规划，使用 OpenCode 辅助本地编程、运行与调试。具体运行验证、数据核查及网络文化现象的社会意义解释由开发者负责。

项目仍处于初期开发阶段，README 将随着实际进展持续更新。

## 2026-11-03 · 小红书搜索接口版本核对

- 通过用户手动网页搜索的只读监听，观察到 `/api/sns/web/v2/search/notes` 返回 HTTP 200、success=true、code=0、items 22 项。该数量为搜索结果项数，未验证全部均为笔记。
- MediaCrawler 原先调用 v1，诊断返回只有 has_more=false，没有 items；将 `media_platform/xhs/client.py` 中搜索路由最小更新为 v2。
- 仅做语法检查，尚未证明 v2 路由与旧请求参数组合能正常获取数据；未批量采集、未提交 Git。
- 正常网页还包含 ext_flags、filters、geo、image_formats、message_id、session_id 等字段；必要性待验证，不猜造参数、不修改风控或签名算法。


### 2026-11-08：采集链路边界修复（Codex）
- 目标：修复离线复现的数据丢失与交互边界，未运行真实采集、未改现有数据库。
- 完成：先过滤空正文再去重；健康检查异常隔离；关键词和数量校验；合并后每平台限量；无链接浏览结果不合并、入库明确拒绝；查询百分号和下划线按字面匹配；分页拒绝零值；显示完整链接；空导出覆盖旧 CSV；回填保留已有非空字段；CLI 导入不再重配标准输出。
- 验证：新增 test_collect_regressions.py，5 项离线回归通过；原清洗7项及存储13项通过。
- 尚未解决：豆瓣电影条目与社交帖子字段语义混用；MediaCrawler 历史结果隔离；extra 互动指标持久化与历史快照；时间格式统一；本地浏览200条上限。这些不能视为已修复，后续分析前需处理。


### 2026-11-08：数据语义与本地研究工作台
- 已完成上一轮遗留的四项：`Post.record_type` 区分帖子与影视条目；时间统一北京时间并保留原值；MediaCrawler 运行前后多重集合差分排除历史结果；`post_observations` 保存每次入库的互动元数据及关键词。
- 旧库读取使用只读连接，旧豆瓣作者与日期移入返回值的 legacy 字段，不参与帖子统计；不修改原始库。下一次主动入库才创建附加快照表。历史未保存的互动数无法恢复。
- 前端：`web/index.html`、`web/style.css`、`web/app.js`；服务入口 `collect/web_app.py`。真实本地库关键词筛选、平台/内容类型/日期筛选、原文跳转、详情、样本时间图和重复短语展示。无外部 CDN、无新增依赖。
- 测试：新数据测试8项 + 上轮回归5项通过；浏览器实测读取83条资料，详情/切页/空结果/390px手机无横向溢出，未发现JS异常。原有清洗7项与存储13项再次通过，共33项通过；页面截图复核后修正手机刷新按钮折行，并增加窄屏详情定位。
- 未运行真实采集，未修改现有 collect.db，未提交 Git。深度群体/情绪/语义演化仍属于后续模型功能，页面没有伪造结果。


### 2026-11-08：Web 实时搜索 + 手动入库 + 清空本地库
- 需求：前端支持直接真实搜索；清空本地库；搜索结果**不自动入库**，每次搜索后
  显示「手动入库」确认键，确认才写库。
- `collect/web_app.py`：新增 `POST /api/search`（调用 B站+豆瓣+微博游客态
  `orchestrator.collect(save=False)` 实时采集，结果只缓存在服务内存，不落盘）与
  `POST /api/import`（把最近一次搜索结果写入本地库，写后清空缓存防重复）；
  新增 `post_to_row()` 把 Post 转成与 export_rows 同形状的行，前端可直接复用。
- `web/`：搜索框改为「实时搜索」（loading 态，约 10~30 秒）；新增「实时搜索」
  标签页：结果列表 + 清洗/源错误统计 + **「手动入库 N 条」按钮** + 入库结果提示；
  「资料浏览」「观察与分析」保留原有本地库能力；搜索视图独占整行并隐藏筛选栏。
- 本地库：原 83 条真实数据已备份为 `data/collect.db.bak_20261108` 后清空；
  验证用入库的 36 条也已清除，库回到空状态，由后续手动入库按需填充。
- 验证：全链路脚本通过——实时搜索「奶龙」命中 36 条（3 源真实数据）、
  搜索后本地库仍 0 条（未自动入库）、手动入库 36 条、再次入库提示缓存已空；
  浏览器实测页面加载与接口返回正常。
- 说明：实时搜索默认 limit=20（B站/豆瓣单页），想更多可稍后调大 limit；
  高频率搜索仍受豆瓣 need_login / 微博游客态限制，适配器已有降级保护。

### 2026-11-09：评论筛选 + OCR 图片文字识别 + 批量采集增强
- 需求：评论是次要数据（只留高质量：点赞高 / 内容长 / 互动讨论多，剔除
  `@` 拉人看的无效评论）；小红书笔记大量观点输出在图片里，配置轻量 OCR
  小模型识别图片文字参与分析；前端工作台展示效果。
- 评论筛选（`collect/sources/mediacrawler_source.py`）：
  - `load_results` 同时读取 `search_contents_*.jsonl`（笔记）与
    `search_comments_*.jsonl`（评论）；评论按 点赞≥100（解析「万」）/
    长度≥50字 / 讨论≥30 任选达标筛选，剔除含 `@` 的评论，每笔记最多 2 条，
    总量不超过笔记的 1/3；
  - 高质量评论作为独立 Post 入库：`record_type="comment"`，url 带
    `#comment-{id}` 保证与笔记去重键不冲突；点赞数解析「1.4万→14000」；
  - 修复 JSONL 跨运行累积导致的重复：按 (platform,url) 去重后再返回。
- OCR 小模型（新增 `collect/ocr.py`，RapidOCR onnx CPU 版）：
  - 懒加载引擎、按图片 URL 缓存识别结果、失败降级不中断采集；
  - 适配器 `MediaCrawlerSource(ocr=True)` 开启：图片文字存入
    `extra["ocr_text"]`（独立字段，不污染原文）；
  - 实测：24 条笔记中 9 条图片含文字，「坏猫年度总结：今年共向妈妈齿此牙
    128次…闯祸365天战绩全网可查」完整识别，~1 秒/图。
- 批量工具（`collect/batch_collect.py`）：新增 `--ocr` 开关，配合
  `--platforms xhs --sources mediacrawler` 使用；`collect/orchestrator.py`
  `source_kwargs` 支持「按源名传参」（`{"mediacrawler": {"ocr": True}}`），
  不影响其他源的构造参数。
- 前端（`web/app.js` / `web/style.css`）：详情页新增「图片文字（OCR 识别）」
  区块（`record_type="comment"` 显示为「评论」类型标签）。
- 验证：评论筛选后 24 笔记 + 7 高赞评论（占比 22%）入库成功；按源传参
  monkeypatch 验证通过；OCR→清洗→入库后库中 9 条带 ocr_text，浏览器实测
  详情页 OCR 区块正常展示。提交：`ecc2b00`（评论筛选）、`ef9f025`（OCR
  模块）、`c1edf12`（OCR 全链路 + 前端）。
- 待办：B站/微博账号登录态采集（MediaCrawler bili/wb）；批量关键词组确认后
  启动大规模采集。

### 2026-11-09：B站内容概览（L1）+ 前端「做减法」改版
- 需求：B站视频「大概讲了什么」在前端展示；前端文案太啰嗦，按「做减法」
  原则改版（免责全局一次 / 删复述 / 按钮动词+宾语 / 空状态一句话+按钮 /
  拿不准的小字收进 ⓘ 提示）。
- B站内容概览（L1，零依赖，`collect/sources/bilibili_source.py`）：
  - 调研结论：B站官方 AI 总结接口 `view/conclusion/get` 游客态 -403（需登录），
    字幕+LLM 总结需 LLM Key（用户已确认稍后提供，届时接 L2）；
  - 本次落地：`BilibiliApiSource` 新增 `detail_limit` 参数，对前 N 条视频调
    详情接口 `/x/web-interface/view`（游客态可用），补 `desc_full`（完整简介）、
    `outline`（简介里「00:00 开场」式时序章节）、时长/分区/完整互动数；
  - 批量时默认 0 不抓（保持深翻页速度），需要时按源传参
    `{"bilibili_api": {"detail_limit": 30}}`。
- 前端改版（`web/index.html` / `web/style.css` / `web/app.js`）：
  - 页脚统一免责说明，删除卡片内重复小字；标题下同义反复全部删除；
  - 详情页新增「内容概览」（B站 desc_full / 章节 / 小红书 OCR 图片文字）
    与互动数一行展示；空状态改为一句话 + 「去实时搜索」按钮；
  - 平台分布/时间线/词云说明收进 ⓘ 悬停提示；实时搜索按钮文案明确
    （「手动入库 N 条」「加载更多」）。
- 验证：`detail_limit=30` 搜索「奶龙」「猫」→ 入库后库中 B站 80 条、
  52 条带完整简介概览；前端浏览器实测 155 条加载、详情页内容概览区块
  正常显示、控制台无 JS 错误。提交：`af0159f`（B站 L1 + 前端改版）。

### 2026-11-09：搜索引擎式工作台重构（黑白极简 + 模糊搜索 + LLM 总结 + 数据分析）
- 需求（用户）：前端统一字体、只能黑白、界面简洁只有搜索框；侧边栏放用户
  信息（暂不接内部信息）与数据分析细分选项；输入词后**主动模糊搜索**扩大
  搜索量；卡片给出标题/平台/日期 + LLM 一小段总结（原帖+评论区）；**不要
  本地库**设计（搜完即弃）；一条条陈列，30 条/页；搜索框下方顶栏可切换
  「详细数据 / 数据分析」，数据分析可视化时间热度、相关话题、相关群体。
- 新增 `collect/llm.py`：OpenAI 兼容 LLM 客户端（默认 DeepSeek），纯标准库，
  读环境变量 `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`；无 Key 时全部
  静默降级返回 None，不阻塞搜索；`summarize_post` 生成 ≤120 字总结（原帖+
  热门评论），`expand_keywords` 用 LLM 扩展搜索词。
- 新增 `collect/search_pipeline.py`：模糊搜索管道——B站搜索建议接口
  （`s.search.bilibili.com/main/suggest`，游客态可用）取真实关联词 + LLM
  补充扩展（≤6 词）；主词多平台深搜 + 扩展词 B站补充，合并去重按热度排序；
  后台线程（4 并发）为每条结果「尽力而为」抓热评（B站评论接口 `reply/main`
  游客态 -404 自动跳过，小红书从 MediaCrawler 已抓 JSONL 读高赞评论），
  有 LLM Key 时据此生成总结；`build_analysis` 统计时间热度/相关话题/
  相关群体/平台构成。
- 重写 `collect/web_app.py`：`POST /api/search`（模糊扩展+分页，30 条/页，
  同词换页复用缓存）、`GET /api/summaries`（前端轮询取评论/总结增量）、
  `GET /api/analysis`（分析统计）；**移除**本地库相关接口（资料浏览/
  手动入库），完全会话式。
- 前端全重写（`web/index.html` / `web/style.css` / `web/app.js`）：黑白配色、
  单字体栈；顶部品牌 + 用户信息占位，中央大搜索框；左栏用户卡片 + 数据
  分析细分选项（时间热度/相关话题/相关群体）；顶栏「详细数据/数据分析」
  切换；结果卡片=平台徽标+标题+作者+日期+LLM 总结（2 秒轮询填充，未配置
  Key 时提示）+热评+互动数+原文链接；分页 30/页；分析视图黑白柱状图/
  词云/群体分布条。无外部 CDN 依赖。
- 验证：`run_search('奶龙')` 5 扩展词、85 条去重（B站65/微博8/豆瓣12）；
  HTTP 端到端搜索「第五人格」97 条 4 页、翻页正常、summaries 全 done、
  analysis 时间热度 36 点/话题/群体正常；静态页面三文件 200。当前无 LLM
  Key，总结留空（`LLM_API_KEY` 配置后重启即启用）。提交：本次。

### 2026-11-13：平台账号状态机与真实有效性验证（阶段 0+1）
- 规范要求：cookie 存在 ≠ 已登录，必须经有效性检查；区分 7 态（未登录/待验证/
  验证中/已登录/已过期/登录失败/状态未知）；网络错误不判失效；登录只认证不采集；
  账号管理与采集共用同一专用会话；凭据不回传前端、不落日志、不进 git。
- 新增 `D:\Projects\MediaCrawler\verify_session.py`：无头启动平台专用档案 → 读
  cookie → 复现各平台 pong（xhs selfinfo / zhihu /api/v4/me / bili nav / wb
  config）→ 提取昵称 → 单行 JSON 输出 `VERIFY:{kind:ok|missing|invalid|network,
  nickname}`，绝不输出 cookie；网络异常/风控 → network（≠失效）。
- 本机无 playwright 捆绑浏览器（ms-playwright 目录为空），两个辅助脚本统一
  `_find_browser()` 定位系统 Chrome/Edge 并注入 `executable_path`，专用档案仍
  与日常浏览器隔离。
- 新增 `collect/account_manager.py`（替换 login_manager.py）：7 状态机 + 状态
  持久化 `data/accounts.json`（gitignore，仅存状态/昵称/最近验证时间/错误文本）；
  登录完成自动触发 verify → 直接落到已登录+昵称；检查状态/重新登录/退出/取消
  登录；退出仅删该平台专用档案。结果映射：ok→已登录 / invalid→已过期 /
  missing→未登录 / network→状态未知（保留原昵称不降级）。
- `collect/web_app.py`：新增 `POST /api/verify`、`GET /api/verify?platform=`、
  `POST /api/login/cancel`、`POST /api/logout`；/api/accounts 改返回 7 态 +
  昵称 + 最近验证时间 + 游客模式标注（douban=暂不支持登录）。
- 前端（web 三件套）：账号面板从侧栏移到**右上角「用户」入口**（右侧抽屉）；
  每平台卡片 = 状态徽章/昵称/最近验证时间/操作（登录/检查状态/重新登录/退出）；
  登录弹窗支持取消（POST /api/login/cancel）、过期重试、网络异常明确文案；
  游客模式标注（bili/wb/douban=游客模式，xhs/zhihu=未接入网页搜索）。
- 修复两处缺陷：`_set_state` 用 `.get` 导致状态不落盘（改 `setdefault`）；
  取消登录与 reader 收尾竞态覆写状态（cancelled 时 reader 不再动状态）。
- 验证：`verify_session.py --platform xhs` → `VERIFY:{"kind":"ok","nickname":
  "假装耍起的紧绷皮燕子"}`；web 端 POST /api/verify → 轮询 → logged_in+昵称+
  最近验证时间；登录/取消接口起停正常（含 xhs 已登录路径 LOGGED_IN、zhihu 弹码
  路径 QR: 输出）；静态页三文件 200；单测新增 6 项（共 19 项全通过）。提交：本次。

### 2026-11-13：网页侧平台账号扫码登录（小红书 / 知乎 / B站 / 微博）
- 需求：用户打开工作台如何登录小红书账号；知乎现在能不能登。
- 现状：网页搜索只用游客态三源（B站/豆瓣/微博），小红书/知乎此前只能通过
  MediaCrawler CLI 扫码登录，网页无登录入口。
- 新增 `D:\Projects\MediaCrawler\login_standalone.py`：MediaCrawler 侧的登录
  辅助脚本——挂载 `tools.utils.show_qrcode` 把二维码 base64 单行输出到 stdout
  （不再弹系统图片窗口），登录完成后 cookie 写入
  `browser_data/{platform}_user_data_dir`，再把 search/detail/creator 三种抓取
  入口替换为 no-op 实现「登录即停」；已登录时直接 `LOGGED_IN` 不带码。
- 新增 `collect/login_manager.py`：子进程管理 + 逐行捕获二维码 + 状态机
  （starting / qr_ready / logged_in / expired / failed / idle）；`is_logged_in`
  按 `browser_data/{platform}_user_data_dir/Default/Network/Cookies` 是否存在
  粗判（真正是否有效由 MediaCrawler 搜索时 pong 自校验）；不保存任何账号密码。
- `collect/web_app.py`：新增 `GET /api/accounts`（各平台登录状态）、
  `POST /api/login {platform}`（启动扫码登录）、`GET /api/login?platform=`
  （轮询状态 + 二维码 base64）；CSP 放开 `img-src data:`（否则二维码图片被拦）。
- 前端（`web/index.html` / `web/style.css` / `web/app.js`）：侧边栏新增
  「平台账号」区（状态点 + 已登录/登录按钮），登录按钮打开黑白扫码弹窗，
  base64 二维码以 data URI 显示，2 秒轮询直至「登录成功」；过期/失败可重试。
- 知乎说明：MediaCrawler 已内置知乎平台（qrcode 登录），扫码流程与小红书一致；
  登录态存 `browser_data/zhihu_user_data_dir`，此后可用 mediacrawler 适配器
  采集知乎（接入网页搜索为后续迭代）。
- 验证：`login_standalone.py --platform zhihu` 实测浏览器启动→pong 失败→弹出
  二维码→stdout 单行 `QR:<base64>`（PNG 头 iVBORw0KGgo 校验通过）；web 端
  `/api/accounts` 返回四平台状态（xhs 已登录/zhihu·bili·wb 未登录）、
  `/api/login` 起停正常；清理测试残留的 zhihu 半成品档案；CSP img data 生效；
  单测新增 5 项（共 18 项全通过）。提交：本次。

## 本地 Web 工作台启动
在项目根运行（PowerShell）：
```powershell
.\.venv\Scripts\python.exe -B -m collect.web_app
```
浏览器打开 http://127.0.0.1:8765 。占用时加 `--port 8766`。关闭终端即停止服务。
如需启用 LLM 总结（原帖+评论区的一小段总结），先设置环境变量再启动：
```powershell
$env:LLM_API_KEY="sk-..."   # OpenAI 兼容接口，默认 DeepSeek
$env:LLM_MODEL="deepseek-chat"   # 可选
.\.venv\Scripts\python.exe -B -m collect.web_app
```

工作台功能（搜索引擎式，搜完即弃、不落库）：
- **模糊搜索**：输入关键词自动扩展关联词（B站搜索建议 + LLM），B站+豆瓣+微博
  多源深搜，按热度排序，30 条/页翻页；结果=标题/平台/日期/LLM 总结/热评/原文；
- **数据分析**：顶栏切换「详细数据 / 数据分析」，左栏细分「时间热度 /
  相关话题 / 相关群体」，基于本次搜索结果做黑白可视化；
- **平台账号**：右上角「用户」入口 → 账号面板（右侧抽屉），每平台显示 7 态
  徽章/昵称/最近验证时间，操作：登录（扫码，可取消/过期重试）、检查状态（真实
  pong 校验）、重新登录、退出（仅清除该平台专用档案，不动采集资料与其他平台）；
  bili/wb/douban 标注游客模式，douban 暂不支持登录；登录态存于 MediaCrawler
  的 browser_data 专用档案，不保存密码；
- 侧边栏用户信息区暂为占位，未接账号系统。

### 新增结构
```text
collect/llm.py               # OpenAI 兼容 LLM 客户端（默认 DeepSeek，无 Key 降级）
collect/search_pipeline.py   # 模糊扩展→多源搜索→评论增强→后台总结→分析统计
collect/account_manager.py   # 平台账号 7 状态机：登录/验证/退出/取消，状态持久化
collect/web_app.py           # 本机 API：/api/search /api/summaries /api/analysis /api/accounts /api/login /api/verify /api/logout + 静态页
web/                        # 黑白极简搜索引擎式界面，无构建步骤
MediaCrawler/login_standalone.py  # MediaCrawler 侧登录辅助（二维码输出 stdout，登录即停）
MediaCrawler/verify_session.py    # MediaCrawler 侧验证辅助（无头 pong + 昵称，输出 VERIFY: JSON）
test_collect_data.py        # 旧库、快照、时间与采集隔离回归
test_collect_regressions.py # 采集边界回归（5 项）
test_account_manager.py     # 账号状态机/验证映射/网络容错/退出隔离（6 项）
docs/frontend-design.md    # 视觉规范与数据口径
```


### 2026-11-13：搜索模块渐进重构（阶段0—2）
- 目标：保持搜索HTTP契约与产品行为，减少Web入口对内部缓存的耦合。
- 基线：原有39项离线测试通过；新增test_search_web.py的8项HTTP/搜索契约测试在重构前通过。
- 修改：SearchPipeline增加search_page/get_posts/result_details/analysis_for公开方法；web_app不再访问私有缓存；评论逻辑抽至collect/comments.py，统计纯函数抽至collect/analysis.py。保留原调用入口委托转发。
- 兼容：不改来源、限量、热度算法、评论筛选、统计口径或入库行为；旧CSV工具、存储、登录管理和前端保持原样。
- 验收：同一批8项HTTP/搜索契约在重构前后均通过，另补2项小红书JSONL评论读取验证；加原39项共49项全部通过。无真实网络、模型付费调用、数据迁移或登录操作；未执行Git提交/推送。
- 文档：同步架构与完成进度，更新docs/code_overview.md，新增docs/refactor_2026-11-13.md；阶段3—5尚未执行。


### 2026-11-13：共享配置整理（阶段3）
- 新增collect/settings.py，集中项目路径、MediaCrawler路径、网页分页、搜索来源、评论数量、后台并发与LLM默认值；模块级旧常量仍保留为别名，兼容原测试和调用方式。
- 不读取或迁移凭据、不创建真实目录；默认值及显式mc_dir参数覆盖行为不变。配置在导入时加载，修改后重启服务。
- 计数解析暂未强行合并：MediaCrawler解析会strip且异常行为与评论解析不同；改变它们属于单独修复，避免以重构名义改变结果。
- 验证：49项离线测试全部通过；共享默认MediaCrawler路径与显式mc_dir覆盖检查通过，全部采集模块语法检查通过。后台状态、账号并发和任务关闭仍待阶段4。


### 2026-11-13：后台任务状态与账号竞态修复（阶段4）
- 已先复现：总结在评论阻塞时过早done；异常无明确终态；缺少关闭入口；旧账号验证在退出后恢复logged_in。
- 修改：总结任务明确queued/running/completed/skipped/failed/cancelled状态，旧done字段保留；账号按平台串行操作并使用代次校验回写；取消恢复登录前快照，退出先使旧任务失效；新增close接口。
- 验证：新增11项事件控制的生命周期测试通过；仅使用虚构数据、模拟进程和临时目录。未执行真实登录、清理真实档案或调用模型。
- HTTP兼容：原字段保留，/api/summaries新增status/error，搜索行新增summary_status/summary_error；前端区分排队、执行、未配置、失败和取消。账号操作增加平台白名单。
- 关闭限制：取消排队任务并阻止迟到回写；正在执行的HTTP不能强杀线程，需等待原请求超时。close限时等待并返回是否全部结束；账号仅尝试回收自己启动的进程树。真实浏览器进程退出效果未实测。

- 阶段4最终验收：40项unittest + 清洗7项 + 旧存储13项，共60项通过；JavaScript语法和Git差异格式检查通过。未提交或推送Git。


### 2026-11-13：前端按职责拆分（阶段5）
- app.js保留搜索、分页与页面入口；新增dom.js共享安全DOM工具、analysis.js图表视图、accounts.js账号交互。通过显式import与状态读取函数协作，不引入框架和构建工具。
- HTML改用原生ES模块，后端静态白名单补充三个脚本；CSS、页面布局、API路径及业务规则保持不变。离开页面清理轮询，不自动退出账号。
- 浏览器验收：模块加载、搜索、翻页、总结轮询、三种分析视图、账号面板、二维码/取消/检查/退出、空结果/错误反馈和390px手机无横向溢出均通过，无JS运行异常；只用模拟API，不发真实平台请求。


可选前端验收脚本：`tools/check_web_ui.py`，需要独立安装了Playwright的测试环境和Chrome，不是应用运行依赖。本次复用MediaCrawler已有Playwright环境运行：
```powershell
D:\Projects\MediaCrawler\.venv\Scripts\python.exe -B tools/check_web_ui.py
```
浏览器使用独立无头会话，登录/退出等API在测试中被拦截为假响应，不操作账号。

- 阶段5最终验收：原60项离线测试通过，四个JS模块语法和Git差异检查通过；浏览器模拟API验收通过。验收脚本曾出现请求已发出但记录尚未写入的竞态，已改为等待响应完成，未改动产品逻辑。无Git提交/推送。


### 2026-11-14：前端请求身份与乱序修复（阶段1：防止前端串结果）
- 目标：人为反转响应顺序时，页面必须始终对应最后一次有效操作。
- 失败样例先行：`tools/check_web_ui.py` 新增乱序验收——先搜 slow（页面内
  包装 fetch 延迟 1.2s 发出真实请求）、马上搜 fast（立即返回）。修复前复现
  `Actual value: 资料-slow`：迟到的 slow 响应覆盖了 fast 结果。实现细节：
  阻塞 Playwright 路由处理器会让请求串行化，达不到并发乱序；改用
  `page.add_init_script` 包装页面 fetch 才真正制造乱序。
- 新增 `web/order.mjs`：请求身份门卫 `requestGate`（next/peek/latest）。
  「启动新操作」的请求（搜索/翻页/统计）用 `next()` 使旧请求失效；轮询类
  请求用 `peek()` 捕获身份不推进，响应返回后再校验 `latest(id)` 且关键词
  一致才允许应用。
- `web/app.js`：`search`/`go` 登记身份并在响应与错误路径校验；`pollSummaries`
  用 `peek()`+关键词双校验，换词/换页后旧轮询不再写 `S.rows`、不再清掉新
  定时器。
- `web/analysis.js`：统计请求登记身份，响应到达后重读状态再渲染（避免旧
  关键词响应配新 dim 渲染）。
- `web/accounts.js`：`loadAccounts` 面板渲染身份守卫；登录弹窗 `pollLogin`/
  `pollVerify` 捕获会话身份，取消或切换平台后旧平台的迟到响应不再写弹窗。
- `collect/web_app.py`：静态白名单与 mime 映射补充 `/order.mjs`。
- 新增 `test_frontend_order.mjs`（Node 无依赖）：4 组乱序场景回归
  （搜索覆盖/换词轮询/翻页作废/登录换平台）。
- 验证：修复前浏览器乱序验收失败（资料-slow）；修复后验收通过且原有用例
  不变；Node 回归 4 组 PASS；40 项 unittest + 清洗 7 项 + 旧存储 13 项共
  60 项通过。未提交 Git（按约定仅在用户要求时提交）。


### 2026-11-15：输入输出边界 + 账号取消语义 + 缓存并发去重（阶段2—4）与口径纠正（阶段5）
- 失败样例先行：
  - HTTP：数组/null/数字请求体此前 `json.loads` 后直接 `.get` 会 500；page/
    size 坏类型被静默回退为 1/30（统一成功）；Content-Length 无上限。现改为
    `_read_json_object` 校验（对象类型 / 大小上限 64KB / 无效长度），
    keyword 必须字符串且 ≤100 字符，page 整数 ≥1，size 整数且 10~100，
    违规一律 400/413 明确报错，不再静默回退。
  - 热度：`_hot_score` 遇 `"1.4万"` 直接 `float()` 抛 ValueError 中断整次
    搜索。新增 `_count` 解析器（数字/逗号/万/亿，非法值按 0），仅用于热度
    排序，不合并其他模块的计数解析器。
  - 模型：`llm.chat` 对 `content: null` 返回字符串 `"None"`，会被当成成功
    总结。现严格校验类型与非空，null/空/非字符串一律返回 None。
  - 账号：已登录→重新登录→退出→迟到取消会把登录前快照恢复成已登录
    （"复活"已退出登录态）。`_advance` 现在标记旧任务 `superseded`，
    `cancel_login` 只取消仍在进行中的任务（starting/qr_ready/失败/过期/
    自动验证中）；无任务、已被退出等新操作替换、登录已完成时返回
    `cancelled:false` 且无副作用。另修正问题9：`last_verified_at` 只有
    `apply_verify_result`（真实验证结果）才更新，登录失败/取消/退出等
    非验证操作不再冒充验证记录。
  - 前端：`accounts.js` 多处 fetch 不检查状态码，取消失败仍显示"已取消"、
    退出失败无提示。现统一用 `dom.js` 新增的 `fetchTimeout`（8s 超时）并
    检查 `r.ok`/业务字段，失败明确提示；轮询带超时边界。
- 阶段4 缓存与并发：`search_page` 改为 `_get_or_run`——同词并发只让一个
  线程执行真实采集，其余线程等待复用；失败结果也发布给等待者（不卡死），
  冷却期（10s）后再次访问自动重试；成功结果带 TTL（300s），过期自动重搜；
  缓存容量上限（32 词），超出淘汰最早写入。配置集中在
  `collect/settings.py`（SEARCH_CACHE_TTL / MAX_ENTRIES / FAIL_RETRY_SECS /
  INFLIGHT_TIMEOUT）。
- 阶段5 口径纠正：分析 API 键不变（timeline/topics/groups/platforms），
  但 `topics` 实际是正文正则短语频次、`groups` 是平台×作者计数，前端展示名
  由「相关话题/相关群体」改为「高频短语/平台与作者」，analysis.py 与
  README 补充口径说明（不是主题模型/群体识别）。覆盖不足的初步原因已记录：
  扩展词只补搜 B站、主词 limit≈size/3、每页展示 30 条但只采集 size*3，
  待真实网络核验后调整。
- 新增测试：test_llm.py（5 项模型边界）；test_search_web 增补 HTTP 校验
  5 项、并发去重/TTL/失败重试/容量 4 项、热度解析 2 项；test_task_lifecycle
  增补退出后迟到取消、登录完成后迟到取消 2 项；test_account_manager 增补
  last_verified_at 只随真实验证更新 1 项。
- 验证：unittest 40→59 项全过；清洗 7 项、旧存储 13 项、Node 乱序回归
  4 组全过；浏览器验收（含乱序场景与更新后的取消 mock）PASS；真实启动
  `python -m collect.web_app` 冒烟：数组/null/坏 page 均 400、空关键词保持
  200 契约。未提交 Git（按约定仅在用户要求时提交）。

### 2026-11-15（续）：任务化搜索显示真实进度 + 知乎扫码登录缺陷修复
- 搜索过程可视化（用户反馈：黑盒等待 + 搜索偏慢）：
  - 新增 `POST /api/search/start`（立即返回 done/running/failed，同词并发去
    重，缓存命中直接 done）、`GET /api/search/progress?task=`（轮询真实进度
    step/collected/errors）；`POST /api/search` 保留同步语义兼容旧调用方。
  - `run_search` 主词（3 源）与扩展词（B站）并行采集（`SEARCH_COLLECT_
    WORKERS=3`），时长从串行求和降为最慢词，单词失败不拖累其他词；全部词
    失败且无结果时结果标记 failed，缓存层按冷却期重试（保持既有失败语义）。
  - 前端搜索改为「启动任务→轮询进度→取结果」：进度条展示真实步骤、已找到
    条数与耗时，超时（180s）与失败明确提示；任务有界缓存、close 时 running
    任务标 failed。
- 知乎扫码登录修复（用户反馈：浏览器跳转后不出二维码就结束）：
  - 根因：外部 MediaCrawler 知乎登录用 `canvas.Qrcode-qrcode` 单选择器等
    30s，页面未出二维码即超时崩溃退出（退出码1），前端永远收不到二维码，
    且 `_login_reader` 把真实原因吞成笼统「登录失败」。
  - 在 CyberField 侧自建 `tools/zhihu_login_standalone.py`（不改外部
    MediaCrawler）：系统 Chrome + 专用档案持久上下文（与日常浏览器隔离），
    直连 passport.zhihu.com/login 扫码页，多选择器截取二维码，失败回退
    知乎首页+点开登录弹窗；仍读不到则发 `QR_MISSING` 并保留浏览器窗口，
    支持窗口内扫码兜底（轮询 z_c0 判定成功）。
  - `account_manager`：zhihu 登录改用自建脚本并传 `--profile` 专用档案；
    `_login_reader` 新增 `QR_MISSING`/`qr_missing` 状态、保留输出尾部并
    提取可读失败原因（替代笼统提示），`poll_login` 透出 `qr_error`；
    前端账号面板展示二维码读取失败原因。
- 新增测试：test_account_manager 增补登录协议 5 项（QR 成功、QR_MISSING+
  窗口内扫码成功、崩溃原因提取、出码后失败按过期、zhihu 专用脚本与档案
  命令）；test_search_web 增补任务化/进度 5 项（start 在途→done、缓存命中
  done、同词去重、未知任务 idle、缺 task 400）。
- 验证：unittest 59→69 项全过；清洗 7 项、旧存储 13 项、Node 乱序回归 4 组
  全过；浏览器验收（含搜索进度 mock 场景）PASS；真实服务冒烟：`/api/search/
  start` 空词 200、非法词 400、`/api/search/progress` 缺 task 400、首页与
  app.js 已带进度 UI。8899 服务已重启为新代码。未提交 Git。

### 2026-11-15（续2）：网页搜索接入小红书登录态搜索
- 背景：用户反馈「目前只有B站和豆瓣，没有小红书，我已登录」。网页搜索此前
  只用 B站/豆瓣/微博游客态；小红书需登录态，且 MediaCrawler 全流程（浏览器+
  逐条详情+评论）对单次网页搜索过重（开可见窗口、分钟级耗时）。
- 方案（不改外部 MediaCrawler）：自建 `tools/xhs_search_standalone.py`，复用
  MediaCrawler 的 `XiaoHongShuClient`（xhshow 纯算法签名）只取搜索列表：
  - 系统 Chrome + 小红书专用档案持久上下文（无头），注入 `libs/stealth.min.js`
    反检测脚本；等 SPA 刷新会话 cookie 后读取；pong 校验登录态；
  - 搜索页大小固定传 20（小红书搜索接口限制，传其他值会静默返回空——实测
    page_size=5 返回空、20 正常返回）；
  - stdout 单行 JSON 协议 `{"ok":true,"items":[...]}` / `{"ok":false,"reason":...}`；
    登录态失效/浏览器启动失败/风控等返回可读原因，退出码 0/1。
- 新增适配器 `collect/sources/xhs_source.py`（`xhs_api`）：子进程调用脚本、
  解析 JSON 转统一 Post（标题取 `note_card.display_title`，extra 带
  liked/collected/comment/shared 热度）；未登录/失败抛 SourceUnavailable 由
  调度器跳过，不影响其他源。
- `settings.py`：`SEARCH_PLATFORMS=("xhs","bili","douban","wb")`、
  `SEARCH_SOURCES=("xhs_api","bilibili_api","douban_api","weibo_api")`、
  新增 `XHS_SEARCH_SCRIPT`；账号面板 xhs `search_mode` 改为「登录态搜索」。
- 新增测试：test_xhs_source 10 项（display_title/note_card 转换、假脚本协议、
  登录失效/风控友好原因、跨平台静默空、健康检查、注册表、末行 JSON）。
- 验证：unittest 69→79 项全过；真实冒烟（用户已登录的小红书档案）：
  脚本 `--keyword 奶茶 --limit 5` 返回真实笔记 JSON，适配器 `search()` 端到端
  返回 3 条（标题/链接/热度齐全，UTF-8 正确）；失败路径（假 Chrome 路径）
  返回 `browser_launch_failed` 单行 JSON。8899 已重启为新代码（首页 200、
  账号面板 xhs=登录态搜索、state=logged_in）。未提交 Git。

### 2026-11-15（续3）：修复网页搜索仍无小红书内容（清洗器删空正文）
- 背景：用户续测网页搜索「仍然没有搜索到小红书平台内容」。端到端复现定位根因：
  `run_search` 调 `orchestrator.collect` 时 `clean` 默认开启，内部 `cleaner.clean_posts`
  只保留 `text.strip()` 非空的帖子；而小红书**搜索列表卡片没有 desc 正文**（标题在
  `note_card.display_title`），适配器产出 `text=""`，5 条真实数据全部被清洗器当空
  文本删除 → 网页结果集里小红书内容完全消失。
- 修复 `collect/sources/xhs_source.py::_to_post`：正文缺省时回退用标题
  （`text = desc or title or ""`），保证有标题的卡片不会被清洗器误删。
- 补充回归测试 test_xhs_source 1 项：`text` 回退标题 + 帖子过 `cleaner.clean_posts`
  不被删（empty_removed=0）；实测真实数据 5 条中 4 条通过清洗（剩 1 条连标题都没
  有，属真正的空卡片，按设计删除）。
- 验证：unittest 79→80 项全过；重启 8899 后走完整 Web API 链路真实搜索「奶茶」，
  结果集平台分布 `bilibili 84 / xiaohongshu 19 / douban 19 / weibo 8`，共 130 条
  去重后结果、errors 为空，小红书 19 条带真实 explore 链接与 xsec_token；
  前端 `dom.js` 已有 `xiaohongshu:'小红书'` 平台徽章映射，可正常展示。未提交 Git。

### 2026-11-15（续4）：修复知乎登录二维码前端不显示（passport 域名下线）
- 背景：用户反馈知乎登录时「前端二维码位置从来没加载出来东西」，每次只能手动
  在脚本弹出的浏览器窗口里扫码。端到端复现定位根因：
  - `tools/zhihu_login_standalone.py` 第 1 步直连 `passport.zhihu.com/login`——
    **该域名已下线（DNS NXDOMAIN，实测不解析）**，45 秒 DNS 失败后回退；
  - 回退走 `www.zhihu.com` 时，专用档案**已登录**，直接进首页不会出现
    signin 二维码 → 脚本走 `QR_MISSING` 兜底 → 前端二维码区永远空白、
    登录模态框一直显示「启动登录」。
- 实测确认：登出态访问 `www.zhihu.com` 会自动跳到 `https://www.zhihu.com/signin`，
  二维码仍是 `<canvas class="Qrcode-qrcode">`（原选择器可匹配，仅 URL 失效）。
- 修复 `tools/zhihu_login_standalone.py`：
  - `_LOGIN_URL` 改为 `https://www.zhihu.com/signin`（现用二维码登录页）；
  - 新增「已登录快速路径」：启动后先查档案 cookie，存在 `z_c0` 立即输出
    `LOGGED_IN` 退出，不再卡启动等待；
  - `_find_qr` 等待状态从 `attached` 改为 `visible`，并补充 `canvas[alt='二维码']`
    选择器；新增 `--headless` 参数供自动化验证。
- 验证（真实浏览器只读打开登录页）：
  - 登出态（临时档案）：脚本输出 `QR:<base64>`，解码为 10671 字节有效 PNG
    （魔数 `\x89PNG`）——前端二维码区可正常渲染；
  - 已登录（真实档案）：立即 `LOGGED_IN`，退出码 0；
  - Web API 端到端：`POST /api/login` → 快速路径 `logged_in` → `/api/verify`
    → 面板 zhihu `logged_in`（昵称「看山」，验证时间刷新）；
  - unittest 80 项全过。未提交 Git。

### 2026-11-15（续5）：搜索加入知乎 + 多平台混合分页（每页都有 B站/知乎/微博/豆瓣）+ 先出第 1 页
- 背景（用户三条反馈）：① 知乎能登录了但搜索里没有知乎内容；② B站占比大头且
  非常集中，每一页里 B站/小红书/知乎/微博内容都要有显示；③ 至少 10 页，可以先
  搜索一部分先显示第 1 页，越靠前点赞/观看/投币/讨论等热度指标越靠前。
- 知乎登录态接入网页搜索（复用续4 已登录的专用档案）：
  - 新增 `tools/zhihu_search_standalone.py`：无头系统 Chrome + 知乎专用档案，
    注入 stealth，先访首页再访搜索页拿搜索态 cookie，复用 MediaCrawler
    `ZhiHuClient`（search_v3 签名）调 `/api/v4/search_v3` 翻页（每页 20）；
    pong 校验登录态；stdout 单行 JSON 协议与小红书脚本一致。
  - 修真实缺陷：httpx 按 ASCII 编码请求头，中文关键词放进 referer 直接抛
    `UnicodeEncodeError`（MediaCrawler 原版 referer 是 ASCII 的 "python" 才没
    踩到）——referer 里关键词改百分号编码后搜索成功。
  - 新增适配器 `collect/sources/zhihu_source.py`（`zhihu_api`）：子进程调用脚本
    转统一 Post（extra 带 voteup/comment 热度）；未登录/风控抛 SourceUnavailable
    由调度器跳过；注册进 `collect/sources/__init__.py`。
  - `settings.py`：`SEARCH_PLATFORMS=("xhs","bili","zhihu","douban","wb")`、
    `SEARCH_SOURCES` 加 `zhihu_api`、新增 `ZHIHU_SEARCH_SCRIPT`、
    `DEFAULT_PAGE_SIZE=20`、`SEARCH_COLLECT_PER_SOURCE=80`；账号面板 zhihu
    `search_mode` 改为「登录态搜索」。
- 多平台混合分页（`collect/search_pipeline.py`）：
  - `run_search` 分两阶段：**主词多源深搜完成即发布 partial 快照**（前端先显示
    第 1 页）→ 再补扩展词（B站）合并去重发布最终结果；进度查询对 partial 仍标记
    running 但带 collected，`start_search` 对 partial 不误判 done。
  - `_balanced_order` 平台混合排序：各平台内部按热度降序，再按页均分轮转——每页
    同时出现各平台内容、平台内越靠前越热；单平台退化为热度降序（兼容旧分页测试）。
  - `_hot_score` 热度指标扩展：新增 `voteup`（知乎赞同）、`attitudes_count`
    `reposts_count`（微博）、`favorites` `coin` `rating_count`（收藏/投币/评分）
    等，各平台都能正确参与热度排序。
  - `tools/xhs_search_standalone.py` 支持翻页（页间 3s 防 461）且翻页失败只保留
    已拿到主词页、不整体失败；微博源加翻页尝试（实测游客态第 2 页起返回 HTML，
    实际仍只能拿到第 1 页约 8 条，分块混合把这 8 条铺到前 8 页各 1 条）。
- 前端（`web/app.js`）：搜索请求显式带 size=20；进度轮询中一旦 `collected≥20`
  先渲染第 1 页（扩展词后台继续补，完成后刷新）；卡片新增知乎赞同（`e.voteup`）
  与微博点赞（`e.attitudes_count`）展示。
- 新增测试：test_zhihu_source 10 项（字段映射/正文回退标题过清洗/limit 截断/
  假脚本协议/登录失效与风控友好原因/健康检查/注册表）；test_search_web 增补
  4 项（平台混合每页齐全、单平台降序兼容、partial 快照与最终结果、partial 进度
  running 且第 1 页可取）。
- 验证：
  - unittest 80→94 项全过；`node test_frontend_order.mjs` 4 组乱序回归 PASS。
  - 知乎脚本冒烟（真实已登录档案）：`--keyword 奶茶 --limit 5` 返回 5 条真实
    回答（赞同 3525/19124 等，带评论数与链接）。
  - 重启 8899 后真实搜索「奶茶」：**268 条去重、14 页（≥10 页）**；进度轮询
    观察到主词 124 条发布后先出第 1 页（partial 阶段真实存在）；第 1/2/6 页
    均为 `bilibili 15 / zhihu 2 / weibo 1 / douban 2` 混合，平台内热门前置
    （首行 B站 640 万播放、第二行知乎 1.9 万赞同）；errors 为可读失败原因。
  - 账号面板：xhs/zhihu 均 `logged_in`，知乎 `search_mode=登录态搜索`。
  - 已知遗留：小红书因本轮连续翻页搜索触发 461 验证码被临时风控（登录态仍在，
    搜索接口需冷却恢复；脚本已容错不丢页 1 结果）；微博游客态仍只有第 1 页量，
    要提升需微博登录态搜索（可仿 xhs/zhihu 方式后续接入）。未提交 Git。

### 2026-11-15（续6）：代码整理去冗余（功能不变，仅清理）
- 背景：用户要求先通读现有代码再整理，去除冗余内容，保证去除后仍可完成全部
  现有功能，且不做代码内容的大幅度修改。
- 清理项（均经全仓 AST 扫描 + 精确 grep 确认无任何引用后移除）：
  - 未使用导入 4 处：`account_manager.py` 的 `Path`、`search_pipeline.py` 的
    `_like_num`（兼容导入，全仓无使用者）、`weibo_source.py` 的
    `parsedate_to_datetime`、`sources/__init__.py` 的 `SourceUnavailable`
    （各源均直接从 base_source 导入）。
  - 死方法 2 处：`search_pipeline.py` 的 `_cache_posts` 与 `_xhs_comments_from_jsonl`
    （注释标「兼容旧入口」但自重构起无任何调用者，评论读取统一走 comments 模块、
    列表读取统一走 get_posts）；同步修订 `docs/refactor_2026-11-13.md` 兼容说明。
- 文档整理（仅描述，不改行为）：
  - `collect/__init__.py`、`docs/code_overview.md` 模块清单补上
    `xhs_source.py` / `zhihu_source.py`，并新增「阶段5更新」段（94 项测试）；
  - `demo_cli.py` 顶部源清单与 BANNER 补齐 小红书/知乎 登录态源。
- 验证：unittest 94 项全过（同基线）；`node test_frontend_order.mjs` 4 组 PASS；
  全仓 AST 未使用导入扫描 4→0；`import collect.*` 冒烟通过。未提交 Git。

### 2026-11-15（续7）：检查点4 报告整理与交付准备
- 背景：按课程检查点4 要求整理交付内容（report.md + ai-records + attachments +
  project 完整 GitLab 仓库）。
- 完成：
  - 新增检查点4 报告（见 `data/checkpoint4-attachments/report.md`，最终随压缩包
    `2024012044_葛芯夷_checkpoint4.zip` 交付）：对照原设计（roadmap）说明完成情况、
    开发经过、计划调整、正常/边界检查记录与 AGENTS.md 使用情况。
  - `docs/roadmap.md` 追加「五·补、开发中计划调整与完成情况」章节，作为 PLAN
    文档（原设计与任务计划 + 完成情况 + 调整说明）。
  - 补齐 AI 交互记录：复用 `data/_export_sessions.py` 从 opencode 会话库导出
    11-09 / 11-13 / 11-14 / 11-15 四天记录，`ai-records/` 现在覆盖
    2026-10-18 → 2026-11-15 全程（10-18/10-27/11-03/11-07/11-08 为既有文件）。
  - 附件素材：94 项 unittest 日志、前端乱序回归 PASS 日志。
- 验证：unittest 94 项全过；`node test_frontend_order.mjs` PASS；导出的
  ai-records 各文件消息数与 opencode 会话库一致。本阶段所有改动（含检查点3 之后
  的未提交改动）作为检查点4 一次提交（提交编号见 `git log` 最新一条）。

### 2026-11-17：高优先级问题修复（审查清单第一轮）
- 背景：对当前工作区做 bad taste 静态检查后，优先修复会影响功能/数据正确性的高优先级问题。
- 完成：
  - `collect/search_pipeline.py`：修复增强任务启动顺序，最终结果写入缓存后再启动评论/总结，避免扩展词帖子永远停在“总结生成中”；移除 `run_search` 内重复 import，并让 HTTP 会话改为线程本地（后台 worker 不再共享 CookieJar）。
  - `clean_posts.py`：空 `source_url` 不再参与去重，避免同平台多条无链接记录被静默吞并；`published_at` 非法值（含 `nan`/`NaT`）在清洗阶段直接给出清晰错误，不再输出无法入库的 CSV。
  - `posts_db.py`：`published_at` 为 `NaT` 时按“无法解析为时间”整批拒绝，错误信息仍指向具体数据行。
  - `collect/settings.py`：MediaCrawler 路径改为支持 `MEDIACRAWLER_DIR` / `MEDIACRAWLER_PYTHON` 环境变量，并自动探测项目同级目录 / 子目录 / 原 Windows 工作区路径，不再只硬编码 `D:\Projects\MediaCrawler`。
  - `collect/sources/mediacrawler_source.py`：MediaCrawler 的“运行前后 JSONL 差分”串行化，避免并发搜索把其他任务写入的记录误判为本次新增。
  - `collect/web_app.py`：HTTP 处理增加 30 秒连接读写超时、统一 500 JSON 兜底、BrokenPipe 静默；POST 未知路径先 404 再读请求体；空关键词统一返回 400。
  - `web/dom.js` / `web/app.js`：新增 `postJSON`/`errorText`，搜索、翻页、进度与总结轮询统一带超时，并从服务端 JSON 错误中取具体原因展示。
  - `web/accounts.js`：「检查状态」按钮增加在途防抖，验证进行中禁用重复提交，避免双击触发新一轮验证。
- 测试与验证：
  - 新增/更新回归：`test_search_web.py`（增强任务在最终缓存发布后才启动）、`test_clean_posts.py`（空 URL 保留 + 非法时间拒绝）、`test_posts_db.py`（NaT 时间整批拒绝）、`test_search_web.py`（空关键词 400）。
  - 全量离线测试通过：`unittest` 69 项 OK；`test_clean_posts.py` 9 项通过；`test_posts_db.py` 14 项通过；`node test_frontend_order.mjs` 4 组 PASS。
  - `node --check` 对 `web/app.js`、`web/accounts.js`、`web/dom.js` 语法检查通过。未提交 Git。

### 2026-11-17（续）：重复/冗余内容合并清理（功能不变）
- 背景：用户要求检查重复或冗余内容，优化后回归验证原有功能不变。
- 完成：
  - 计数解析三处合一：新增 `collect/num_utils.py`（`parse_count` / `parse_count_int`，支持万/亿/逗号、非法值归 0），`search_pipeline._count`、`mediacrawler_source._parse_count`、`comments._like_num` 全部改为薄封装调用同一实现。
  - 登录态脚本源去重：新增 `collect/sources/script_search_source.py` 基类（子进程调用、单行 JSON 解析、错误文案映射），`xhs_source.py` 与 `zhihu_source.py` 从各约 130 行缩到约 55/45 行，只保留平台类属性与 `_to_post` 字段映射；构造参数与公开行为不变。
  - 小清理：`web/style.css` 删除末尾重复的 `@media(max-width:860px)` 块；`web/app.js` 删除未使用的 `all` 变量；`web_app.py` 合并重复 `urlsplit`、用顶层 `llm.available()` 替代行内 `__import__`、`_row` 去掉冗余 `pipe` 参数；`post.py` 的 `time_utils` 导入提到模块顶部；`web/accounts.js` 剩余手写 JSON POST 统一改用 `postJSON`。
  - 文档同步：`docs/code_overview.md` 模块索引补 `num_utils.py` 与 `script_search_source.py`。
- 测试与验证：
  - 新增 `test_collect_data.py::test_count_parsing_unified`（三处解析同源、非法值归 0）。
  - 全量回归通过：`unittest` 96 项 OK（含 xhs/zhihu 源 20 项，确认基类重构后接口不变）；`test_clean_posts.py` 9 项；`test_posts_db.py` 14 项；`node test_frontend_order.mjs` 4 组 PASS；`node --check` 前端四个模块语法通过；`compileall` 全量编译通过；源注册表冒烟正常。未提交 Git。

### 2026-11-17（续2）：重构计划 A 批执行（测试基建 + 低风险修复）
- 背景：按确认的重构 plan 执行 A 批——先建前端测试安全网，再做低风险小修。
- 完成：
  - A1 前端测试基建：新增 `test_frontend_dom.mjs`（`el`/`link` 协议白名单/`fetchTimeout`/`postJSON`/`errorText`，6 用例）与 `test_frontend_accounts.mjs`（`actionsFor` 七态矩阵 + 未知状态，8 用例）；用 Node 内置 `node:test` + 手写最小 DOM stub，零新增依赖；`accounts.js` 的 `actionsFor` 提升为模块级纯函数并导出（行为不变）。
  - A2 错误处理：`accounts.js` 修复 doVerify 错误分支重复消费响应体的自引入瑕疵（S1）；`pollLogin`/`pollVerify` 网络异常不再静默，显示「网络异常，自动重试中…」；`app.js` 进度轮询失败同样给出可感知提示（S2）。
  - A3 异常吞噬补日志（行为不变）：`account_manager`（状态读写、验证/登录工作线程、进程回收）、`llm`、`comments`、`ocr`、`search_pipeline`（扩词/增强）、`bilibili_source`、`weibo_source`、`mediacrawler_source` 的静默 `except` 统一补 `logger.debug/warning`（不含凭据）；默认日志级别下控制台输出不变。
  - A4 `run_search` 采集线程池加 try/finally，中途异常不再泄漏线程。
- 测试与验证：Python `unittest` 96 项 OK；`test_clean_posts.py` 9 项；`test_posts_db.py` 14 项；前端 `node --test` 14 项 PASS + `test_frontend_order.mjs` 4 组 PASS；`node --check` 前端模块语法通过；`compileall` 通过。未提交 Git。
- 遗留自知：`search_pipeline._http_session` 的主线程特例是兼容旧测试 patch 的权宜之计，后续 C3（测试体系统一）时可顺手清掉。

## 2026-11-21 · Windows 分享版

搜索主词的每源目标提高到 120 条，实际结果受来源分页与去重限制。网页暂停 AI 摘要，保留正文预览和评论。分享包附启动脚本，仅包含代码与依赖清单，平台账号由使用者自行登录。

网页分析按关键词合并本次搜索及 SQLite 已存帖子，按平台、链接去重。按日统计有发布时间的帖子，并按帖子数排列显式共现标签。

网页分轮搜索：每源先取 6 条，再扩大原词范围；不足千条时按可用建议词补充。网页可随时按平台筛选和翻页；失败来源在本次搜索停止重试。

平台登录直接打开专用浏览器访问官方页面。完成登录后关闭该窗口，工作台自动验证。

时间热度采用可选起止日期的折线图。共现分析按篇统计标签和标题正文分词，豆瓣条目简介仅参与文本统计。可在分析页输入服务商、模型和密钥，按需发送聚合统计生成解读。

首轮优先展示社交帖子。书影音目录条目在后续结果中排到社交帖子之后，仍可按豆瓣筛选。

AI 梗解读先检索 B 站公开视频，补充互动数据，再以标题和简介为依据解释含义与用法。推荐列表链接直接来自平台记录，互动数字按可取得的数据展示。

### 续搜与独立 AI 分析

- 目标：在同一搜索下多次扩大样本，并给梗解读独立入口。
- 网页搜索完成后可点「继续搜索」。留空时继续检查 B 站后续公开页并尝试尚未搜索的建议词。填入补搜词可在当前任务累计相关词结果。重复链接不会增加总数。
- 「数据分析」增加「AI 分析」选项。切换统计视图会保留当前关键词的解读，发起新搜索会重置表单。
- 验证：97 项 unittest 通过。浏览器验收覆盖两次补搜、保留页码和 AI 分析切换。B 站「奶龙」实测第 2 页相比第 1 页增加 39 个链接。

## 2026-11-22 · 服务器访客版

- 目标：在并行云 HTTPS 网关后展示可用的搜索工作台。
- 运行：Python 3.10+，项目根运行 `python3 -m collect.web_app --public --bind 0.0.0.0`。访客版默认读取 `BAT_PORT_http`，也可以通过 `--port` 指定网关对应端口。健康检查路径为 `/healthz`。
- 功能：B站、豆瓣和微博公开检索、平台筛选、续搜和样本统计。平台账号、历史数据库和面向访客收集密钥的 AI 接口在访客版关闭。
- 验证：本地 HTTP 检查首页、健康检查、访客来源及账号/AI 路由隔离。

### Windows 便携版

- 解压完整压缩包后双击 `Start-CyberField.cmd`。运行时和依赖随包提供，平台登录使用本机 Chrome 或 Edge 专用档案。
- 便携版使用空闲的回环端口，将登录状态保存在解压目录。AI 分析继续由使用者在工作台输入自己的 API Key。
- 启动器显式指向内置 Python。登录验证、登录态搜索和 MediaCrawler 适配器使用同一个解释器。
- 验证：97 项单元测试通过。最终 ZIP 解压后用内置运行时启动，核对首次登录状态为空，并通过了搜索、平台登录界面和 AI 解读的模拟浏览器验收。
