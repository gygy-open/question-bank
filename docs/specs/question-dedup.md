# 题目查重：录入前识别重复与高度相似题目

## 背景

### 问题定义

题库目前没有任何题目级去重。同一道题可能经由单题新建、智能导入、后台批量导入、MCP 与站内 AI 反复录入，造成题库冗余、组卷时选到重复题、审核与统计失真。

简单的全文精确比对不可行：同一道题在不同来源中常有空格、全半角标点、换行、题号前缀、LaTeX 写法（`\dfrac` / `\frac`、多余空格）等差异，精确比对会漏判。反过来，题库中大量“只改了数字”的变式题是不同的题，语义相似度（向量检索）会把它们误判为重复。

### 现有能力与缺口

- 已有：导入请求的幂等键（防重复提交）、导入源文件 sha256 提示（`DuplicateUploadRead`，文件级，仅提示）、媒体资产按内容 sha256 去重。
- 已有：RichDoc → 纯文本（`rich_doc_to_plain_text`）、题目可见性过滤（`visible_questions_filter`）、数据迁移框架（`data_migrations`）。
- 缺口：不存在题目内容级的重复识别；Embedding 模型是可选配置，不能作为查重前提。

## 目标

1. 新建或修改题目前，识别同学科中已存在的**重复**与**高度相似**题目，并在录入前让用户确认。
2. 对格式性差异（空白、标点、全半角、题号、LaTeX 排版写法、选项顺序）不敏感。
3. 不把“数字或公式不同的变式题”判为重复。
4. 所有写入入口统一生效：网页单题、智能导入、后台批量导入、MCP、站内 AI。
5. 不依赖向量库，SQLite / MySQL 均可用，单次检查开销可控。

### 非目标

- 跨学科查重；语义改写（同义改述）识别；已有存量重复题的批量合并工具。

## 已确认的决策

| 项 | 决定 |
| --- | --- |
| 比对范围 | 同学科、当前用户**可见**、未删除的题目（复用 `visible_questions_filter`，不泄露他人私有题） |
| 判定级别 | **重复**与**高度相似**都需要用户确认后才能录入 |
| 修改题目 | 修改后的内容同样查重（排除自身） |
| 后台批量导入（无人值守） | 照常入库；在导入任务结果中列出疑似重复的题及其命中对象，可在任务详情中一键删除 |

## 判定规则

### 比对内容

- 题干 + 选项（选项按归一化文本**排序**后拼接，选项顺序打乱视为同一题）。
- 材料题的小题：拼接所属材料（stimulus）文本，避免“(1) 求 x 的值”这类短题干误报。
- **不含**答案、思路、解析、总结：同一道题补充解析不应成为新题。
- 题型不同（如单选 vs 解答）视为不同题。

### 归一化（`dedup_normalize`，带版本号）

1. RichDoc → 纯文本，公式取 LaTeX 源码，图片取 `asset:<assetId>`（媒体库按内容去重，同图同 ID）。
2. Unicode NFKC（全角→半角）、统一大小写。
3. 统一标点：中英文逗号、句号、括号、引号、冒号、分号映射到同一字符集。
4. 去除全部空白字符（含换行、不间断空格）。
5. 去除题号前缀：`1.`、`1、`、`(1)`、`（1）`、`①`、`例1`、`第1题` 等。
6. LaTeX 规范化：去空格；去除 `\left` `\right` `\displaystyle` `\,` `\;` `\quad` 等排版命令；`\dfrac` / `\tfrac` → `\frac`；去除冗余单字符花括号（`x^{2}` → `x^2`）。
7. 去除填空占位符差异：多个下划线、`（ ）`、`____` 统一为单一占位符。

归一化规则变更时递增 `DEDUP_VERSION`，触发重算（见“存储与维护”）。

### 两级判定

| 级别 | 判定 | 说明 |
| --- | --- | --- |
| 重复 | 归一化文本的 SHA-256 指纹完全相同，且题型相同 | 走索引等值查询 |
| 高度相似 | MinHash-LSH 召回候选后精确计算相似度 ≥ 0.90 | 覆盖错别字、增删少量字词、标点残差等 |

