# 组稿系统 AST 与模块全流程验收

## 1. 文档目的

本文用于验收从“选择学科、组织组稿、编辑节点与模块、插入题目、定稿、查看历史版本”到后续“导出与旧试卷迁移”的完整业务流程。

本文中的“文档”特指由 `CompositionNode` 组成的 AST。根层允许基础节点和模块并列；首期模块子树只有一层，子节点统一位于 `body` slot，不允许模块嵌套。

验收分为两个范围：

- **范围 A：当前已实现**，必须能够立即执行并通过。
- **范围 B：下一阶段待实现**，用于后续导出与迁移上线前验收。

验收人员不得把范围 B 的未实现项记录为当前版本回归缺陷。

## 2. 当前能力状态

| 能力 | 状态 |
|---|---|
| 当前学科上下文 | 已实现 |
| 共享组稿与个人组稿 | 已实现 |
| 任意层级文件夹 | 已实现 |
| 组稿元数据 | 已实现 |
| 基础节点与模块并列的文档画布 | 已实现 |
| 富文本、标题、题目、分页基础节点 | 已实现 |
| 参考答案 / 答案与解析模块 | 已实现 |
| 乐观锁冲突保护 | 已实现 |
| 题目内容冻结快照（Question Node） | 已实现 |
| 题目版本状态检测（stale/deleted，不拉取内容） | 已实现 |
| 题目手动同步（同步此题 / 同步全部） | 已实现 |
| 定稿与不可变 Snapshot | 已实现 |
| 版本列表与只读预览 | 已实现 |
| DOCX/LaTeX 导出 | 下一阶段 |
| Paper 数据迁移与旧入口下线 | 下一阶段 |

## 3. 验收环境

### 3.1 服务

后端：

```bash
cd backend
uv run alembic upgrade head
uv run fastapi dev app/main.py
```

前端：

```bash
cd frontend
pnpm install
pnpm dev
```

默认访问地址：

```text
http://localhost:3000
```

### 3.2 自动化基线

执行：

```bash
cd backend
uv run pytest -q

cd ../frontend
pnpm test
pnpm generate
```

当前基线：

- 后端：`249 passed, 1 skipped`。跳过项为未配置 `MYSQL_TEST_URL` 的真实 MySQL 测试。
- 前端：`116 passed`。
- Nuxt 静态生成成功。

正式发布前必须补跑真实 MySQL 迁移测试。

### 3.3 测试数据

至少准备：

- 用户 A：普通教师。
- 用户 B：另一名普通教师。
- 学科 S1：数学。
- 学科 S2：物理。
- 数学题目 Q1：选择题，包含答案和解析。
- 数学题目 Q2：主观题，包含答案和解析。
- 物理题目 Q3。

用户 A 与用户 B 均能登录。

## 4. P0 核心验收

P0 任一失败即阻止发布。

### AC-001 学科上下文隔离

**步骤**

1. 当前学科切换到数学。
2. 打开“组稿工作台”。
3. 在共享作用域创建文件夹“数学资料”。
4. 创建组稿“数学期中复习”。
5. 切换当前学科到物理。
6. 保持共享作用域。

**预期**

- 物理下看不到“数学资料”和“数学期中复习”。
- 切回数学后数据恢复可见。
- 直接使用数学 Composition ID 请求物理路径时，后端返回 404。

### AC-002 共享与个人作用域

**步骤**

1. 用户 A 在数学共享作用域创建“共享稿”。
2. 用户 A 在数学个人作用域创建“个人稿 A”。
3. 用户 B 登录并进入数学共享作用域。
4. 用户 B 进入数学个人作用域。
5. 用户 B 尝试直接访问“个人稿 A”的 URL/API。

**预期**

- 用户 B 能看到并编辑“共享稿”。
- 用户 B 看不到“个人稿 A”。
- 直接访问用户 A 的个人稿返回 404。
- 前端请求中不发送 `owner_id`。

### AC-003 文件夹树

**步骤**

1. 创建根文件夹 A。
2. 在 A 下创建 A-1。
3. 在 A-1 下创建 A-1-1。
4. 重命名 A-1。
5. 将 A-1-1 移动到 A 下。
6. 尝试把 A 移动到 A-1-1 下。
7. 尝试删除仍包含内容的 A。

