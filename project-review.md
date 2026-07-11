# AI 桌面知识库 / Personal Memory App 项目方案与进度说明

## 1. 项目概述

本项目是一个本地优先的 AI 个人知识库应用，目标是让用户把每天的想法、项目记录、英语句子、技术笔记等内容保存到本机，并通过 AI 辅助完成检索、总结、标签生成、问答和每周复盘。

项目目前同时提供本地 Web App 和原生窗口两种运行形态：用户既可以在浏览器中访问 `http://127.0.0.1:8000`，也可以通过 `pywebview` 在独立桌面窗口中使用。后续仍可使用 Tauri 打包为可分发的 `.app` 安装包。

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
| 语义检索 | 本地 hash embedding（含中文 bigram，版本化自动重建），装上 sentence-transformers 后自动启用 |
| AI 总结/标签/问答 | Ollama 本地 LLM |
| 测试 | pytest + FastAPI TestClient |
| 桌面端 | pywebview 原生窗口；后续可升级为 Tauri 安装包 |

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
├── desktop.py
├── Local Memory.command
├── project-review.md
├── app
│   ├── main.py
│   ├── db.py
│   ├── schemas.py
│   ├── settings.py
│   ├── services
│   │   ├── documents.py
│   │   ├── embeddings.py
│   │   ├── library.py
│   │   ├── memory.py
│   │   ├── notion.py
│   │   ├── ocr.py
│   │   ├── ollama.py
│   │   ├── retrieval.py
│   │   └── webcapture.py
│   ├── static
│   │   ├── app.js
│   │   └── styles.css
│   └── templates
│       └── index.html
├── tests
│   ├── test_api.py
│   ├── test_document_parsers.py
│   ├── test_library_service.py
│   ├── test_memory_service.py
│   ├── test_notion_sync.py
│   ├── test_ocr_import.py
│   └── test_webcapture.py
└── docs
    ├── screenshots
    │   ├── dashboard-desktop.png
    │   └── dashboard-mobile.png
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
- `GET /api/models`（列出本机 Ollama 已安装模型及当前选用模型）
- `PUT /api/settings`（切换 Ollama 模型，持久化到 SQLite）
- `GET /api/courses` / `POST /api/courses` / `PUT /api/courses/{id}`（课程管理）
- `GET /api/library/documents` / `POST /api/library/import`（资料列表与多格式导入）
- `GET /api/library/documents/{id}` / `POST /api/library/documents/{id}/retry`（详情与失败重试）
- `POST /api/library/capture`（网页正文采集，带 SSRF 防护）
- `GET /api/notion/status` / `POST /api/notion/sync`（Notion 只读同步状态与触发）
- `GET /api/study/candidates`（获取待审批候选卡）
- `PUT /api/study/cards/{card_id}/approve` / `POST .../reject`（审批或拒绝候选卡）
- `GET /api/study/queue` / `POST /api/study/cards/{card_id}/grade`（独立卡片队列与评分）
- `GET /api/study-pack` / `POST /api/study-pack/import`（课程 Study Pack 导出和审核结果导入）
- `GET /api/backup` / `POST /api/backup/restore`（本地备份下载与恢复）
- `GET /api/diagnostics`（隐私安全运行诊断）
- `GET /api/courses/{course_id}/dashboard`（课程学习仪表盘指标）
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
| 中文 bigram 检索优化 | 已完成 |
| embedding 版本化自动重建 | 已完成 |
| Ollama 模型选择（UI + 持久化） | 已完成 |
| Prompt 优化（JSON 格式/低温度/语言跟随） | 已完成 |
| macOS 双击启动器 | 已完成 |
| 原生桌面窗口（pywebview） | 已完成 |
| 项目截图与演示说明 | 已完成 |
| 本地 git 仓库 | 已完成 |
| 课程资料库与多格式导入（5A） | 已完成 |
| 统一检索（笔记 + 文档分块，带引用） | 已完成 |
| 截图 OCR（macOS Vision，可插拔）（5B） | 已完成 |
| 网页正文采集 + SSRF 防护（5B） | 已完成 |
| Notion 只读同步（幂等 + 归档）（5B） | 已完成 |
| 可控复习卡 + ChatGPT Study Pack（5C） | 已完成 |
| 版本化事务迁移（5D） | 已完成 |
| 本地备份与恢复（5D） | 已完成 |
| 隐私安全诊断（5D） | 已完成 |
| 课程学习仪表盘（5D） | 已完成 |
| 自动总结 | 已完成基础版 |
| 自动标签 | 已完成基础版 |
| 本地 embedding | 已完成 |
| 语义搜索 | 已完成 |
| 问答搜索 | 已完成 |
| Weekly Review | 已完成 |
| Web UI | 已完成 MVP |
| 响应式布局 | 已完成基础版 |
| 单元测试/API 测试 | 已完成（99 项） |
| README | 已完成 |
| 后续桌面端架构预留 | 已完成 |
| GitHub 仓库 | 已建立：`khalilpong/Local-AI-learning-Manager` |
| Tauri .app 打包 | 可选项，待安装 Rust 工具链 |