防误报约束：

- **数值 / 公式签名**：从归一化文本提取数字串与 LaTeX 记号序列；两题签名不同时，即使相似度 ≥ 0.90，也**不判为“重复”**，最高标为“高度相似（可能为变式题）”，并在差异中突出不同的数字。
- **短文本**：归一化后长度 < 8 的题干只做“重复”判定，不做相似匹配。
- 返回候选最多 5 条，按级别、相似度排序。

### 相似度算法

- 特征：归一化文本的字符 3-gram（CJK、字母数字、LaTeX 记号统一按字符切分）。
- MinHash：64 个哈希函数；LSH 分 16 个桶 × 每桶 4 行（召回阈值约 0.5，保证召回）。
- 精确复核：对召回候选（上限 50）计算 3-gram Jaccard 与 `difflib.SequenceMatcher` 比率，取两者较大值作为相似度。
- 纯 Python 实现，无新依赖。

## 存储与维护

- `questions` 新增列：
  - `dedup_fingerprint CHAR(64) NULL`，索引 `(subject_id, dedup_fingerprint)`；
  - `dedup_version SMALLINT NULL`。
- 新表 `question_dedup_bands(question_id FK CASCADE, subject_id, band SMALLINT, hash BIGINT)`，索引 `(subject_id, band, hash)`，主键 `(question_id, band)`。
- 维护时机：`crud_question` 新建 / 修改题目时与媒体引用同步（`_sync_media_refs` 同一位置）重算；材料内容变更时重算其小题；软删除不删索引行，查询时联表过滤 `deleted_at IS NULL`。
- 存量回填：新增一个 `data_migrations` 任务，分批为 `dedup_version IS NULL OR < DEDUP_VERSION` 的题目计算并写入；幂等，启动时自动执行（桌面版与 Docker 一致）。

## 服务与接口

### 查重服务

`question_dedup.find_duplicates(db, *, viewer, subject_id, q_type, content, options, stimulus, exclude_question_id=None) -> List[DuplicateCandidate]`

`DuplicateCandidate`：`question_id`、`level`（`duplicate` / `similar`）、`similarity`、`variant`（数字或公式不同）、题干摘要、`q_type`、`status`、创建人、创建时间、差异片段。

另提供批量版本，供导入时一次处理多题，并检测**同批次内**互相重复的题。

### 服务端强制（capability 层）

- `question.create`、`question.update`、`question.derived.create`、`question.batch_create` 的入参新增 `allow_duplicate: bool = False`（批量为按题设置）。
- 检出候选且未带 `allow_duplicate` 时抛出新的领域错误 `DuplicateSuspected`（HTTP 409，错误码 `question.duplicate_suspected`，`params` 携带候选列表）。
- 整卷导入：
  - `paper-imports/preview` 响应新增 `duplicates: {temp_id: [DuplicateCandidate]}` 与 `intra_batch_duplicates`。
  - 提交请求新增 `allow_duplicate_temp_ids: [str]`；提交时服务端复核，命中但未放行的题按“跳过”处理并在 `skipped` 中说明原因（避免预检与提交之间的竞态）。
- 后台 worker（`commit_extracted_paper_import`）：以 `allow_duplicate=all` 写入，同时把命中结果写入 `result_summary.duplicates`（新题 ID → 候选），不阻塞导入。

### 新增接口

- `POST /api/v1/questions/duplicate-check`：入参为题目草稿（与新建一致，可带 `exclude_question_id`），返回候选列表；用于编辑器实时提示，只读、不写库。
- 导入任务详情：展示 `result_summary.duplicates`，支持对选中的新题执行批量删除（复用 `question.batch_delete`）。

## 各入口交互

### 网页：新建 / 修改题目

- 编辑时（题干或选项停止输入约 800ms）调用 `duplicate-check`，在题干下方显示非阻塞提示：“发现 1 道重复题 / 2 道相似题”，可展开。
- 点击保存若收到 409：弹出对比对话框，左右并排展示已有题与当前题、高亮差异，按钮为“查看已有题”“仍然保存”“取消”。“仍然保存”带 `allow_duplicate=true` 重试。

