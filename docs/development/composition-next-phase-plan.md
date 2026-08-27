# 组稿系统导出与 Paper 迁移实施计划

## 1. 背景

组稿系统已经完成以下基础能力：

- 当前学科上下文中的共享组稿与个人组稿。
- 任意层级文件夹与软删除。
- 基础节点与 Module 并列的 CompositionNode AST 画布。
- `rich_text`、`heading`、`question`、`page_break` 基础节点。
- `question_details` 模块及“参考答案”“答案与解析”预设。
- Composition revision 乐观锁与操作时间线。
- 题目内容版本检测。
- 不可变定稿版本与只读快照预览。

当前旧版 Paper 与新版 Composition 暂时并存。新版定稿已经能够冻结完整题目内容，但 DOCX/LaTeX 导出仍只支持旧版 Paper。

本计划撰写后，草稿态编辑体验又新增了题号、赋分、题目级字段显隐覆盖、选项排版等能力（详见 3.1 末尾“待补口径”），这些能力目前只影响画布编辑，尚未在 `finalize_version`/Snapshot 中被完整冻结，导出实现启动前必须先补齐。

下一阶段目标是让 `CompositionVersion.snapshot` 成为正式发布和导出的唯一输入，并完成旧 Paper 的一次性迁移准备。当前 AST 与模块契约视为本阶段的稳定输入，不在导出实现中重新设计。

## 2. 阶段目标

### 2.1 必须交付

1. 从任意 CompositionVersion 导出 DOCX。
2. 从任意 CompositionVersion 导出 LaTeX ZIP。
3. 正确渲染基础节点、Module 及其具名 slot 子节点。
4. `question_details` 使用定稿时冻结的 `answer_item.source_question_node_id` 解析源 Question 节点，不得重新查询当前题库。
5. 导出过程不得依赖实时 Question 数据。
6. 前端版本预览页提供导出入口和完整状态反馈。
7. 建立 Paper 到 Composition 的数据迁移程序、校验报告和回滚方案。

### 2.2 本阶段不做

- 实时协作或 CRDT。
- 版本修改、删除或覆盖。
- 公网分享链接。
- 审批流。
- 多栏布局。
- PDF 原生渲染。
- 模板市场。

## 3. 架构原则

### 3.1 已落地的输入架构

导出实现必须建立在以下事实之上：

- `CompositionNode` 使用客户端生成的 UUID 标识，`node_kind` 为 `block | module | reference`。
- 根层包含 `rich_text`、`heading`、`question`、`page_break` 与 `question_details`；模块子节点统一位于 `body` slot。
- 首期 AST 只有 root 与 module body 两层，Module 不允许嵌套。
- `question` 节点保存 `question_id`、`question_revision` 和服务端冻结的题目内容。
- `question_details` 保存 `scope` 与完整的四字段全局开关。
- `answer_item` 通过 `source_question_node_id` 指向同一文档中的根层 Question Node，并保存 `included` 与完整的四字段 nullable override。
- 保存 AST 时，服务端已经根据 `before | all` 规范化 `answer_item` 集合和题序；自定义 Heading/RichText 通过 `anchor_before_node_id` 固定在某答案项之前或模块尾部。
- `question` 节点 `props` 现在还可携带：`number`（题号字符串）、`show`（按 `answer/thinking/analysis/summary` 四键的显隐覆盖，值为 `true/false/缺省`，缺省表示继承 Composition 级全局默认）、`optionLayout`（`auto | 1 | 2 | 4` 选项排版列数）、`score`（0~1000，允许 0.5 步进的分值）。这些字段只在用户点击“保存内容”时随 AST 一起持久化。
- Composition 本身新增 `numbering_enabled`、`scoring_enabled`（依赖 `numbering_enabled`，关闭题号会级联关闭赋分）、`question_display`（四字段全局显隐默认值）三个即时持久化（PATCH 生效、不走“保存内容”）的草稿态开关；节点最终“是否显示某字段”= `question.props.show[key] ?? question_display[key]`。
- **待补口径（导出实现前必须解决）**：`_build_snapshot` 当前只冻结每个 `question` 节点自身的 `props`，Composition 级 `numbering_enabled` / `scoring_enabled` / `question_display` 并未写入 Snapshot 顶层元数据。若定稿时某题的 `show` 某字段仍是“继承全局”（未显式覆盖），Snapshot 里将没有信息还原其最终应显示还是隐藏，导出结果会和编辑器预览不一致。必须在编码前二选一并写入 ADR：(a) 冻结时把三个 Composition 级默认值一并写入 Snapshot 顶层，交给 CompositionAssembler 按“节点覆盖 ?? 全局默认”解析；或 (b) 冻结时为每个 `question` 节点把 effective show/number/score 结果展开成完整、无缺省的 `props` 再写入 Snapshot。
- Snapshot schema version 为 `2`，`nodes` 按前序展平：每个 root node 后紧跟其按 position 排序的 module children。

导出层不得把 `question_details.scope` 当作重新生成答案项的指令；它只能消费 Snapshot 中已经冻结的 `answer_item` 与自定义子节点。

