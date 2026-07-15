# Question Bank 题库系统

AI 原生的题库系统

![](./docs/example-imports.png)

## 核心特性

- **多格式智能导入**：Word / Markdown / 图片，AI 抽取结构化题目
- **多题型支持**：单选、多选、填空（支持多解）、判断、解答题；富文本 + LaTeX 公式
- **AI 多供应商**：Gemini、OpenAI 及所有 OpenAI 兼容 API（DeepSeek、通义、私有部署等），配置存于数据库、可热切换
- **知识点 RAG**：ChromaDB 向量检索 + 批量重排序，把 AI 推荐的知识点映射到标准体系
- **审核工作流**：草稿 → 待审 → 发布 → 归档，含审核日志、软删除、批量操作
- **组卷 / 试题篮**：跨条件筛选、临时收藏、导出

## 主要功能

| 模块 | 说明 |
|------|------|
| 智能导入 | 上传 Word / Markdown / 图片，AI 自动抽取结构化题目（三步流程：上传 → 审核 → 入库） |
| 题库管理 | 多条件筛选、批量操作、知识点/标签关联、母子题结构编辑、软删除 |
| 知识点体系 | 按学科组织的树形知识点，向量化入库，支持 RAG 自动匹配 |
| AI 对话 | 多模型聊天（支持图片），可选 Provider / Model，对话历史持久化 |
| 审核工作流 | 草稿 → 待审 → 发布 → 归档，审核日志完整记录 |
| 学科 & 标签 | 学科 CRUD、标签分类管理 |
| 用户 & 权限 | 用户管理、角色控制、登录统计 |
| 操作审计 | 全局活动日志，支持分页与筛选 |
| 系统设置 | AI Provider / Model 热配置、Prompt Template 管理（超管专属） |
| 文件预览 | DOCX / Markdown 源文件在线预览 |

## 快速体验 (Quick Start)

### Docker Compose

```bash
# 1. 克隆仓库
git clone https://github.com/gygy-open/question-bank.git question-bank && cd question-bank

# 2. 生成环境变量文件并修改
cp .env.example .env
# 编辑 .env，至少设置 SECRET_KEY 和 MYSQL_PASSWORD
# 生成随机 SECRET_KEY: openssl rand -hex 32

# 3. 启动全部服务（MySQL + ChromaDB + Backend + Worker + Frontend）
docker compose up -d --build

# 4. 首次启动后初始化数据
docker compose exec backend python scripts/initial_data.py

# 5. 创建超级管理员
docker compose exec backend python scripts/create_superuser.py
```

访问：
- 前端：http://localhost
- 后端 API 文档：http://localhost:8000/docs


## 架构与设计

### 题目全景视图 (Question Entity Overview)

此图展示了“题目”这一核心实体的全景视图，包含其组成要素、关联信息以及在前端交互中的应用能力。

```mermaid
graph LR
    %% 核心节点
    Q((("题目<br>(Question)")))

    %% 一级分支
    Content["📝 内容信息"]
    Attr["🏷️ 属性分类"]
    Relation["🔗 关联关系"]
    Manage["⚙️ 管理信息"]
    Interact["👆 交互与应用"]

    Q --> Content
    Q --> Attr
    Q --> Relation
    Q --> Manage
    Q --> Interact

    %% 内容信息子节点
    Content --> C1("题干 (Markdown/Latex公式)")
    Content --> C2("选项 (JSON结构)")
    Content --> C3("参考答案 (填空支持多解/JSON)")
    Content --> C4("解析/思路/总结")

    %% 属性分类子节点
    Attr --> A1("题型 (单/多/填/判/解)")
    Attr --> A2("难度 (1-5星)")
    Attr --> A3("状态 (草稿/待审/发布/归档)")

    %% 关联关系子节点
    Relation --> R1("所属学科")
    Relation --> R2("知识点 (多对多)")
    Relation --> R3("标签 (多对多)")
    Relation --> R4("结构关系 (母题/子题/拆分)")

    %% 管理信息子节点
    Manage --> M1("创建/更新 (人/时间)")
    Manage --> M2("导入来源 (文件路径/任务)")
    Manage --> M3("审核 (计数/日志记录)")

    %% 交互与应用子节点 (基于组件能力)
    Interact --> I1("试题篮 (组卷)")
    Interact --> I2("源文件预览")
    Interact --> I3("结构化图谱查看")
    Interact --> I4("快速审核/编辑")

    %% 样式
    classDef core fill:#f9f,stroke:#333,stroke-width:4px,color:black;
    classDef branch fill:#e1f5fe,stroke:#0277bd,stroke-width:2px,color:black;
    classDef leaf fill:#fff,stroke:#666,stroke-dasharray: 5 5,color:black;

    class Q core;
    class Content,Attr,Relation,Manage,Interact branch;
    class C1,C2,C3,C4,A1,A2,A3,R1,R2,R3,R4,M1,M2,M3,I1,I2,I3,I4 leaf;
```