## 8. 验证结果

当前已运行自动化测试：

```bash
python3 -m pytest -q
```

结果：

```text
99 passed
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
- 中文多字词查询（如"机器学习"）能把相关中文笔记排在无关笔记之前。
- 向量版本过期时 `ensure_embeddings` 会重建并且幂等（第二次调用返回 0）。
- 模型设置通过 `PUT /api/settings` 持久化，重启应用后仍然生效。
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
- 启动时旧库（hash-v1 向量）被自动迁移到 hash-v2，健康检查显示 `embedding: hash-v2-384`，搜索分数正常。
- 侧边栏模型下拉框正确列出本机 Ollama 已安装模型，切换 `deepseek-r1:14b` 后健康检查立即反映，写回 `qwen2.5` 同样生效。
- 浏览器 console 无错误日志。

## 9. 运行与使用说明

### 9.1 安装与启动

安装依赖：

```bash
pip install -r requirements.txt
```

**方式一（最简单）**：在 Finder 中双击项目根目录下的 `Local Memory.command`，会自动启动服务并打开浏览器；关闭那个终端窗口即停止服务。

**方式二（原生桌面窗口）**：

```bash
pip install pywebview
python3 desktop.py
```

应用会在独立的原生窗口中打开（无浏览器地址栏），关闭窗口即退出。

**方式三（命令行）**：

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

然后浏览器访问 `http://127.0.0.1:8000`。

如果要启用 Ollama（可选，不启用时所有功能自动降级为本地 fallback）：

```bash
ollama pull qwen2.5
ollama serve
```

左侧边栏底部的 "Local only" 面板会显示 Ollama 当前状态（`ready` 或 `offline fallback`）；上方的 **Ollama model 下拉框**列出本机已安装的全部模型，切换后立即生效并持久保存（重启不丢）。想用哪个模型，先 `ollama pull <模型名>` 再在下拉框里选择即可。

想获得更强的中英文语义检索（可选）：

```bash
pip install sentence-transformers
```

重启应用即可——embedding 后端默认为 `auto`，装好后自动启用，旧笔记的向量会在启动时自动重建，无需手动迁移。

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
- 复习卡已与笔记解耦；新笔记和文档分块只生成候选卡，批准后才进入复习。
- OCR 依赖本机安装 pyobjc（macOS Vision）；未安装时图片保持 `ocr_required`。
- Notion 同步和网页采集需要真实令牌/外网，未在当前沙箱做端到端联网验证。
- 尚未做真正桌面端安装包（.app），当前提供 pywebview 原生窗口和双击启动器。
- 尚未配置 GitHub Actions 等持续集成流程。
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

### 阶段 2：增强 AI 能力（已完成）

- [x] 中英文混合检索优化。分词器为相邻汉字生成二元组（bigram），使"机器学习"这类多字词能作为整体匹配，而不是散落的单字；已用中文笔记测试验证排序正确。
- [x] embedding 版本化与自动重建。每条向量记录生成它的模型版本（当前 `hash-v2-384`），启动时自动检测并重建过期向量，保证查询向量和笔记向量始终可比。这也让后续切换 sentence-transformers 时无需手动迁移。
- [x] embedding 后端默认值改为 `auto`：装好 `sentence-transformers` 后重启即自动启用（未安装时回落到 hash），旧向量会被自动重建。本机因未安装该库（依赖 torch 体积较大），当前实际运行 hash 后端。
- [x] 支持用户选择 Ollama 模型。新增 `GET /api/models`（列出本机已安装模型）和 `PUT /api/settings`（切换模型并持久化到 SQLite，重启后保留）；侧边栏提供下拉框，实测切换 `deepseek-r1:14b` 生效并正确持久化。
- [x] Prompt 优化：总结/标签改用 Ollama 的 `format: json` 强制 JSON 输出（不再依赖正则碰运气），温度调低（0.2/0.3）提升稳定性；摘要和回答要求跟随笔记/问题的语言（中文笔记出中文摘要）；问答和周报要求输出 Markdown（配合前端渲染）。