### 3.2 版本驱动

导出接口只接受 `composition_id + version_no`，读取对应的不可变 Snapshot。

禁止以下行为：

- 从草稿直接导出。
- 导出时重新读取 Question 表。
- 根据当前草稿重新计算历史版本中的模块题目范围或字段配置。
- 因题库更新而改变旧版本导出结果。

### 3.3 中间表示

新增与来源无关的导出中间结构，例如：

```text
CompositionVersion.snapshot
        ↓
CompositionAssembler
        ↓
ExportDocument
        ↓
DOCXRenderer / LaTeXRenderer
```

`CompositionAssembler` 负责解释节点与 Module 语义，Renderer 只负责格式输出。

不得把 Composition Snapshot 解析逻辑分别复制到 DOCX 与 LaTeX Renderer。

### 3.4 节点与模块注册表

基础节点和 Module 分别对应明确的 assembler handler：

| 类型 | 输出语义 |
|---|---|
| `rich_text` | RichDoc 内容 |
| `heading` | 指定级别的标题 |
| `question` | 冻结的题干、选项及可选编号、分值、选项排版列数，并按 effective show 内联输出 answer/thinking/analysis/summary |
| `page_break` | 强制分页 |
| `question_details` | 按 Snapshot 中已冻结的 body slot 顺序展开自定义内容与 answer_item |
| `answer_item` | 从同一 Snapshot 的源 Question 节点输出生效字段 |

未知 Node/Module Type 必须返回可定位的导出错误，不允许静默丢弃。

## 4. 后端实施任务

### 4.1 定义导出契约

新增 Composition 导出请求：

```json
{
  "format": "docx",
  "title": "可选覆盖标题"
}
```

首期格式：

- `docx`
- `latex`

建议端点：

```http
POST /api/v1/subjects/{subject_id}/compositions/{composition_id}/versions/{version_no}/export?scope=shared
```

必须沿用 Subject、Scope 和个人 Owner 的资源校验。

### 4.2 CompositionAssembler

建议新增：

```text
backend/app/services/exporting/composition_assemble.py
```

职责：

- 校验 Snapshot `schema_version`。
- 从前序展平的 `nodes` 重建 root/module body 关系，并校验 parent、slot 和 position。
- 按冻结 AST 顺序构造格式无关的 `ExportDocument`。
- 为题目生成稳定题号。
- 将 `answer_item.source_question_node_id` 映射到同一 Snapshot 内嵌的 Question 节点。
- 解析“题目级 override > module 全局字段”的最终显示规则。
- 按持久化的 `answer_item` 顺序输出，不根据 module scope 重算题目范围。
- 校验锚点、引用和父子归属，返回包含 Node UUID、slot 和 position 的错误信息。

### 4.3 扩展导出中间结构

检查并按需扩展现有：

- `backend/app/services/exporting/contracts.py`
- `backend/app/services/exporting/renderers/docx.py`
- `backend/app/services/exporting/renderers/latex.py`
- `backend/app/services/exporting/richdoc/`

建议增加的节点：

- `ExportHeading`
- `ExportRichText`
- `ExportQuestion`
- `ExportPageBreak`
- `ExportQuestionDetails`

应复用现有 RichDoc、公式、表格、图片、题目选项、答案和解析渲染能力。

`ExportQuestion` 需要额外携带：题号（`number`）、分值（`score`，允许为空）、选项排版列数（依据 `optionLayout` 与选项内容解析出的最终列数，不在 Renderer 里重新做“宽内容强制单列”的判断）、以及按 effective show 解析出的内联 answer/thinking/analysis/summary 内容。effective show 的解析规则见 3.1 “待补口径”。

### 4.4 导出错误模型

错误响应至少包含：

```json
{
        "detail": "Unsupported snapshot node",
        "node_id": "00000000-0000-4000-8000-000000000000",
        "node_type": "unknown",
  "version_no": 3
}
```

对损坏 Snapshot、缺失内嵌题目、无法解析的 RichDoc，必须返回 422；权限或上下文不匹配返回 404。

### 4.5 导出测试

必须覆盖：

- 富文本、表格、图片和公式。
- H1-H4 标题。
- 选择题、填空题和主观题。
- 分页。
- `question_details: all` 与 `before`。
- 模块全局四字段开关、题目级覆盖和排除。
- 模块内自定义标题、富文本、图片和公式。
- 同一题目重复出现时按不同 Question 节点 UUID 分别输出。
- 题库内容更新后旧版本导出不变。
- 题目软删除后旧版本仍可导出。
- 相同版本重复导出的语义内容一致。
- 题号、赋分开关级联关闭、选项排版（auto/1/2/4，含宽内容强制单列）在导出中的还原。
- 题目级 `show` 覆盖与 Composition 级 `question_display` 全局默认的组合（显式 true/false、以及继承全局两种情况）。
- 100+ Node 长组稿。

## 5. 前端实施任务

### 5.1 导出入口

在版本只读页增加导出按钮：

- Word
- LaTeX

