# AI 桌面知识库 / Personal Memory App 项目方案与进度说明

## 1. 项目概述

本项目是一个本地优先的 AI 个人知识库应用，目标是让用户把每天的想法、项目记录、英语句子、技术笔记等内容保存到本机，并通过 AI 辅助完成检索、总结、标签生成、问答和每周复盘。

项目目前采用本地 Web App 形态：用户在浏览器中访问本机地址 `http://127.0.0.1:8000` 使用应用。后续可以在此基础上封装为真正的桌面端应用，例如使用 Tauri 或 Electron。

## 2. 项目定位

普通笔记软件主要解决“记录”和“分类”问题，本项目进一步加入 AI 能力，重点解决以下问题：

- 笔记内容越来越多后难以快速找到相关信息。
- 用户不一定会手动整理标签。
- 技术笔记、英语句子、项目想法等内容分散，缺少统一回顾。
- 用户希望数据保存在本地，不上传到云端。

因此，本项目的核心定位是：

> 一个保护隐私的本地 AI 个人记忆系统，用本地数据库和本地模型帮助用户管理长期知识。

## 3. 当前技术方案

### 3.1 总体架构

```text
Browser UI
   |
   | HTTP on 127.0.0.1
   v
FastAPI Backend
   |
   | stores notes, tags, summaries, embeddings
   v
SQLite Database
   |
   | optional local LLM calls
   v
Ollama Local LLM
```

### 3.2 技术栈

| 模块 | 技术 |
| --- | --- |
| 后端框架 | Python + FastAPI |
| 数据库 | SQLite |
| 前端 | HTML + CSS + Vanilla JavaScript |
| 模板渲染 | Jinja2 |
| 语义检索 | 本地 hash embedding，后续可切换 sentence-transformers |
| AI 总结/标签/问答 | Ollama 本地 LLM |
| 测试 | pytest + FastAPI TestClient |
| 后续桌面端方向 | Tauri 或 Electron |

### 3.3 本地隐私设计

本项目不需要云服务器。当前设计中：

- FastAPI 只绑定 `127.0.0.1`，默认不暴露到局域网。
- 笔记数据保存在本地 `SQLite` 数据库。
- embedding 向量也保存在本地数据库。
- Ollama 在用户电脑本地运行。
- 没有账号系统、云同步、第三方分析统计。

## 4. 已实现功能

### 4.1 添加笔记

已完成。

用户可以通过网页表单创建笔记，字段包括：

- 标题
- 来源/分类
- 正文内容

保存后，数据写入 SQLite。

### 4.2 自动总结

已完成基础版本。

实现方式：

- 如果 Ollama 可用，则调用本地 LLM 生成总结。
- 如果 Ollama 不可用，则使用本地 fallback 逻辑生成简短摘要。

这样可以保证应用在没有启动 Ollama 时也能继续使用。

### 4.3 自动打标签

已完成基础版本。

实现方式：

- Ollama 可用时，由本地 LLM 返回标签。
- Ollama 不可用时，系统从标题和正文中提取关键词作为标签。

### 4.4 语义搜索

已完成。

当前实现使用本地 hash embedding 生成向量，并结合关键词匹配进行排序。搜索结果会返回匹配分数。

当前设计保留了升级接口，后续可以切换为：