**预期**

- 树层级、面包屑和移动结果正确。
- 环形移动被拒绝。
- 非空文件夹删除返回冲突，UI 明确提示先移动或删除内容。
- 根目录列表只显示 `folder_id IS NULL` 的组稿，不混入子文件夹组稿。

### AC-004 创建和编辑组稿

**步骤**

1. 在数学共享作用域根目录创建组稿。
2. 填写标题和描述并保存。
3. 移入某个数学共享文件夹。
4. 归档后恢复。
5. 移入回收站并恢复。

**预期**

- 每次成功修改后 revision 递增。
- 列表与详情显示一致。
- 回收站外默认不显示软删除数据。
- 恢复后重新出现在原目录。
- 不允许移动到其他 Subject 或其他 Scope 的文件夹。

### AC-005 文档节点与模块编辑

**步骤**

在空画布依次添加：

1. H1 标题。
2. 富文本，包含段落、列表、公式或表格中的至少两种。
3. 数学题目 Q1。
4. 分页。
5. 数学题目 Q2。
6. “参考答案”模块，范围选择“此前题目”。
7. “答案与解析”模块，范围选择“全篇题目”。

然后执行：

- 上移和下移根节点。
- 删除一个普通节点。
- 修改模块预设标题，并在某道题前及模块尾部插入富文本，其中至少一处包含图片。
- 修改模块全局字段开关，并对一题设置字段覆盖和排除。
- 保存内容。
- 刷新页面。

**预期**

- 页面刷新后根节点、模块子节点、内容和配置保持一致。
- 节点 UUID 在保存前后保持稳定；同一 `parent_id + slot` 下的 position 连续为 `0..n-1`。
- “参考答案”和“答案与解析”是同一 `question_details` 模块的不同初始预设，插入后均可自由编辑。
- 画布直接显示模块的真实答案内容，不出现“定稿时生成”的占位提示。
- 模块内答案项始终跟随正文题序，自定义标题/富文本通过锚点保持在指定题目前或模块尾部。
- 一次整批保存只增加一次 Composition revision。
- 一次保存只产生一条 `nodes_replaced` 时间线事件。

### AC-006 节点与模块校验

**步骤与预期**

| 操作 | 预期 |
|---|---|
| 保存空 RichText | 前端阻止，后端也应拒绝非法载荷 |
| 保存空 Heading | 前端阻止 |
| Heading level 设置为 5 | 后端返回 422 |
| PageBreak 携带 content | 后端返回 422 |
| `question_details.scope` 为其他值 | 后端返回 422 |
| 模块字段缺少 `answer/thinking/analysis/summary` 任一键，或包含额外键 | 后端返回 422 |
| 模块任一字段开关不是布尔值 | 后端返回 422 |
| `answer_item.overrides` 缺少四字段任一键，或值不是布尔值/`null` | 后端返回 422 |
| `answer_item` 引用非 Question 节点或其他模块 | 后端拒绝，事务不产生部分变更 |
| 模块嵌套模块 | 后端返回 422 |
| Question 节点不带 question_id | 后端返回 422 |
| 插入物理题目到数学组稿 | 后端拒绝，事务不产生部分变更 |

### AC-007 乐观锁冲突

**步骤**

1. 用户 A 和用户 B 同时打开同一共享组稿。
2. 用户 A 修改并保存内容。
3. 用户 B 基于旧 revision 保存。

**预期**

- 用户 B 收到 409 冲突。
- 用户 B 的本地内容仍保留，不被静默刷新覆盖。
- 页面显示明确冲突提示。
- 用户选择“重新加载”后才放弃本地修改。
- 数据库中不存在用户 B 的部分节点更新。

### AC-008 题目内容冻结与版本检测

**步骤**

1. 将数学题目 Q1 插入组稿并保存。
2. 记录 Question Node 的 `question_revision` 与画布上显示的题干内容。
3. 修改 Q1 的题干或答案。
4. 重新打开组稿。
5. 在 Question Node 上点击“同步此题”（或画布顶部“同步全部”）。

