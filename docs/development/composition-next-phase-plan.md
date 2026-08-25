# 组稿系统下一阶段实施计划

## 1. 背景

组稿系统已经完成以下基础能力：

- 当前学科上下文中的共享组稿与个人组稿。
- 任意层级文件夹与软删除。
- 线性 Block 画布。
- `rich_text`、`heading`、`question`、`page_break`、`answer_summary` 五类 Block。
- Composition revision 乐观锁与操作时间线。
- 题目内容版本检测。
- 不可变定稿版本与只读快照预览。

当前旧版 Paper 与新版 Composition 暂时并存。新版定稿已经能够冻结完整题目内容，但 DOCX/LaTeX 导出仍只支持旧版 Paper。

下一阶段目标是让 `CompositionVersion.snapshot` 成为正式发布和导出的唯一输入，并为旧 Paper 一次性迁移做好准备。

## 2. 阶段目标

### 2.1 必须交付

1. 从任意 CompositionVersion 导出 DOCX。
2. 从任意 CompositionVersion 导出 LaTeX ZIP。
3. 正确渲染五类 Block。
4. `answer_summary` 使用定稿时冻结的 `resolved_question_ids`，不得重新查询当前题库。
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

### 3.1 版本驱动

导出接口只接受 `composition_id + version_no`，读取对应的不可变 Snapshot。

禁止以下行为：

- 从草稿直接导出。
- 导出时重新读取 Question 表。
- 根据当前画布重新计算答案汇总范围。
- 因题库更新而改变旧版本导出结果。

### 3.2 中间表示

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

`CompositionAssembler` 负责解释 Block 语义，Renderer 只负责格式输出。

不得把 Composition Snapshot 解析逻辑分别复制到 DOCX 与 LaTeX Renderer。

### 3.3 渲染注册表

每类 Block 对应一个明确的 assembler handler：

| Block | 输出语义 |
|---|---|
| `rich_text` | RichDoc 内容 |
| `heading` | 指定级别的标题 |
| `question` | 冻结的题干、选项及可选编号 |
| `page_break` | 强制分页 |
| `answer_summary` | 按冻结 ID 顺序输出答案和解析 |

未知 Block Type 必须返回可定位的导出错误，不允许静默丢弃。

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
- 按 Block 顺序构造格式无关的 `ExportDocument`。
- 为题目生成稳定题号。
- 将 `answer_summary.resolved_question_ids` 映射到同一 Snapshot 内嵌题目。
- 返回包含 Block 位置的错误信息。

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
- `ExportAnswerSummary`

应复用现有 RichDoc、公式、表格、图片、题目选项、答案和解析渲染能力。

### 4.4 导出错误模型

错误响应至少包含：

```json
{
  "detail": "Unsupported snapshot block",
  "block_index": 7,
  "block_type": "unknown",
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
- `answer_summary: all`。
- `answer_summary: before`。
- 同一题目重复出现时答案汇总按冻结 ID 去重。
- 题库内容更新后旧版本导出不变。
- 题目软删除后旧版本仍可导出。
- 相同版本重复导出的语义内容一致。
- 100+ Block 长组稿。

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
- 422 Block 定位错误。
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
- 相同题目顺序。
- 相同答案汇总范围。
- 相同分页位置。

可允许样式差异，不允许内容差异。

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

- `section_title` 非空且与前一项不同：插入 `heading` Block。
- 每条关联插入一个 `question` Block。
- `score` 放入 Question Block 中性展示属性；如果当前 Block Schema 尚未支持分值，应先补充 `props.score` 契约。

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
2. 实现五类 Block 到中间结构的转换。
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
| 未知 Block 被忽略 | assembler 显式报错并返回 block index |
| 大组稿导出超时 | 压测后超过阈值转后台任务，不提前引入复杂队列 |