### 阶段 3：桌面端封装（已完成核心目标）

- [x] 原生桌面窗口 `desktop.py`：基于 `pywebview`（macOS 上使用系统 WKWebView），后端 FastAPI 在同一进程的后台线程中启动，UI 显示在独立原生窗口里（无浏览器地址栏/标签页），关窗即优雅停止服务。运行方式：`pip install pywebview && python3 desktop.py`。已实测窗口正常打开、后端健康检查通过、退出干净。
- [x] macOS 双击启动器 `Local Memory.command`：Finder 中双击即启动服务并自动打开浏览器，自动复用已在运行的实例。
- [x] 数据库位置可配置：`MEMORY_DB_PATH` 指到 `~/Library/Application Support/Local Memory/memory.db` 即完成应用目录迁移，无需改代码。
- [ ]（可选）Tauri 打包成 .app 安装包：需要先安装 Rust 工具链（rustup 或 `brew install rust`），适合作为发布环节再做；当前 pywebview 方案已提供等价的桌面使用体验。

### 阶段 4：发布和展示（部分完成）

- [x] 初始化 git 仓库：已在本地 `main` 分支完成首次提交，`.gitignore` 排除数据库、缓存和本地配置。
- [x] GitHub 远程仓库已建立：`khalilpong/Local-AI-learning-Manager`。本地代码通过独立发布分支和 Pull Request 合入 `main`，保留远端初始提交历史，不使用强制推送。

- [x] 编写项目截图和演示说明：截图保存在 `docs/screenshots/`（桌面版 + 移动版布局），README 新增 Screenshots 和 Demo Walkthrough 章节（六步演示流程：记录 → 复习 → 统计 → 检索 → 问答 → 周报）。
- [x] 简历项目描述（见第 12 节）。

### 阶段 5：完整学习工作流升级（实施中）

本阶段已经完成需求分析和架构选择，正式设计见：

`docs/superpowers/specs/2026-07-11-learning-workflow-upgrade-design.md`

总体分工确定为：Notion 管理课程、任务和正式笔记；ChatGPT 负责互动讲解、测验和综合分析；Local Memory 负责原始资料、统一检索、引用、复习卡和长期记忆。

本轮明确暂不实施 VPS、远程同步或公开部署，所有新增功能继续保持本地优先。

#### 5A：课程资料库与本地导入

- [x] 完成功能范围、数据模型、导入状态和验收标准设计。
- [x] 增加课程、原始文档和文档 chunk 数据表，并为旧笔记加入可空课程/来源关联；旧数据保持兼容。
- [x] 完成 Markdown、TXT、PDF、DOCX、PPTX 解析器和带引用位置的重叠分块；图片会明确返回 `ocr_required`。
- [x] 完成课程管理、资料上传/列表/详情和失败重试 API；重复导入返回已有资料，缺失资源统一返回 404。
- [x] 完成课程创建、批量文件导入、资料状态/失败重试界面，以及搜索和问答的课程筛选。
- [x] 增加受管理的本地原始文件库，采用临时文件写入和原子移动，上传大小默认限制为 100 MB。
- [x] 导入 Markdown、TXT、PDF、DOCX、PPTX，并接收和归档常见图片；图片在 5B OCR 完成前标记为 `ocr_required`。
- [x] 保存页码、幻灯片和标题层级等引用位置。
- [x] 使用 SHA-256 去重并支持失败重试；损坏资料保留原文件和可读错误状态。
- [x] 将笔记和文档分块加入统一搜索和问答；文档结果返回课程、原始文件名和标题/页码/段落/幻灯片位置。

#### 5B：截图、网页与 Notion（已完成）