**预期**

- 插入并保存后，Question Node 冻结当前题目内容快照；画布始终渲染该快照，不再向 `/questions` 拉取实时题目内容。
- 修改题干或答案后 `Question.content_revision + 1`；仅修改标签、状态、来源或难度不增加 `content_revision`。
- 重新打开后，状态接口 `GET .../question-revisions` 标记该题“题库有更新”，但画布仍显示旧的冻结内容。
- 普通“保存内容”不会隐式刷新已有题目的快照（节点 UUID 未变时保留数据库中的快照与 `question_revision`）。
- 点击“同步此题/同步全部”后，Question Node 内容与 `question_revision` 更新为题库最新值，组稿 revision +1，并写入一条 `question_nodes_synced` 时间线事件。
- 有未保存修改时同步按钮不可用（避免覆盖本地内容）。
- 题目被软删除后，状态接口标记该题“题库已删除”，但已冻结的 Question Node 内容仍可正常显示。

### AC-009 定稿

**步骤**

1. 保证组稿所有修改已保存。
2. 点击“定稿”。
3. 输入备注“第一次定稿”。
4. 再次对同一 revision 定稿，备注“打印版”。

**预期**

- 有未保存修改时定稿按钮不可用。
- 存在“题库有更新”的题目时仍可定稿；对话框提示本次将冻结当前显示的旧版本内容，但不阻止定稿。
- 定稿完全不查询实时题库，直接从 Question Node 的冻结内容合成 schema v2 Snapshot。
- 若某 Question Node 的冻结内容缺失或损坏，定稿返回 422 并指明 node id。
- 第一次生成 v1，第二次生成 v2。
- 两个版本允许拥有相同 `source_revision`。
- 定稿不增加 Composition revision。
- 每次定稿生成一条 `finalized` 时间线事件。

### AC-010 快照冻结

**步骤**

1. 打开 v1 版本预览，记录 Q1 题干、答案和解析。
2. 回到题库修改 Q1 的题干、答案和解析。
3. 再次打开 v1。
4. 对草稿“同步全部”并重新保存，再定稿为 v3。

**预期**

- v1 内容完全不变。
- v3 包含修改后的题目内容（因先同步再定稿）。
- 版本预览不向实时题目详情接口发起查询。
- 题目被软删除后，v1 仍可完整预览；软删除的实时题目也不阻止定稿（定稿只读 Node 快照）。

### AC-011 题目详情模块冻结

使用以下顺序：

```text
Q1
参考答案模块（before）
Q2
Q1（再次插入）
答案与解析模块（all）
```

**预期**

- `before` 只展示第一个 Q1 节点。
- `all` 按正文顺序展示 Q1、Q2、Q1；重复题按不同 Question 节点 UUID 分别保留，不按 `question_id` 去重。
- 保存时服务端已按 scope 规范化模块的 `answer_item` 集合与顺序；定稿和预览消费这些持久化引用，不重新计算范围。
- 全局字段开关与单题覆盖、排除在定稿预览中保持一致。
- 模块标题、题间/尾部富文本和图片按编辑顺序冻结。
- 答案、思路、解析和总结来自 Snapshot 内嵌的源 Question 节点，不查询实时题库。
- 空题目范围仍显示用户编辑的模块内容，不报错。

### AC-012 版本权限与不可变性

**步骤**

1. 用户 A 创建个人组稿并定稿。
2. 用户 B 尝试访问其版本列表和版本详情。
3. 对 Composition 软删除。
4. 再次访问已存在版本。
5. 检查 API 是否存在版本修改或删除端点。

**预期**

- 用户 B 收到 404。
- 软删除后仍可查看历史版本。
- 软删除后不能创建新定稿。
- 不存在版本 PATCH、PUT 或 DELETE 接口。

## 5. P1 体验验收

P1 缺陷通常不阻止数据模型上线，但必须在正式替换旧 Paper 前修复。

### AC-101 响应式布局

在至少以下视口验收：

- 1440 × 900
- 1024 × 768
- 390 × 844

预期：

