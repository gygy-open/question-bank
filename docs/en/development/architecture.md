# Architecture

This page is for developers and deployers. It outlines the system's tech stack and layering.

## Tech Stack

| Layer | Technology |
|----|------|
| Backend | Python 3.13+, FastAPI, SQLAlchemy (Async), Alembic, Pydantic |
| Frontend | Nuxt 4 (SPA), Vue 3.5+, TypeScript, Tailwind CSS v4, Shadcn UI |
| AI | Multiple providers (Gemini / OpenAI-compatible), abstracted behind the `AIProvider` interface |
| Vector store | ChromaDB |
| Database | MySQL (Server edition) / SQLite (Desktop edition) |
| Packaging | Docker (Server edition), PyInstaller + Inno Setup (Desktop edition) |

## Component Relationships

```
                 ┌──────────────────┐
   Browser    →  │ Frontend Nuxt SPA │
                 └────────┬─────────┘
                          │ /api
                 ┌────────▼────────┐        ┌──────────────────────┐
                 │ Backend FastAPI  │  ───►  │ AI providers          │
                 └───┬────────┬────┘        │ Gemini / OpenAI-compat│
                     │        │             └──────────────────────┘
              ┌──────▼─────┐ ┌▼───────────┐
              │ Database    │ │ ChromaDB   │
              │MySQL/SQLite │ │ vectors    │
              └────▲───────┘ └▲───────────┘
                   │          │
              ┌────┴──────────┴────┐
              │ Worker (bg jobs)    │  ◄── enqueued by backend (imports, etc.)
              └────────────────────┘
```


## Layers and Key Modules

**Backend (`backend/app/`)**

- `api/` — routes (`api/v1/endpoints/*`)
- `crud/` — data access, inheriting from `crud/base.py:CRUDBase`
- `models/` — SQLAlchemy models
- `schemas/` — Pydantic models
- `services/` — business services, such as `ai_provider.py` (AI interface) and `doc_processor.py` (document parsing and extraction)
- `core/config.py` — static configuration
- `capabilities/` — business use cases (Capabilities) shared by REST, AI chat, the worker and MCP, with one set of authorization and logic; the entry point is recorded in `ExecutionContext.surface` (`api`/`chat`/`worker`/`mcp`)
- `mcp_server/` — MCP server (`/api/mcp`, same port as the API): API key auth middleware that maps Capabilities and read-only queries to MCP tools; see [MCP Access](/en/features/mcp)
- `worker.py` — background job processing

**Frontend (`frontend/app/`)**

- `pages/` — page routes
- `components/ui/` — UI components (Shadcn style)
- `composables/` — e.g. `useAPI`
- `plugins/api.ts` — API client (injects auth automatically)

## Deployment Modes and This Architecture

- **Desktop edition**: the frontend (static), backend, Worker and SQLite are all bundled into a single executable that runs as a tray app; ChromaDB is used locally.
- **Server edition**: each component runs in its own container (see [Docker Compose Deployment](/en/server/docker)).

## Database-Driven AI Configuration

AI providers, models and keys are stored in the database (`ai_providers`, `ai_models`, `user_ai_preferences`) rather than in environment variables, so they can be switched on the fly. An empty `ai_providers.owner_id` means a global provider; a non-empty one means a user's personal provider. Keys are stored encrypted (`app/core/secrets.py`). All callers resolve models through `app/services/ai_resolver.py` in the order "explicitly specified → personal default → global". To add a provider, implement the `AIProvider` interface in `app/services/ai_provider.py`.

## Diagrams

### Question Entity Overview

This diagram gives a full view of the core "Question" entity: its components, related information, and what it supports in the frontend.

```mermaid
graph LR
    %% Core node
    Q((("Question")))

    %% First-level branches
    Content["📝 Content"]
    Attr["🏷️ Attributes"]
    Relation["🔗 Relations"]
    Manage["⚙️ Management"]
    Interact["👆 Interaction & Use"]

    Q --> Content
    Q --> Attr
    Q --> Relation
    Q --> Manage
    Q --> Interact

    %% Content children
    Content --> C1("Stem (Markdown/LaTeX formulas)")
    Content --> C2("Options (JSON structure)")
    Content --> C3("Reference answer (fill-in-the-blank supports multiple answers/JSON)")
    Content --> C4("Explanation/Approach/Summary")

    %% Attribute children
    Attr --> A1("Question type (single/multiple/fill-in/true-false/free response)")
    Attr --> A2("Difficulty (1-5 stars)")
    Attr --> A3("Status (draft/pending review/published/archived)")

    %% Relation children
    Relation --> R1("Subject")
    Relation --> R2("Knowledge points (many-to-many)")
    Relation --> R3("Tags (many-to-many)")
    Relation --> R4("Structure (parent/sub-question/split)")

    %% Management children
    Manage --> M1("Created/updated (by/at)")
    Manage --> M2("Import source (file path/task)")
    Manage --> M3("Review (count/log records)")

    %% Interaction children (based on component capabilities)
    Interact --> I1("Question basket (paper assembly)")
    Interact --> I2("Source file preview")
    Interact --> I3("Structure graph view")
    Interact --> I4("Quick review/edit")

    %% Styles
    classDef core fill:#f9f,stroke:#333,stroke-width:4px,color:black;
    classDef branch fill:#e1f5fe,stroke:#0277bd,stroke-width:2px,color:black;
    classDef leaf fill:#fff,stroke:#666,stroke-dasharray: 5 5,color:black;

    class Q core;
    class Content,Attr,Relation,Manage,Interact branch;
    class C1,C2,C3,C4,A1,A2,A3,R1,R2,R3,R4,M1,M2,M3,I1,I2,I3,I4 leaf;
```

