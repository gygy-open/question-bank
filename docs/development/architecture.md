# 架构总览

本页面向开发者与部署者，概述系统的技术栈与分层。

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.13+、FastAPI、SQLAlchemy（Async）、Alembic、Pydantic |
| 前端 | Nuxt 4（SPA）、Vue 3.5+、TypeScript、Tailwind CSS v4、Shadcn UI |
| AI | 多供应商（Gemini / OpenAI 兼容），经 `AIProvider` 接口抽象 |
| 向量库 | ChromaDB |
| 数据库 | MySQL（服务器版） / SQLite（桌面版） |
| 打包 | Docker（服务器版）、PyInstaller + Inno Setup（桌面版） |

## 组件关系

```
                 ┌─────────────────┐
   用户浏览器  →  │  前端 Nuxt SPA   │
                 └────────┬────────┘
                          │ /api
                 ┌────────▼────────┐        ┌──────────────────────┐
                 │  后端 FastAPI    │  ───►  │ AI 供应商             │
                 └───┬────────┬────┘        │ Gemini / OpenAI 兼容  │
                     │        │             └──────────────────────┘
              ┌──────▼──┐  ┌──▼─────────┐
              │ 数据库   │  │ ChromaDB   │
              │MySQL/SQLite│ │ 向量库     │
              └────▲────┘  └──▲─────────┘
                   │          │
              ┌────┴──────────┴────┐
              │ Worker 后台任务      │  ◄── 后端入队(导入等)
              └────────────────────┘
```


## 分层与关键模块

**后端（`backend/app/`）**

- `api/` — 路由（`api/v1/endpoints/*`）
- `crud/` — 数据访问，继承 `crud/base.py:CRUDBase`
- `models/` — SQLAlchemy 模型
- `schemas/` — Pydantic 模型
- `services/` — 业务服务，如 `ai_provider.py`（AI 接口）、`doc_processor.py`（文档解析抽取）
- `core/config.py` — 静态配置
- `worker.py` — 后台任务处理

**前端（`frontend/app/`）**

- `pages/` — 页面路由
- `components/ui/` — UI 组件（Shadcn 风格）
- `composables/` — 如 `useAPI`
- `plugins/api.ts` — API 客户端（自动注入鉴权）

## 部署形态与本架构的关系

- **桌面版**：前端（静态）+ 后端 + Worker + SQLite 全部打进单个可执行文件，以托盘应用运行；ChromaDB 以本地形式使用。
- **服务器版**：各组件为独立容器（见 [Docker Compose 部署](/server/docker)）。

## AI 配置为数据库驱动

AI 供应商 / 模型 / Key 存于数据库（`ai_providers`、`ai_models`），而非环境变量，支持热切换。新增供应商需实现 `app/services/ai_provider.py` 中的 `AIProvider` 接口。

## 图解

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