- [x] 完成 OCR Provider、网页安全边界和 Notion 只读同步设计。
- [x] 截图 OCR：可插拔 `OcrProvider` 接口，提供 macOS Vision 后端（pyobjc，纯本地）和 `NullOcrProvider` 回退；导入图片时有 provider 就 OCR 并以「image OCR」引用位置入库，否则保持 `ocr_required` 并保留原图供重试；provider 就绪后重试即可补索引。
- [x] 网页正文采集：`capture_page` 抓取 HTTP(S) 页面，提取标题和正文（剥离 script/style），记录规范 URL 和抓取时间；SSRF 防护拒绝非 HTTP 协议、localhost、以及 loopback/私网/链路本地/保留/组播地址（IP 字面量直接判定，主机名解析后逐一校验，解析器可注入以保证离线测试），重定向后 URL 二次校验。
- [x] Notion 只读同步：`sync_notion` 通过可注入客户端拉取显式共享页面，单向且幂等；未变页面跳过、编辑页面重建索引、Notion 中消失的页面在本地归档（`archived_at`）而非删除，再次出现则解除归档；`HttpNotionClient` 仅从 `NOTION_TOKEN` 环境变量读取令牌，令牌绝不出现在任何 API 响应中。
- [x] 归档语义通过对 `source_documents` 安全 `ADD COLUMN archived_at` 迁移实现（已在既有数据库上验证），归档文档从列表和统一检索中排除。

验证：71 项 pytest 全部通过（新增 26 项覆盖 OCR、网页采集、SSRF 拒绝、Notion 幂等/归档/令牌保护）；浏览器实机验证了网页采集表单的 SSRF 拒绝提示、Notion 未配置时的禁用与提示、`archived_at` 迁移在既有库上无损、移动端无溢出、控制台无错误。因沙箱 DNS 将外网域名解析为私有地址，真实外网抓取与真实 Notion 令牌无法在此环境端到端验证，但索引与同步逻辑均以注入依赖完整覆盖。

#### 5C：可控复习与 ChatGPT Bridge（已完成）

- [x] 完成复习卡候选和 ChatGPT Study Pack 交接格式设计。
- [x] 将复习卡与笔记解耦，幂等迁移现有复习历史和调度参数。
- [x] 新笔记和文档 chunk 只生成候选卡，由用户编辑、批准或拒绝；active 卡可暂停。
- [x] 导出带课程资料、来源位置、现有卡和可复用课程指令的 `study-pack.md`。
- [x] 导入经用户审核的结构化 ChatGPT Markdown；笔记和候选卡保持本地且不会自动激活。

#### 5D：可靠性和学习仪表盘（已完成）

- [x] 版本化事务迁移：新增 `schema_migrations` 表和 `Database.schema_version()`，每个编号迁移在 SQLite savepoint 内执行、成功后才记录，失败整体回滚；重复 init 幂等。
- [x] 本地备份与恢复：`BackupService` 用 SQLite 在线备份 API 打包 manifest + 数据库 + 受管理文件库为校验过的 ZIP；恢复前拒绝非 ZIP、坏 manifest、绝对路径和 `../` 穿越，暂存目录做完整性校验后原子替换、失败回滚。`GET /api/backup` 下载、`POST /api/backup/restore`（2 GB 上限），前端「Local data」面板含下载和二次确认的恢复。
- [x] 隐私安全诊断：`GET /api/diagnostics` 报告数据库可写性/schema 版本/大小、存储可写性/剩余空间、解析器可用性、OCR/embedding/Ollama/Notion 状态，全部为能力布尔值，绝不含令牌、环境值或路径；前端诊断列表带 Ready / Action needed / Unavailable 徽章。
- [x] 课程学习仪表盘：`GET /api/courses/{id}/dashboard` 汇总笔记数、文档总数与未解决导入、候选/active/暂停/到期卡数、弱项卡（低熟练度或上次 `again`）和未来 7 天复习负担（逾期卡并入今日）；前端提供课程选择器、指标块、弱项列表和每日负担柱状图。

验证：`99 passed` 自动化测试（新增 backup/diagnostics/dashboard 及迁移覆盖）；`compileall`、`node --check`、`git diff --check` 全通过；备份往返实测（创建 → 拒绝损坏档 → 恢复，笔记与文档数不变）；浏览器实机验证诊断列表、仪表盘空态与含数据态（1 候选/3 active/2 到期、弱项卡、负担柱状图）、桌面与移动端无横向溢出、控制台无错误。

至此 Stage 5（完整学习工作流升级）5A–5D 全部完成。

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

Stage 5（完整学习工作流升级）5A–5D 已全部完成：课程资料库与多格式导入、统一引用检索、截图 OCR、网页采集、Notion 只读同步、可控复习卡与 ChatGPT Study Pack、版本化迁移、本地备份恢复、诊断与课程仪表盘，全部本地运行。VPS/远程同步/公开部署仍按设计暂缓。后续可选：Tauri 打包 .app、接入 sentence-transformers、GitHub Actions CI。