### Security Architecture

This diagram shows how the system's components are isolated for security, keeping user data and privacy protected while still using external AI services to process questions.

```mermaid
graph TD
    subgraph SafeZone ["Server network (Private Network)"]
        User("User / computer")
        Server["Application server<br>(FastAPI Backend)"]
        
        subgraph DataStores [Data stores]
            direction TB
            MySQL[("MySQL<br>core business data")]
            ChromaDB[("ChromaDB<br>vector index data")]
            FileSystem[("File system<br>documents/images")]
        end
    end

    subgraph ExternalZone ["External AI (Public Internet)"]
        AI_Service(("AI LLM service<br>(Gemini / OpenAI)"))
    end

    %% Normal business flow
    User -- "1. HTTPS request" --> Server
    Server -- "2. Read/write data" --> MySQL
    Server -- "3. Semantic search" --> ChromaDB
    Server -- "4. File access" --> FileSystem
    
    %% AI interaction flow
    Server -- "5. Send de-identified question text" --> AI_Service
    AI_Service -- "6. Return explanation/answer" --> Server

    %% Key security isolation
    AI_Service -.-x|"❌ Physically isolated"| MySQL
    AI_Service -.-x|"❌ Physically isolated"| ChromaDB
    
    %% Style definitions
    classDef db fill:#ff9999,stroke:#333,stroke-width:2px,color:black;
    classDef srv fill:#99ccff,stroke:#333,stroke-width:2px,color:black;
    classDef ai fill:#eeeeee,stroke:#333,stroke-width:2px,stroke-dasharray: 5 5,color:black;
    
    %% Apply styles
    class MySQL,ChromaDB,FileSystem db;
    class Server srv;
    class AI_Service ai;
```

### Technical Architecture

This diagram shows the overall tech stack and how modules interact, for developer reference.

```mermaid
graph TB
    subgraph Frontend ["Frontend (Nuxt 4 SPA)"]
        direction TB
        UI_Comps["UI components<br>(Shadcn / Tailwind v4)"]
        Logic["Business logic<br>(Composables / useAPI)"]
        Editor_Engine["Editor core<br>(Tiptap + Mathlive + Katex)"]
        
        UI_Comps --> Logic
        UI_Comps --> Editor_Engine
    end

    subgraph Backend ["Backend (FastAPI + Python 3.13)"]
        direction TB
        API["API routes (Pydantic Schemas)"]
        Svc_Layer["Service layer<br>(DocProcessor / AIProvider)"]
        DAL["Data layer<br>(SQLAlchemy Async / Alembic)"]
        
        API --> Svc_Layer
        Svc_Layer --> DAL
    end

    subgraph Data_Infra ["Data infrastructure"]
        MySQL[("MySQL<br>(structured data)")]
        ChromaDB[("ChromaDB<br>(vector data)")]
        FS["Local file system<br>(Uploads / Static)"]
    end

    subgraph AI_Cloud ["External AI services"]
        LLM(("LLM API<br>(Gemini / OpenAI)"))
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

### Knowledge Extraction Workflow

This diagram shows the optimized RAG (Retrieval-Augmented Generation) flow, in particular the batch reranking mechanism.

```mermaid
sequenceDiagram
    participant Doc as DocProcessor
    participant ChatAI as Chat Model (LLM)
    participant VDB as VectorStore (Chroma)
    
    Note over Doc: 1. Extract questions (Extract)
    Doc->>ChatAI: Send document/images (extract_questions)
    ChatAI-->>Doc: Return question list (with AI-suggested knowledge points)
    
    Note over Doc: 2. Vector search for candidates (Search)
    loop For each question
        Doc->>Doc: Pick query terms (prefer AI-suggested knowledge points)
        Doc->>VDB: Search similar knowledge points (Top 5)
        Note right of VDB: Query embedded with the Embedding Model
        VDB-->>Doc: Return candidate standard knowledge points
        Doc->>Doc: Collect into batch list
    end
    
    Note over Doc: 3. Batch rerank (Batch Rerank)
    Doc->>ChatAI: Send all questions + candidate knowledge points (batch_rerank)
    ChatAI-->>Doc: Return the most relevant knowledge points per question
    
    Note over Doc: 4. Map results (Map)
    Doc->>Doc: Map knowledge points back to database IDs
    Doc->>Doc: Finish question processing
```