```text
sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

这样可以获得更强的中英文语义检索效果。

### 4.5 问答搜索

已完成。

流程：

1. 用户输入问题。
2. 系统先从本地笔记中检索相关内容。
3. 将相关笔记作为上下文交给 Ollama。
4. 返回回答和引用来源。

如果 Ollama 不可用，则返回本地 fallback 答案，并列出相关笔记来源。

### 4.6 每周 Review

已完成。

系统可以根据指定周范围内的笔记生成 weekly review。

当前能力：

- 获取一周内的笔记。
- 调用 Ollama 生成结构化周报。
- Ollama 不可用时生成本地基础周报。
- 将周报保存到 SQLite。

### 4.7 Web UI

已完成 MVP 版本。

页面包括：

- 左侧导航栏
- 添加笔记区域
- 搜索区域
- 最近笔记列表
- 问答区域
- 每周 Review 区域
- 本地隐私状态提示

UI 已做响应式布局，支持桌面和移动端宽度。

### 4.8 笔记编辑、删除、标签筛选与相似笔记

已完成。

- 每张笔记卡片提供 `View / Edit / Delete` 操作。
- `View` 打开详情弹窗，展示完整正文、标签，以及按 embedding 余弦相似度排序的相似笔记列表，点击相似笔记可继续跳转查看。
- `Edit` 在弹窗内切换为表单，保存后会重新调用 AI（或本地 fallback）生成总结、标签和 embedding，并刷新笔记列表。
- `Delete` 会先弹出确认框，确认后调用 `DELETE /api/notes/{id}`，依赖 SQLite 外键级联清理标签和 embedding。
- 标签筛选条从 `GET /api/tags` 拉取全部标签及计数，点击标签会同时过滤笔记列表和搜索结果；笔记卡片和搜索结果里的标签本身也可点击筛选。

### 4.9 搜索结果高亮

已完成。

搜索结果的标题和摘要中，命中查询词的部分会用 `<mark>` 高亮显示，帮助用户快速判断结果相关性。

### 4.10 间隔重复复习（Study Queue）

已完成。这是本项目提升学习效率的核心功能。

- 每条新笔记自动进入复习队列，无需手动添加。
- 复习界面采用记忆卡片形式：先只显示标题和标签（提示自己回忆内容），点击 "Show answer" 后显示完整正文。
- 回忆后按三档自评：
  - `Again`（忘了）：10 分钟后重新出现，熟练度下调。
  - `Good`（记得）：下次复习约 1 天后，之后每次按熟练度系数拉长间隔。
  - `Easy`（很熟）：下次复习约 3 天后，间隔增长更快。
- 调度算法为简化版 SM-2（Anki 同源算法）：每条笔记维护 `ease`（熟练度系数，初始 2.5，下限 1.3）、`interval_days`（当前间隔）、`reps`（连续记住次数），存储在 SQLite `review_states` 表中，删除笔记时级联清理。

### 4.11 学习统计面板

已完成。

- 笔记总数、本周新增、连续记录天数（streak）、当前待复习数、今日已复习数。
- 近 14 天笔记创建活动柱状图。
- 复习评分和新建/删除笔记后统计实时刷新。

### 4.12 Markdown 渲染

已完成。

笔记详情弹窗、复习卡片答案、AI 问答回答、Weekly Review 内容均支持 Markdown 显示，包括标题、加粗、斜体、行内代码、无序/有序列表和代码块。渲染器为本地 JavaScript 实现（先做 HTML 转义再解析），不引入任何 CDN 或第三方库，保持零外部依赖。

### 4.13 Markdown 导出

已完成。

顶栏 `Export` 按钮（或 `GET /api/export/markdown`）可将全部笔记按时间顺序导出为单个 Markdown 文件，包含标题、日期、来源、标签、AI 摘要和正文，方便备份或迁移到其他笔记工具。

### 4.14 键盘快捷键

已完成。

- `/`：聚焦搜索框。
- `n`：聚焦新笔记标题框。
- `Esc`：关闭详情弹窗。

在输入框内打字时快捷键不会误触发。

## 5. 项目文件结构

```text
.
├── README.md
├── requirements.txt
├── .env.example
├── app
│   ├── main.py
│   ├── db.py
│   ├── schemas.py
│   ├── settings.py
│   ├── services
│   │   ├── embeddings.py
│   │   ├── memory.py
│   │   └── ollama.py
│   ├── static
│   │   ├── app.js
│   │   └── styles.css
│   └── templates
│       └── index.html
├── tests
│   ├── test_api.py
│   └── test_memory_service.py
└── docs
    ├── project-review.md
    └── superpowers
        ├── specs
        └── plans