- 工具栏按钮不重叠。
- 长标题不会覆盖作用域和定稿按钮。
- 文件夹树和组稿列表可操作。
- 版本侧栏在移动端可关闭和滚动。
- Node 内容不溢出画布。

### AC-102 加载与错误态

模拟：

- 网络延迟。
- 401。
- 404。
- 409。
- 422。
- 500。

预期：

- 显示加载状态，防止重复提交。
- 401 走统一登录失效处理。
- 404 返回列表并提示不存在或无权访问。
- 409 保留本地内容。
- 422 显示可理解的校验错误。
- 500 不清空当前画布。

### AC-103 未保存保护

**步骤**

1. 修改标题但不保存，切换页面。
2. 修改 Node 或 Module 但不保存，关闭或刷新页面。
3. 取消离开。

**预期**

- 路由离开和浏览器关闭均有提示。
- 取消离开后本地内容仍存在。
- 保存完成后离开不再提示。

### AC-104 大组稿

准备至少 100 个 Node，其中至少 30 个 Question Node 和 2 个 `question_details` Module。

预期：

- 首次加载可完成。
- 画布和模块使用 Question 节点冻结快照，完全不向 `/questions` 发起逐节点或批量的实时内容查询。
- 题目版本状态用一次批量 `GET .../question-revisions` 获取（不返回题目内容），不产生逐节点 N+1 请求。
- “同步全部”只发一次 `POST .../question-nodes/sync` 批量请求。
- 上下移动和编辑无明显布局抖动。
- 保存请求只有一次 `PUT .../nodes` 完整 AST Replace。

## 6. P0 下一阶段导出验收

以下用例在完成导出实施后启用。

### AC-201 DOCX 导出

从某个定稿版本导出 DOCX。

预期：

- 基础节点、模块及模块子节点顺序正确。
- 题目详情模块正确输出全局字段、单题覆盖、排除和自定义图文。
- 公式、表格和图片可见。
- 下载文件可被 Microsoft Word 或 LibreOffice 打开。
- 文件名包含组稿标题和版本号。

### AC-202 LaTeX 导出

从同一版本导出 LaTeX ZIP。

预期：

- ZIP 包含主 `.tex` 和所需资源。
- 内容顺序与 DOCX、网页预览一致。
- 特殊字符正确转义。
- 数学公式保持 LaTeX 语义。

### AC-203 导出历史稳定性

**步骤**

1. 导出 v1。
2. 修改或删除题库中的 Q1。
3. 再次导出 v1。

**预期**

- 两次导出的业务内容一致。
- 导出过程中没有读取实时 Question 内容。

### AC-204 损坏快照

构造未知 Node Type、非法 Module Type、悬空 reference 或缺失题目快照的测试数据。

预期：

- 后端返回 422。
- 错误包含版本号、Node UUID/位置和 Node Type。
- 不生成看似成功但缺内容的文件。

## 7. P0 下一阶段迁移验收

### AC-301 Paper 审计

运行 audit 模式。

预期报告包含：

- Paper 总数。
- 空 Paper 数量。
- PaperQuestion 总数。
- 孤儿 Question 引用。
- 重复或异常 sequence。
- 缺失 subject/owner。
- 无法迁移的题目内容。

Audit 不得写入业务数据。

### AC-302 Paper 迁移

选择包含以下情况的样本：

- 空试卷。
- 无大题标题。
- 多个大题标题。
- 同题重复。
- 带分值。
- 已归档。

预期：

- 每个 Paper 只生成一个 Personal Composition。
- Owner、Subject、标题、描述、状态正确。
- Heading Node 和 Question Node 顺序正确。
- 重复执行迁移不会重复创建数据。

### AC-303 迁移验证

Verify 报告逐卷比较：

- 标题。
- Owner。
- Subject。
- 题目数量。
- 题目顺序。
- 大题标题。
- 分值。

所有差异必须可定位到 Paper ID 和 Composition ID。

### AC-304 回滚演练

在数据库副本完成：

1. 迁移。
2. 前端切换。
3. 模拟失败。
4. 恢复数据库或启用旧 Paper 只读入口。

预期：