### 安全架构图 (Security Architecture)

此图展示了系统中各组件的安全隔离设计，确保用户数据和隐私得到保护，同时利用外部 AI 服务进行题目处理。

```mermaid
graph TD
    subgraph SafeZone ["服务器网络环境 (Private Network)"]
        User("用户 / 电脑")
        Server["业务系统服务器<br>(FastAPI Backend)"]
        
        subgraph DataStores [数据存储]
            direction TB
            MySQL[("MySQL<br>核心业务数据")]
            ChromaDB[("ChromaDB<br>向量索引数据")]
            FileSystem[("文件系统<br>文档/图片")]
        end
    end

    subgraph ExternalZone ["外部 AI 环境 (Public Internet)"]
        AI_Service(("AI 大模型服务<br>(Gemini / OpenAI)"))
    end

    %% 正常的业务流程
    User -- "1. HTTPS 请求" --> Server
    Server -- "2. 读写数据" --> MySQL
    Server -- "3. 语义检索" --> ChromaDB
    Server -- "4. 文件存取" --> FileSystem
    
    %% AI 的交互流程
    Server -- "5. 发送脱敏题目文本" --> AI_Service
    AI_Service -- "6. 返回解析/答案" --> Server

    %% 关键的安全隔离展示
    AI_Service -.-x|"❌ 物理隔离"| MySQL
    AI_Service -.-x|"❌ 物理隔离"| ChromaDB
    
    %% 样式定义
    classDef db fill:#ff9999,stroke:#333,stroke-width:2px,color:black;
    classDef srv fill:#99ccff,stroke:#333,stroke-width:2px,color:black;
    classDef ai fill:#eeeeee,stroke:#333,stroke-width:2px,stroke-dasharray: 5 5,color:black;
    
    %% 应用样式
    class MySQL,ChromaDB,FileSystem db;
    class Server srv;
    class AI_Service ai;
```

### 技术架构图 (Technical Architecture)

此图展示了系统的整体技术栈与模块交互关系，供开发人员参考。

```mermaid
graph TB
    subgraph Frontend ["前端 (Nuxt 4 SPA)"]
        direction TB
        UI_Comps["UI 组件<br>(Shadcn / Tailwind v4)"]
        Logic["业务逻辑<br>(Composables / useAPI)"]
        Editor_Engine["编辑器核心<br>(Tiptap + Mathlive + Katex)"]
        
        UI_Comps --> Logic
        UI_Comps --> Editor_Engine
    end

    subgraph Backend ["后端 (FastAPI + Python 3.13)"]
        direction TB
        API["API 路由 (Pydantic Schemas)"]
        Svc_Layer["服务层<br>(DocProcessor / AIProvider)"]
        DAL["数据层<br>(SQLAlchemy Async / Alembic)"]
        
        API --> Svc_Layer
        Svc_Layer --> DAL
    end

    subgraph Data_Infra ["数据基础设施"]
        MySQL[("MySQL<br>(结构化数据)")]
        ChromaDB[("ChromaDB<br>(向量数据)")]
        FS["本地文件系统<br>(Uploads / Static)"]
    end

    subgraph AI_Cloud ["外部 AI 服务"]
        LLM(("大模型 API<br>(Gemini / OpenAI)"))
    end

    %% Data Flow
    Logic <==>|"REST API (JSON)"| API
    DAL <==>|"aiomysql"| MySQL
    Svc_Layer <==>|"Vector Search"| ChromaDB
    Svc_Layer ==>|"File I/O"| FS
    Svc_Layer <==>|"HTTPS / SSE"| LLM

    %% Styling
    classDef fe fill:#dbeafe,stroke:#2563eb,color:black;
    classDef be fill:#dcfce7,stroke:#16a34a,color:black;
    classDef infra fill:#fef9c3,stroke:#ca8a04,color:black;
    classDef ai fill:#f3e8ff,stroke:#9333ea,color:black;

    class UI_Comps,Logic,Editor_Engine fe;
    class API,Svc_Layer,DAL be;
    class MySQL,ChromaDB,FS infra;
    class LLM ai;
```