导出按钮不得出现在未定稿草稿上。

### 5.2 状态反馈

必须提供：

- 请求中状态。
- 下载成功反馈。
- 422 Node 定位错误。
- 404 权限或版本不存在提示。
- 文件名清理和浏览器下载。

建议文件名：

```text
{composition-title}-v{version-no}.docx
{composition-title}-v{version-no}-latex.zip
```

### 5.3 预览一致性

前端 SnapshotRenderer 和后端 CompositionAssembler 必须使用相同语义：

- 相同标题层级。
- 相同题目顺序、题号和分值。
- 相同模块子节点、字段配置和源题引用。
- 相同选项排版列数。
- 相同的题目级内联字段显隐结果（`show` 覆盖与 `question_display` 全局默认的合并结果）。
- 相同分页位置。

可允许样式差异，不允许内容差异。截至目前，只读版本预览用的 `SnapshotRenderer.vue` 尚未渲染题号（`props.number`）、分值（`props.score`）以及题目级内联 `show` 字段——这些是画布编辑器新增的能力，早于 Snapshot 顶层口径问题（见 3.1）被引入。在实现 CompositionAssembler/Renderer 之前，应先补齐 `SnapshotRenderer` 对这些字段的渲染，作为导出实现的可视化基线；两者应共用同一套 effective show/layout 解析逻辑（如 `frontend/app/lib/compositionDocument.ts` 中的 `effectiveQuestionField`/`resolveOptionColumns`），避免各自重复实现产生偏差。

## 6. Paper 迁移计划

### 6.1 迁移规则

每个 Paper 转为一个 Personal Composition：

| Paper 字段 | Composition 字段 |
|---|---|
| `owner_id` | `owner_id` |
| `subject_id` | `subject_id` |
| `title` | `title` |
| `description` | `description` |
| `status` | `status` |

`paper_questions` 按 `sequence` 转换：

- `section_title` 非空且与前一项不同：插入 `heading` 节点。
- 每条关联插入一个 `question` 节点，并在迁移脚本中生成 UUID。
- `score` 放入 Question 节点中性展示属性；如果当前 Node Schema 尚未支持分值，应先补充 `props.score` 契约。

### 6.2 迁移策略

迁移分三步运行：

1. `audit`：只检查，不写数据。
2. `migrate`：事务式批量迁移并记录 Paper 与 Composition 映射。
3. `verify`：逐条比较标题、学科、Owner、题目数量、顺序、大题标题和分值。

迁移脚本必须可重复运行，不得重复创建 Composition。建议建立临时映射表或为 Composition 增加仅迁移使用的来源标识；具体方案在编码前通过 ADR 确认。

### 6.3 切换顺序

1. 完成并验证 Composition 导出。
2. 在测试环境运行 Paper 审计与迁移。
3. 前端题库“加入试卷”入口替换为“插入组稿”。
4. 生产环境备份数据库。
5. 运行迁移和 verify。
6. 隐藏旧 Paper 导航和写入口。
7. 保留旧表一个发布周期，仅只读回滚使用。
8. 验收通过后再创建删除旧表的独立迁移。

不得在同一迁移中同时迁移数据并删除 Paper 表。

## 7. 建议实施顺序

1. 定义 `ExportDocument` 扩展和 CompositionAssembler 单元测试。
2. 实现基础节点与 Module registry 到中间结构的转换。
3. 接入 DOCX Renderer。
4. 接入 LaTeX Renderer。
5. 增加版本导出 API 和权限测试。
6. 增加前端导出入口。
7. 执行跨格式金丝雀测试。
8. 编写 Paper audit/migrate/verify 脚本。
9. 在副本数据库演练迁移和回滚。
10. 切换题库入口及旧 Paper 导航。

## 8. 完成定义

下一阶段仅在以下条件全部满足后完成：

- DOCX 与 LaTeX 均从 CompositionVersion Snapshot 生成。
- 导出过程中没有实时 Question 查询。
- 旧版本在题库修改或删除后仍能复现。
- SnapshotRenderer 与两个导出格式的内容语义一致。
- Paper 迁移审计、迁移、验证和回滚均在数据库副本演练通过。
- 后端全套测试、前端全套测试、静态生成及 MySQL 迁移测试通过。
- 验收文档中的 P0 与 P1 用例全部通过。

## 9. 风险与控制

| 风险 | 控制措施 |
|---|---|
| Snapshot JSON 体积较大 | 版本列表禁止返回 snapshot；只在详情和导出读取 |
| DOCX 与 LaTeX 内容不一致 | 共用 CompositionAssembler 与 ExportDocument |
| 图片资源失效 | 定稿时验证资源可访问；后续考虑资源归档 |
| 迁移产生重复数据 | 幂等来源映射与 verify 报告 |
| Paper 一次性下线无法回滚 | 旧表保留一个发布周期，写入口先关闭 |
| 未知 Node/Module 被忽略 | assembler 显式报错并返回 node UUID、slot 与 position |
| 大组稿导出超时 | 压测后超过阈值转后台任务，不提前引入复杂队列 |
