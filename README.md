# CyberField

**网络热梗采集与传播演化研究工具**  
*An Open-Source-Oriented Toolkit for Online Meme Collection and Evolution Research*

CyberField 是一个面向中文互联网的网络文化数据采集与本地研究工具，旨在帮助研究者系统收集、整理和追踪网络热梗、流行话题及亚文化现象，为研究其传播机制、演化过程和社会文化意义提供可追溯的原始资料。

目前项目已完成基础 CSV 清洗、SQLite 存储与关键词查询、多源采集框架（`collect/`，已接入 MediaCrawler 并支持终端演示），现已提供本地只读 Web 研究工作台（原生 HTML/CSS/JS + Python 标准库 HTTP 服务），后续扩展深度分析能力（时间线梗演化、群体画像、话题共现、讨论度/热度、态度分析），详细路线见 `docs/roadmap.md`。

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
| 用户与账号管理 | 注册/登录、平台账号凭据加密存储 | 规划中 |
| 可视化界面 | 本地只读工作台：检索、来源详情、样本时间分布和重复短语 | 基础版已完成；深度模型未接入 |
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
| FastAPI + ECharts | Web 可视化仪表盘 | 规划中 |
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

### 6.4 运行测试

```powershell
.\.venv\Scripts\python.exe test_clean_posts.py
.\.venv\Scripts\python.exe test_posts_db.py
```

两套独立测试共 20 项（清洗 7 项 + 存储 13 项），测试数据全部自行构造，不依赖样本文件。

### 6.5 运行多源采集 Demo（终端）

```powershell
.\.venv\Scripts\python.exe -m collect.demo_cli
```

终端交互菜单：采集新关键词（可多平台；**B站/豆瓣/微博游客态免登录**，MediaCrawler 平台需首次扫码）、浏览本地库、统计概览、导出 CSV/JSON。采集数据存于 `data/collect.db`，导出到 `data/export/`。目标架构与分析规划见 `docs/roadmap.md`。

## 7. 项目文件结构

```text
CyberField/
├── .gitignore
├── README.md
├── requirements.txt
├── clean_posts.py           # 数据清洗
├── posts_db.py              # SQLite 存储与关键词查询（cp2_B 合并）
├── test_clean_posts.py      # 清洗测试（7 项）
├── test_posts_db.py         # 存储测试（13 项）
├── AGENTS.md
├── collect/                 # 多源采集框架（新增）
│   ├── post.py              # 统一数据契约 Post
│   ├── orchestrator.py      # 多源调度 / 合并 / 去重
│   ├── store.py             # 采集库入库 / 查询 / 统计
│   ├── demo_cli.py          # 终端交互式 Demo
│   └── sources/             # 适配器（base_source / mediacrawler_source）
├── data/                    # 数据文件（一律不提交 Git）
│   ├── sample_posts.csv
│   ├── cleaned_posts.csv    # 运行生成
│   ├── collect.db           # 采集库（collected_posts 表）
│   └── export/              # 导出 CSV / JSON
├── docs/                    # 文档
│   ├── code_overview.md     # 代码全览（12 文件）
│   ├── roadmap.md           # 三周开发计划与六大分析规划
│   └── 项目背景介绍.md       # 供 AI 协作讨论的背景介绍
│   └── 第02讲-提示词工程基础.pdf  # 课程材料，不提交 Git
└── .venv/                   # 本地虚拟环境，不提交 Git
```

随着功能扩展，将逐步添加采集器、数据库、可视化界面和研究项目管理模块。

## 8. 开发计划

- [x] 建立项目与 Git 仓库
- [x] 完成项目说明文档
- [x] 实现 CSV 基础清洗与去重
- [x] 为清洗程序编写测试
- [x] 创建项目独立 Python 虚拟环境
- [x] 配置 `.gitignore` 和依赖文件
- [ ] 设计统一的网络帖子数据结构
- [ ] 建立 SQLite 本地资料库
- [ ] 实现基础检索与数据导出
- [ ] 接入首个符合访问规则的真实数据源
- [ ] 实现采集任务管理和增量更新
- [ ] 构建话题传播时间线
- [ ] 开发本地可视化界面
- [ ] 添加人工标签和田野笔记
- [ ] 完善测试、异常处理和使用文档

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

## 本地 Web 工作台启动
在项目根运行（PowerShell）：
```powershell
.\.venv\Scripts\python.exe -B -m collect.web_app
```
浏览器打开 http://127.0.0.1:8765 。占用时加 `--port 8766`。关闭终端即停止服务。数据库缺失显示空状态。

工作台功能：
- **实时搜索**：顶部输入关键词调用 B站+豆瓣+微博游客态真实搜索（约 10~30 秒）；
  结果是临时数据，**不自动入库**；
- **手动入库**：每次搜索结果显示「手动入库」确认键，点击后才写入本地库，
  且只入库最近一次搜索结果（防重复）；
- **资料浏览 / 观察与分析**：浏览已入库资料，筛选、原文跳转、时间线与词云。

### 新增结构
```text
collect/time_utils.py       # 统一北京时间；未知日期留空
collect/web_app.py          # 本机只读 API + 实时搜索/手动入库接口 + 静态页面
web/                       # 响应式界面，无构建步骤
test_collect_data.py        # 旧库、快照、时间与采集隔离回归
test_collect_regressions.py # 采集边界回归（5 项）
docs/frontend-design.md    # 视觉规范与数据口径
```