```

## 6. 核心模块说明

### 6.1 `app/main.py`

负责 FastAPI 应用入口，包括：

- 页面路由
- API 路由
- 静态资源挂载
- 服务初始化

主要 API：

- `GET /`
- `GET /api/health`
- `POST /api/notes`
- `GET /api/notes`（支持 `tag` 筛选参数）
- `GET /api/notes/{note_id}`（返回笔记详情和相似笔记）
- `PUT /api/notes/{note_id}`（编辑笔记，重新生成总结/标签/embedding）
- `DELETE /api/notes/{note_id}`（删除笔记）
- `GET /api/tags`（返回全部标签及使用次数）
- `GET /api/search`（支持 `tag` 筛选参数）
- `POST /api/ask`
- `GET /api/study/queue`（获取当前到期的复习队列）
- `POST /api/study/{note_id}/grade`（提交复习评分 again/good/easy）
- `GET /api/stats`（学习统计：总数、本周、streak、待复习、今日已复习、14 天活动）
- `GET /api/export/markdown`（导出全部笔记为 Markdown 文件）
- `GET /api/reviews/weekly`
- `POST /api/reviews/weekly`

### 6.2 `app/db.py`

负责 SQLite 数据库访问，包括：

- 初始化数据表
- 保存笔记
- 保存标签
- 保存 embedding 向量
- 保存 weekly review
- 查询笔记和周报
- 复习状态（`review_states` 表：到期时间、间隔、熟练度、连续记住次数）
- 学习统计查询（到期数、每日创建、今日复习数）

### 6.3 `app/services/memory.py`

负责业务逻辑，包括：

- 创建/编辑/删除笔记
- 搜索笔记（支持标签筛选）
- 推荐相似笔记
- 问答
- 生成 weekly review
- 间隔重复调度（简化版 SM-2：`study_queue` / `grade_note`）
- 学习统计（`stats`）
- Markdown 导出（`export_markdown`）

### 6.4 `app/services/embeddings.py`

负责本地 embedding。

当前默认使用 deterministic hash embedding，不需要下载模型，方便项目快速运行。后续可以切换为 `sentence-transformers`。

### 6.5 `app/services/ollama.py`

负责 Ollama 调用和本地 fallback。

设计重点：

- Ollama 可用时使用本地 LLM。
- Ollama 不可用时不影响笔记保存和搜索。
- 所有 AI 数据都留在本机。

## 7. 当前进度

| 功能 | 状态 |
| --- | --- |
| 项目结构搭建 | 已完成 |
| FastAPI 后端 | 已完成 |
| SQLite 存储 | 已完成 |
| 添加笔记 | 已完成 |
| 编辑笔记 | 已完成 |
| 删除笔记 | 已完成 |
| 标签筛选 | 已完成 |
| 相似笔记详情展示 | 已完成 |
| 搜索结果高亮 | 已完成 |
| 间隔重复复习（SM-2 简化版） | 已完成 |
| 学习统计面板 | 已完成 |
| Markdown 渲染 | 已完成 |
| Markdown 导出 | 已完成 |
| 键盘快捷键 | 已完成 |
| 自动总结 | 已完成基础版 |
| 自动标签 | 已完成基础版 |
| 本地 embedding | 已完成 |
| 语义搜索 | 已完成 |
| 问答搜索 | 已完成 |
| Weekly Review | 已完成 |
| Web UI | 已完成 MVP |
| 响应式布局 | 已完成基础版 |
| 单元测试/API 测试 | 已完成（18 项） |
| README | 已完成 |
| 后续桌面端架构预留 | 已完成 |
| GitHub 仓库 | 尚未创建 |
| Tauri/Electron 桌面封装 | 尚未开始 |

## 8. 验证结果

当前已运行自动化测试：

```bash
python3 -m pytest -q
```

结果：

```text
18 passed
```

已验证内容：

- 创建笔记可以写入 SQLite。
- 自动总结、标签和 embedding 会随笔记保存。
- 编辑笔记会重新生成总结、标签和 embedding，并正确持久化。
- 删除笔记会返回 404（针对已删除或不存在的笔记）并级联清理标签和 embedding。
- 标签筛选可以同时作用于笔记列表和搜索接口。
- 新笔记自动进入复习队列；评分 `good` 后间隔至少 1 天并移出当前队列；评分 `again` 会重置连续记住次数并下调熟练度；无效评分返回 400，不存在的笔记返回 404。
- 统计接口正确返回总数、待复习数、今日已复习数、streak 和 14 天活动。
- Markdown 导出包含全部笔记的标题和正文。
- 搜索接口能返回相关笔记。
- 问答接口能返回答案和引用来源。
- Weekly Review 可以生成并持久化。
- 首页可以正常渲染。
- favicon 不再产生 404 控制台错误。

同时做过本地浏览器实机验证（连接真实运行中的 Ollama 服务）：

- 创建笔记后自动生成总结和标签。
- 点击笔记卡片 `View` 打开详情弹窗，正确显示正文、标签和按相似度排序的相似笔记。
- 点击 `Edit` 修改正文后保存，标题、标签、相似笔记分数都随之更新。
- 点击标签筛选条或笔记/搜索结果里的标签，笔记列表按标签正确过滤。
- 搜索结果标题和摘要中命中的关键词被正确高亮。
- 点击 `Delete` 弹出确认框，确认后笔记从列表中移除，接口返回 `204`。
- 复习卡片完整流程：显示标题 → `Show answer` 展开正文 → 评分后自动切换下一张，待复习计数和统计面板实时更新。
- Markdown 笔记在详情弹窗中正确渲染标题、加粗、斜体、行内代码、无序/有序列表和代码块。
- `Export` 下载返回正确的 `Content-Disposition` 附件头和完整笔记内容。
- 快捷键 `/`、`n`、`Esc` 行为正确，输入框内不误触发。
- 移动端宽度（375px）无横向滚动溢出。
- 浏览器 console 无错误日志。

## 9. 运行与使用说明

### 9.1 安装与启动

安装依赖：

```bash
pip install -r requirements.txt
```

启动服务：

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

浏览器访问：

```text
http://127.0.0.1:8000
```

如果要启用 Ollama（可选，不启用时所有功能自动降级为本地 fallback）：

```bash
ollama pull qwen2.5
ollama serve
```

左侧边栏底部的 "Local only" 面板会显示 Ollama 当前状态（`ready` 或 `offline fallback`）。

### 9.2 日常使用流程（建议的学习工作流）

**第一步：随手记（Add note）**

- 在左上角 "Add note" 面板输入标题、来源（如 `english` / `project` / `tech`）和正文，点击 `Save note`。
- 正文支持 Markdown 语法（标题、加粗、列表、代码块等），在详情和复习时会格式化显示。
- 保存后系统自动生成一句话摘要和标签，无需手动整理。
- 快捷键：按 `n` 直接跳到标题输入框。

**第二步：每天花几分钟复习（Study queue）**

这是提升记忆效率的核心。每条新笔记会自动进入复习队列：

1. 看到卡片标题后，先在脑中回忆这条笔记讲了什么。
2. 点击 `Show answer` 查看正文对照。
3. 根据回忆效果自评：
   - `Again`：完全想不起来 → 10 分钟后再来一次。
   - `Good`：基本记得 → 约 1 天后再复习，之后间隔逐渐拉长。
   - `Easy`：非常熟 → 约 3 天后再复习，间隔增长更快。
4. 评分后自动出现下一张卡片，直到队列清空。

坚持每天清空复习队列，长期记忆效果远好于反复通读笔记。

**第三步：用统计保持节奏（Learning stats）**

- `Day streak` 显示连续记笔记的天数，保持它不断是最简单的自我激励。
- `Due to review` 提示今天还有多少条要复习。
- 14 天活动图直观展示最近的记录强度。

**第四步：需要时检索和提问**

- 搜索：按 `/` 聚焦搜索框，输入关键词即可（语义 + 关键词混合排序，命中词高亮）。点击标签筛选条可只看某一类笔记。
- 问答（Ask memory）：直接用自然语言提问，例如 "这周我学了哪些 FastAPI 相关的东西？"，系统会检索相关笔记并给出带引用来源的回答。
- 点击任意笔记卡片可查看完整内容和相似笔记，支持编辑和删除。

**第五步：每周复盘（Weekly review）**

每周末点击 `Generate this week`，系统汇总本周笔记生成结构化周报（主题、值得回顾的想法、建议的下一步行动）。

### 9.3 数据备份

- 所有数据保存在本地 `./data/memory.db`（SQLite），直接复制该文件即可完整备份。
- 也可以点击顶栏 `Export` 按钮，将全部笔记导出为一个 Markdown 文件，方便迁移到 Obsidian、Notion 等其他工具。

### 9.4 键盘快捷键一览

| 按键 | 功能 |
| --- | --- |
| `/` | 聚焦搜索框 |
| `n` | 聚焦新笔记标题框 |
| `Esc` | 关闭详情弹窗 |

## 10. 当前限制

当前版本是 MVP，还存在以下限制：

- 默认 embedding 是 hash embedding，语义理解能力不如真正的 sentence-transformers 模型。
- UI 是基础生产力工具风格，还可以继续优化视觉和交互细节。
- 尚未加入文件导入功能，例如 Markdown、PDF、网页剪藏。
- 尚未做真正桌面端安装包。
- 尚未创建 GitHub 远程仓库。
- 当前没有多用户和账号系统，因为项目目标是本地个人使用。

## 11. 后续开发计划

### 阶段 1：完善知识库基础功能（已完成）

- [x] 增加笔记编辑功能。`PUT /api/notes/{id}` 会重新调用 AI（或本地 fallback）生成总结、标签和 embedding，保证编辑后的检索质量不下降。
- [x] 增加笔记删除功能。`DELETE /api/notes/{id}` 依赖 SQLite 外键级联删除标签和 embedding。
- [x] 增加标签筛选。新增 `GET /api/tags` 返回标签及计数，`GET /api/notes` 和 `GET /api/search` 都支持 `tag` 参数；前端提供可点击的标签筛选条。
- [x] 增加相似笔记详情展示。点击笔记卡片打开详情弹窗，展示完整正文和基于 embedding 余弦相似度排序的相似笔记列表（复用已有的 `similar_notes` 服务方法）。
- [x] 增加搜索结果高亮。前端对查询词做转义和正则匹配，用 `<mark>` 包裹搜索结果标题和摘要中的命中词。

验证：14 项 pytest 全部通过（新增 6 项覆盖编辑、删除、标签筛选），并在本地浏览器中手动验证了创建、编辑、删除、标签筛选、相似笔记、搜索高亮的完整交互流程，同时确认了与本机 Ollama 服务的实时联动。

### 阶段 1.5：学习效率升级（已完成）

- [x] 间隔重复复习系统（Study queue，简化版 SM-2 调度）。
- [x] 学习统计面板（总数、本周、streak、待复习、今日已复习、14 天活动图）。
- [x] Markdown 渲染（详情、复习卡片、问答回答、周报，本地实现零依赖）。
- [x] 全库 Markdown 导出备份。
- [x] 键盘快捷键（`/` 搜索、`n` 记笔记、`Esc` 关弹窗）。

验证：18 项 pytest 全部通过（新增 4 项覆盖复习调度、统计、导出），并在浏览器中实机验证了复习评分流转、统计实时刷新、Markdown 渲染、导出下载和快捷键，移动端布局无溢出。

### 阶段 2：增强 AI 能力

- 接入 `sentence-transformers` 作为默认语义 embedding。
- 支持用户选择 Ollama 模型。
- 优化 prompt，使总结、标签、weekly review 更稳定。
- 增加中文和英文混合笔记的检索优化。

### 阶段 3：桌面端封装

建议使用 Tauri：

- Tauri 启动本地 FastAPI 后端。
- Tauri WebView 加载本地 UI。
- 数据库迁移到系统应用目录，例如 macOS：

```text
~/Library/Application Support/Local Memory/memory.db
```

这样可以把当前本地 Web App 转成真正的桌面应用。

### 阶段 4：发布和展示

- 初始化 git 仓库。
- 在 GitHub 账号 `khalilpong` 下创建仓库。
- 编写更完整的项目截图和演示说明。
- 准备简历项目描述。

## 12. 简历描述建议

英文简历可写：

```text
Built a local-first AI personal memory app with FastAPI, SQLite, semantic search, Ollama-powered summarization, and a desktop-ready architecture.
```

中文简历可写：

```text
开发了一个本地优先的 AI 个人知识库应用，基于 FastAPI 和 SQLite 实现笔记管理、语义搜索、自动总结、自动标签、问答检索和每周复盘，并预留桌面端封装架构。
```

## 13. 总结

目前项目已经完成一个可运行的 MVP。它满足最初提出的核心要求：

- Python + FastAPI 后端
- SQLite 本地存储
- 本地 embedding 搜索
- Ollama 本地 LLM 接入
- Web UI
- 创建笔记、搜索笔记、问答、weekly review
- 数据保存在本地
- 具备后续桌面端封装基础

下一步建议优先完善“编辑/删除笔记”和“sentence-transformers 语义模型”，然后再进行 Tauri 桌面端封装。