### 知识点提取与 RAG 流程 (Knowledge Extraction Workflow)

此图展示了优化的 RAG (Retrieval-Augmented Generation) 流程，特别是批量重排序机制。

```mermaid
sequenceDiagram
    participant Doc as DocProcessor
    participant ChatAI as Chat Model (LLM)
    participant VDB as VectorStore (Chroma)
    
    Note over Doc: 1. 提取题目 (Extract)
    Doc->>ChatAI: 发送文档/图片 (extract_questions)
    ChatAI-->>Doc: 返回题目列表 (含 AI 推荐知识点)
    
    Note over Doc: 2. 向量检索候选 (Search)
    loop 每一道题目
        Doc->>Doc: 确定查询词 (优先用 AI 推荐知识点)
        Doc->>VDB: 搜索相似知识点 (Top 5)
        Note right of VDB: 使用 Embedding Model 向量化查询
        VDB-->>Doc: 返回候选标准知识点
        Doc->>Doc: 收集到 Batch 列表
    end
    
    Note over Doc: 3. 批量重排序 (Batch Rerank)
    Doc->>ChatAI: 发送所有题目 + 候选知识点 (batch_rerank)
    ChatAI-->>Doc: 返回每道题最相关的知识点
    
    Note over Doc: 4. 结果映射 (Map)
    Doc->>Doc: 将知识点映射回数据库 ID
    Doc->>Doc: 完成题目处理
```

## 本地开发

### 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Nuxt 4 (SPA) · Vue 3.5 · TypeScript · Tailwind v4 · Shadcn UI · Tiptap · KaTeX · MathLive |
| 后端 | Python 3.13 · FastAPI · SQLAlchemy 2.0 (Async) · Alembic · Pydantic |
| 数据 | MySQL 8 · ChromaDB · 本地文件系统 |
| AI | Google Gemini · OpenAI 兼容 API |
| 部署 | Docker Compose · Nginx |

### 目录结构

```
question-bank/
├── backend/            # FastAPI 后端
│   ├── app/            # 业务代码 (api/ crud/ models/ schemas/ services/)
│   ├── alembic/        # 数据库迁移
│   └── scripts/        # 运维脚本
├── frontend/           # Nuxt 4 SPA 前端
│   └── app/            # 页面、组件、composables
├── docker-compose.yml  # 一键部署
└── .env.example        # 环境变量模板
```

**后端：**
```bash
cd backend
cp .env.example .env
# 编辑 .env 配置本地 MySQL / ChromaDB 连接
uv sync
uv run alembic upgrade head
uv run python scripts/initial_data.py         # 初始化基础数据
uv run python scripts/create_superuser.py     # 创建管理员
uv run fastapi dev app/main.py                # 启动 API
uv run python -m app.worker                   # 另一个终端启动后台任务
```

**前端：**
```bash
cd frontend
pnpm install
pnpm dev
```
默认 `/api` 请求代理到后端 `http://localhost:8000`。

### AI 服务配置

AI Provider 配置存储在数据库中（`ai_providers` / `ai_models` 表），登录管理后台 → 系统设置 → AI 服务配置 中添加：

- **Google Gemini** — 需要 `GEMINI_API_KEY`
- **OpenAI 兼容** — 支持任何兼容 OpenAI API 的服务（如 DeepSeek、通义、私有部署等）

## 开源协议

本项目采用 [AGPL-3.0-or-later](./LICENSE) 协议。这意味着：

- ✅ 自由使用、修改、分发
- ✅ 商业使用
- ⚠️ **通过网络提供服务时**，必须公开你的修改代码
- ⚠️ 衍生作品必须使用相同的 AGPL 协议

## 贡献指南

欢迎贡献！请阅读 [CONTRIBUTING.md](./CONTRIBUTING.md)。
