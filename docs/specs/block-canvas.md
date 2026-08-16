# 产品规格说明书：Block Canvas (块级组卷排版引擎)

## 1. 背景与痛点 (Background)
当前项目以“试卷”作为组卷的主要形态，数据模型紧耦合了试卷与试题（通过 `paper_questions`），且导出排版严重依赖固化的 TeX/Word 模板。随着业务演进，系统将不仅需要生成标准试卷，还需要生成包含知识点讲解、例题、练习题等混排格式的“学案”、“练习册”或小颗粒度的“题组”。
为应对多样化的文档发布形态需求，必须将底层的组卷模型升级为通用的“文档-块（Document-Block/Publication-Block）”架构，即 Block Canvas。

## 2. 目标 (Goals)
- **底层统一**：构建 `Publication` (出版物/文档) 和 `PublicationBlock` (内容块) 的通用抽象数据模型，取代专用的试卷试题关联表，统一承载试卷、学案、题组等多种业务。
- **前端积木化编辑器**：实现一套无头（Headless）的可视化块级画布编辑器（Block Canvas），支持动态插入、拖拽排序不同类型的业务块（如富文本块、试题块）。
- **渲染插件化导出**：脱离固化的导出模板，实现基于 Pipeline 的流式导出引擎，按需将 Block 序列转换为中间态 Markdown 后渲染为 Docx/PDF 等最终成果物。

## 3. 架构设计 (Architecture)

### 3.1 核心数据模型 (Backend)
脱离具体业务局限，引入通用块级内容组织形式。
- **`Publication` 表**: 抽象的文档/发布物实体。包含核心属性 `title`, `meta_data`(JSON)，及 `pub_type` (如 `exam_paper`, `study_guide`, `question_group` 等，用于区分业务场景)。
- **`PublicationBlock` 表**: 构成出版物内容的积木块。
  - `publication_id`: 归属的文档 ID。
  - `type`: 块类型标识（如 `text`, `question`, `heading`, `page_break`）。
  - `sequence`: 在画布中的呈现顺序。
  - `content`: JSON类型，存储本块专有数据（如对于文本块则是富文本内容；对于试题块，可以存放本卷分值配置）。
  - `ref_id`: 可选的外部实体引用（如指向题库中某一题的 `question_id`）。

### 3.2 前端工程与能力 (Frontend)
- **画布底座 (`<BlockCanvas>`)**: 基于 `vuedraggable` 构建的通用容器，只负责负责块的流式渲染、拖放管控以及基础级的区块工具栏（上移、下移、删除、气泡加号菜单插入新块）。
- **动态组件注入与注册表 (Block Registry)**: 并排提供单独隔离的组件资产（如 `TextBlock.vue`, `QuestionBlock.vue`），在画布循环内通过 Vue 动态组件 `<component :is="...">` 按类型的分发渲染。
- **上下文感知 (Context Injection)**: 画布提供根级别的 Provider (如告知当前是在编辑讲义还是试卷)，子 Block 组件 Inject 并在内部做出展示适配（如讲义的题块强行展示答案，试卷的题块默认隐藏答案）。

### 3.4 导出渲染管线 (Export Pipeline)
- 在后端提供并注册各种类型 Block 专属的 `Renderer` 渲染插件。
- Pipeline 在导出时顺序编排 Block 树，由其自己的 Renderer 实现序列化为标准协议（如 Markdown 片段）。
- 将拼接成的长下文交由 Pandoc 和其他文印引擎生成最终样式，剔弃传统的整页面 TeX 挖空式模板注入做法。

## 4. 实施规划 (Phases)
- **第一阶段 (Phase 1)**: 落库底层，完成 `Publication` 与 `PublicationBlock` 等表设计、Alembic 迁移脚本，以及 CRUD 基础接口。开发最简易版本的后台 Export Renderer，打通由块转 MD 流程。
- **第二阶段 (Phase 2)**: 前端实现首版 `<BlockCanvas>` 引擎与最基础的 `TextBlock`、`QuestionBlock` 组件，具备拖拽排版以及多模块录入的基本视图。
- **第三阶段 (Phase 3)**: 用这套机制去“平替/重构”原先的`papers`试卷创建和编辑页面。
- **第四阶段 (Phase 4)**: （本底层稳固之后）在此基础上顺势落地“题组 (Question Group) 管理系统”及多端输出。