- 旧 Paper 数据未在迁移步骤中删除。
- 用户可以回到迁移前状态。
- Composition 新数据不会污染第二次迁移。

## 8. API 安全检查

至少验证：

- 未登录访问全部 Composition API 返回 401。
- Personal 资源不能通过猜测 ID 访问。
- Subject 路径参数与资源 Subject 不一致时返回 404。
- Scope 参数与资源 Scope 不一致时返回 404。
- Shared 资源对所有已登录用户可编辑。
- 客户端提交 `owner_id` 不影响实际 Owner。
- 已软删除 Folder 不可作为新父目录。
- 已软删除 Composition 不可修改文档节点或创建定稿。

## 9. 数据库检查

验收完成后抽查：

```sql
SELECT id, subject_id, scope_type, owner_id, revision, deleted_at
FROM compositions;

SELECT id, composition_id, parent_id, slot, position, node_kind, node_type,
       question_id, question_revision, source_question_node_id,
       anchor_before_node_id, (content IS NOT NULL) AS has_content
FROM composition_nodes
ORDER BY composition_id, parent_id, slot, position;

SELECT composition_id, version_no, source_revision, label, finalized_at
FROM composition_versions
ORDER BY composition_id, version_no;

SELECT composition_id, composition_revision, event_type, summary, created_at
FROM composition_events
ORDER BY composition_id, id;
```

检查项：

- Shared 行 `owner_id IS NULL`。
- Personal 行 `owner_id IS NOT NULL`。
- 节点 ID 为合法 UUID；同一 `parent_id + slot` 下 position 连续。
- 根节点 `parent_id/slot IS NULL`；模块子节点 `slot = 'body'`。
- Question 节点有完整引用（`question_id`、`question_revision` 非空）且 `content IS NOT NULL`（冻结快照）。
- 非 Question 节点没有 `question_id`；`answer_item.source_question_node_id` 指向同稿根层 Question 节点。
- `question_details` 位于根层，首期不存在 Module 嵌套；其子节点只包含 heading、rich_text 和 answer_item。
- 每个题目详情模块的 answer_item 按源 Question 节点 UUID 与范围一一对应，重复 `question_id` 不合并。
- 版本号在每个 Composition 内连续递增。
- 定稿事件 revision 等于其 source revision。
- 替换事件 `nodes_replaced` 的 revision 等于替换后的组稿 revision。
- 同步事件 `question_nodes_synced` 的 revision 等于同步后的组稿 revision。

## 10. 验收记录模板

| 用例 | 结果 | 执行人 | 日期 | 证据/缺陷链接 |
|---|---|---|---|---|
| AC-001 | 通过 / 失败 / 阻塞 |  |  |  |
| AC-002 | 通过 / 失败 / 阻塞 |  |  |  |
| AC-003 | 通过 / 失败 / 阻塞 |  |  |  |
| AC-004 | 通过 / 失败 / 阻塞 |  |  |  |
| AC-005 | 通过 / 失败 / 阻塞 |  |  |  |
| AC-006 | 通过 / 失败 / 阻塞 |  |  |  |
| AC-007 | 通过 / 失败 / 阻塞 |  |  |  |
| AC-008 | 通过 / 失败 / 阻塞 |  |  |  |
| AC-009 | 通过 / 失败 / 阻塞 |  |  |  |
| AC-010 | 通过 / 失败 / 阻塞 |  |  |  |
| AC-011 | 通过 / 失败 / 阻塞 |  |  |  |
| AC-012 | 通过 / 失败 / 阻塞 |  |  |  |

## 11. 发布判定

### 当前阶段

满足以下条件可判定当前阶段通过：

- AC-001 至 AC-012 全部通过。
- 后端、前端自动化测试通过。
- SQLite 开发迁移成功。
- 真实 MySQL 迁移测试通过。
- 无 P0 数据丢失、越权或快照漂移问题。

### 替换旧 Paper 前

还必须满足：

- AC-201 至 AC-204 全部通过。
- AC-301 至 AC-304 全部通过。
- 旧入口切换和回滚演练完成。
- 至少一名真实教师完成一份包含讲解、题目、分页和题目详情模块的端到端试用。