### 智能导入审阅页

- preview 返回后，在每道题旁显示徽标“重复 #123”或“相似 92%”（变式题另加标记），点击展开对比。
- 命中“重复”的题**默认取消勾选**，“相似”的题保持勾选但显示提示；用户勾选即视为确认，提交时放入 `allow_duplicate_temp_ids`。
- 同批次互相重复的题同样标出。
- 汇总条：“本次共 N 题，其中 x 题与题库重复、y 题高度相似”。

### 后台批量导入

- 导入照常完成；任务列表显示“疑似重复 k 题”，详情页列出每道新题与命中的已有题，可勾选后批量删除新题。

### MCP 与站内 AI

- `question_create` 等工具返回 `isError`，内容含 `question.duplicate_suspected` 与候选列表。
- 工具描述与服务说明要求 AI **先把候选告知用户并征得同意**，再以 `allow_duplicate: true` 重试；不得自行放行。
- 站内 AI 的 `propose_question_draft` / `propose_questions_batch` 生成的是待确认草稿：命中时仍创建草稿，但在回复与提案卡片中标注疑似重复，由用户在确认环节决定。

## 权限与隐私

- 只与当前用户可见的题比对，候选只返回可见题的信息。
- `duplicate-check` 需要该学科 `VIEW_QUESTION`；写入入口沿用各自权限。

## 性能

- 重复判定：一次索引等值查询。
- 相似判定：16 次索引查询（可合并为一条 `IN`）召回候选，候选上限 50，复核为内存计算；单题检查目标 < 50ms（万级题量、SQLite）。
- 批量导入：批量计算签名，一次查询召回全批候选。

## 测试要点

- 归一化：空白 / 全半角 / 标点 / 题号 / LaTeX 写法 / 选项乱序 / 填空占位符差异 → 指纹相同。
- 变式题：仅数字不同 → 不判“重复”，最多“相似（变式）”。
- 短题干不触发相似匹配；题型不同不判重。
- 可见性：他人私有题不参与比对；软删除题不参与。
- 修改题目排除自身；材料题拼接材料文本。
- 各入口：网页 409 与放行重试、导入 preview 标记与提交复核、worker 记录结果、MCP 返回错误与放行重试。
- 回填迁移幂等、版本升级触发重算。

## 实施拆分

1. 归一化与签名模块 + 单元测试（无外部依赖）。
2. 存储：迁移、维护钩子、存量回填数据迁移。
3. 查重服务（单题 / 批量 / 批内）+ `duplicate-check` 接口。
4. capability 层强制与 `allow_duplicate`；整卷导入 preview / 提交 / worker 结果。
5. 前端：编辑器实时提示与对比对话框、导入审阅页标记、导入任务详情。
6. MCP 与站内 AI 工具描述、错误呈现；文档与 i18n。

## 实现说明（已落地）

状态：已实现。代码入口：`app/services/question_dedup_core.py`（归一化与签名）、`app/services/question_dedup.py`（flush 钩子、查询、回填）。

与上文设计的差异与补充：

- **签名维护方式**：通过 SQLAlchemy `before_flush` / `after_flush` 钩子统一维护，所有写入路径（含 worker、MCP）自动覆盖，不需要在各 CRUD 中调用。
- **材料题相似度**：带材料的题目分别计算「材料」与「题目本体」的相似度并取较小值；是否做模糊匹配按题目本体长度判断。否则同一材料下的不同小题会因共享长材料被误判为相似。
- **句末标点**：归一化时去除句末标点（`。` `?` 等）。
- **候选预览**：展示题干原文，差异片段基于归一化文本。
- **MCP**：额外提供只读工具 `check_question_duplicates`；服务说明要求 AI 征得用户同意后才以 `allow_duplicate` 重试。
- **批量创建（`question.batch_create`）**：任一题命中且未放行时整批返回 409，`params.items` 列出全部命中项。
- **存量回填**：数据迁移任务名为 `question_dedup_v{DEDUP_VERSION}`，规则版本递增后会自动重跑。
