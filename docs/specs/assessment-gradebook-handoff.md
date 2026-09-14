# 学生成绩录入功能交接文档

> 状态：功能分支开发中，尚未提交或合并  
> 分支：`feat/assessment-gradebook`  
> 更新日期：2026-09-14

## 1. 文档目的

本文用于交接建立在“组稿定稿”之上的学生成绩录入功能，说明需求边界、设计思想、领域模型、后端和前端架构、已完成功能、未完成功能以及验收方法。

当前版本已经形成可手工使用的教师端 MVP：教师可维护学生与班级，从共享组稿定稿版本创建考试，逐题录入成绩，使用 Excel 批量导入导出，并在成绩完整后锁定考试。

## 2. 需求范围

### 2.1 当前目标

- 管理学科内的学生档案和班级名册。
- 从不可变的组稿定稿版本创建一次考试。
- 冻结考试题目、题型、分值和参与者名单。
- 支持教师按学生、按题录入成绩。
- 支持 Excel 成绩表导出、预检和原子导入。
- 支持多人录分时的并发冲突检测和操作审计。
- 保留未来接入在线考试、自动判分和题目分析的扩展空间。

### 2.2 当前非目标

- 学生在线答题、监考、计时和交卷。
- 自动判分和答案事实表。
- 排名、成绩发布和学生端成绩查询。
- 跨考试、跨班级的长期趋势分析。
- 完整教务模型，例如学年、学期、年级和教学班排课。

## 3. 核心设计思想

### 3.1 组稿版本是考试模板，考试场次是一次事实

`CompositionVersion` 是不可变的试卷模板；`ExamSession` 表示某个班级参加的一次具体考试。两者分离后，同一份定稿试卷可以创建多场考试，而每场考试有独立的名单、成绩、状态和审计记录。

只允许从 `shared` 且已启用赋分的组稿定稿版本创建考试。`personal` 版本、无题版本、缺少题目分值或快照损坏的版本都会被拒绝。

### 3.2 创建考试时冻结业务快照

创建 `ExamSession` 时，在一个事务内完成：

1. 从 `CompositionVersion.snapshot` 提取题目。
2. 冻结为 `ExamQuestion`，保存节点 ID、题型、满分和顺序。
3. 复制班级当前成员为 `ExamParticipant`，冻结姓名和学号。
4. 为每位参与者创建独立的 `ExamResult`。
5. 写入 `ExamEvent(created)`。

此后修改组稿、学生姓名或班级成员，不会改变已经创建的考试事实。

### 3.3 逐题成绩是事实，总分是派生结果

`ExamScoreItem` 保存“某学生在某道考试题上的得分”。`ExamResult.total_score` 是逐题得分完整时的缓存汇总；只要有一题未录入，总分保持 `NULL`，不能用 `0` 表示“未录入”。

所有分值使用 `Numeric(6, 2)` / Python `Decimal`，不使用浮点数。单题得分必须满足：

$$
0 \le score \le max\_score
$$

并且最多保留两位小数。

### 3.4 并发控制按学生成绩行隔离

每个 `ExamResult` 有独立 `revision`。单行保存要求客户端提交 `expected_revision`，数据库执行条件更新：

```text
UPDATE exam_results
SET revision = revision + 1
WHERE id = :result_id AND revision = :expected_revision
```

命中 0 行时返回 `409 Conflict`，前端刷新 gradebook。不同学生的成绩行互不阻塞，避免用整个考试的全局版本锁放大冲突。

### 3.5 幂等键必须绑定完整请求身份

单行保存的 `batch_id` 只允许重放相同的目标成绩行、`expected_revision` 和成绩项。Excel 导入的 `batch_id` 与文件 SHA-256 摘要绑定。复用同一 `batch_id` 发送不同请求会返回 `409`。

这保证网络重试不会重复增加 revision 或重复写审计事件，也不会让幂等键跨资源误用。

### 3.6 Excel 导入必须先预检，再原子应用

导出的工作簿包含：

- 可见工作表 `成绩录入`：学号、姓名、逐题分数和总分公式。
- 隐藏工作表 `_meta`：格式版本、考试 ID、题目 ID、result ID 和各行 revision。

隐藏元数据用于验证文件属于当前考试、题目结构未损坏且成绩未被他人更新。预检不写数据库；应用时先校验所有行，再在一个事务中更新全部成绩。任一行非法时整批拒绝。

### 3.7 权限与业务能力分层

权限只表达“能不能做”，capability 表达“执行哪个业务用例”。API 端点保持为薄适配器，领域规则和事务集中在 service。

| 权限 | Editor | Manager | Admin | 用途 |
|------|:------:|:-------:|:-----:|------|
| `VIEW_ASSESSMENT` | 是 | 是 | 是 | 查看考试、gradebook、名册，导出 Excel |
| `EDIT_SCORE` | 是 | 是 | 是 | 逐题录分、Excel 预检与应用 |
| `MANAGE_ASSESSMENT` | 否 | 是 | 是 | 创建学生、班级、考试及推进状态 |

Viewer 当前不具备 assessment 权限。所有资源均受 `subject_id` 强上下文约束，跨学科访问返回 `404`，避免资源枚举。

## 4. 领域模型

```mermaid
erDiagram
    SUBJECT ||--o{ STUDENT : contains
    SUBJECT ||--o{ CLASSROOM : contains
    CLASSROOM ||--o{ CLASSROOM_STUDENT : has
    STUDENT ||--o{ CLASSROOM_STUDENT : joins
    COMPOSITION_VERSION ||--o{ EXAM_SESSION : templates
    CLASSROOM ||--o{ EXAM_SESSION : takes
    EXAM_SESSION ||--|{ EXAM_QUESTION : freezes
    EXAM_SESSION ||--o{ EXAM_PARTICIPANT : freezes
    EXAM_SESSION ||--o{ EXAM_RESULT : owns
    EXAM_PARTICIPANT ||--|| EXAM_RESULT : receives
    EXAM_RESULT ||--o{ EXAM_SCORE_ITEM : contains
    EXAM_QUESTION ||--o{ EXAM_SCORE_ITEM : scores
    EXAM_SESSION ||--o{ EXAM_EVENT : audits
```

| 表 | 职责 | 关键约束 |
|----|------|----------|
| `students` | 学科内学生档案，可选绑定系统用户 | `(subject_id, student_no)` 唯一 |
| `classrooms` | 学科内班级或学生群组 | `(subject_id, name)` 唯一 |
| `classroom_students` | 当前班级成员关系 | `(classroom_id, student_id)` 唯一 |
| `exam_sessions` | 一次考试及其生命周期 | 绑定 `CompositionVersion` 和 `Classroom` |
| `exam_questions` | 创建考试时冻结的题目投影 | `(exam_session_id, composition_node_id)` 唯一 |
| `exam_participants` | 创建考试时冻结的姓名和学号 | 每个学生每场考试最多一行 |
| `exam_results` | 每位参与者的成绩单和独立 revision | `participant_id` 唯一 |
| `exam_score_items` | 逐题得分事实 | `(exam_result_id, exam_question_id)` 唯一 |
| `exam_events` | 追加式考试审计日志 | `(exam_session_id, batch_id)` 唯一 |

迁移文件：`backend/alembic/versions/e5f6a7b8c9d0_add_assessment_gradebook_tables.py`。

## 5. 生命周期

```mermaid
stateDiagram-v2
    [*] --> draft: 创建考试
    draft --> recording: 开始录入
    recording --> locked: 成绩完整后锁定
    locked --> archived: 待实现
    locked --> recording: 待实现，必须填写解锁原因
```

当前已实现：

- `draft -> recording`：至少有一名参与者和一道题。
- `recording -> locked`：所有非缺考参与者都必须录满每一道题。
- 非 `recording` 状态拒绝修改成绩和应用 Excel 导入。

模型已经预留 `archived` 和 `absent`，但对应修改 API 尚未实现。

## 6. 代码架构

### 6.1 后端

| 层 | 文件 | 职责 |
|----|------|------|
| ORM | `backend/app/models/assessment.py` | 表、关系、枚举、唯一约束和检查约束 |
| CRUD | `backend/app/crud/crud_assessment.py` | 学科限定查询和关系预加载 |
| Schema | `backend/app/schemas/assessment.py` | HTTP 请求及响应契约 |
| Domain service | `backend/app/services/assessment_service.py` | 状态机、不变量、事务、并发、幂等和审计 |
| Excel transport | `backend/app/services/assessment_excel.py` | 工作簿生成、解析和模板完整性验证 |
| Capability | `backend/app/capabilities/assessments.py` | 用例注册、权限声明和执行入口 |
| API | `backend/app/api/v1/endpoints/assessments.py` | 路由、multipart、文件限制和响应适配 |
| Router | `backend/app/api/v1/api.py` | 以 `/api/v1/subjects` 前缀注册 assessment 路由 |

关键原则：

- API 不直接写 ORM。
- CRUD 不承载领域事务。
- Service 抛出 transport-independent 的 `DomainError`。
- 所有写操作使用 `AsyncSession` 并明确 `commit/rollback`。
- Excel 解析与数据库更新分离，便于纯解析测试和未来替换文件格式。

### 6.2 前端

| 文件 | 职责 |
|------|------|
| `frontend/app/types/assessment.ts` | Assessment TypeScript 契约 |
| `frontend/app/lib/assessments.ts` | 纯 URL 构造函数 |
| `frontend/app/composables/useAssessments.ts` | API 调用、multipart/blob 处理、409 分类 |
| `frontend/app/pages/rosters/index.vue` | 学生和班级名册管理 |
| `frontend/app/pages/exams/index.vue` | 考试列表和创建 |
| `frontend/app/pages/exams/[id].vue` | 逐题录分、状态管理和 Excel 工作流 |
| `frontend/app/components/AppSidebar.vue` | 按权限显示考试与名册导航 |

成绩页的行草稿同时保存 `result_id`、`revision`、原值和当前值，只提交发生变化的题目。注意 `participant_id` 和 `result_id` 是不同资源 ID，成绩写入必须使用 `result_id`。

## 7. API 契约

所有路径均以 `/api/v1/subjects/{subject_id}` 开头。

| 方法 | 相对路径 | 权限 | 状态 |
|------|----------|------|------|
| `POST` | `/students` | `MANAGE_ASSESSMENT` | 已实现 |
| `GET` | `/students` | `VIEW_ASSESSMENT` | 已实现，支持搜索和分页 |
| `POST` | `/classrooms` | `MANAGE_ASSESSMENT` | 已实现 |
| `GET` | `/classrooms` | `VIEW_ASSESSMENT` | 已实现 |
| `GET` | `/classrooms/{id}/students` | `VIEW_ASSESSMENT` | 已实现 |
| `PUT` | `/classrooms/{id}/students` | `MANAGE_ASSESSMENT` | 已实现，整体替换 |
| `GET` | `/exam-sessions` | `VIEW_ASSESSMENT` | 已实现，支持状态/班级过滤 |
| `POST` | `/exam-sessions` | `MANAGE_ASSESSMENT` | 已实现 |
| `GET` | `/exam-sessions/{id}` | `VIEW_ASSESSMENT` | 已实现 |
| `POST` | `/exam-sessions/{id}/start-recording` | `MANAGE_ASSESSMENT` | 已实现 |
| `POST` | `/exam-sessions/{id}/lock` | `MANAGE_ASSESSMENT` | 已实现 |
| `GET` | `/exam-sessions/{id}/gradebook` | `VIEW_ASSESSMENT` | 已实现 |
| `PATCH` | `/exam-sessions/{id}/results/{result_id}` | `EDIT_SCORE` | 已实现 |
| `GET` | `/exam-sessions/{id}/gradebook.xlsx` | `VIEW_ASSESSMENT` | 已实现 |
| `POST` | `/exam-sessions/{id}/score-imports/preview` | `EDIT_SCORE` | 已实现 |
| `POST` | `/exam-sessions/{id}/score-imports/apply` | `EDIT_SCORE` | 已实现 |

### 7.1 错误语义

| HTTP 状态 | 含义 |
|-----------|------|
| `400` | 文件格式/大小、分值格式、状态前置等请求无效 |
| `403` | 当前用户缺少 capability 所需权限 |
| `404` | 资源不存在，或资源不属于路径中的学科 |
| `409` | revision 冲突、状态冲突、重复资源或 `batch_id` 误复用 |
| `422` | 跨资源语义错误、损坏/过期 Excel 模板、整批导入校验失败 |

## 8. 已完成内容

### 8.1 后端

- 9 张 Assessment 表及 Alembic 迁移。
- `VIEW_ASSESSMENT`、`EDIT_SCORE`、`MANAGE_ASSESSMENT` 权限。
- 学生创建、搜索和分页。
- 班级创建、成员读取与原子整体替换。
- 从共享组稿定稿版本创建考试并冻结题目与名单。
- 考试列表、详情、开始录入和锁定。
- Gradebook 矩阵读取及逐题成绩保存。
- 每位学生独立 revision 乐观锁。
- 严格 `batch_id` 幂等和 `ExamEvent` 审计。
- Excel 导出、只读预检和全批原子应用。
- Excel 错考试、结构损坏、过期 revision、非法分值和权限保护。

### 8.2 前端

- 侧栏按权限显示“考试”和“学生名册”。
- 学生、班级创建及成员管理页面。
- 未保存班级成员变更的切换保护。
- 考试列表、创建和考试详情页面。
- 从共享组稿版本页面进入创建考试流程。
- 逐题录分、差异提交、保存状态和冲突刷新。
- Excel 导出。
- Excel 文件选择、自动预检、错误列表、确认应用及导入后刷新。
- `EDIT_SCORE` 与 `MANAGE_ASSESSMENT` 的 UI 权限分离。

### 8.3 已有测试

- `backend/tests/test_api_assessment_exam_sessions.py`
- `backend/tests/test_api_assessment_gradebook.py`
- `frontend/app/lib/__tests__/assessments.test.ts`
- `frontend/app/composables/__tests__/useAssessments.test.ts`

截至本文更新时：

- 后端全量：`622 passed, 1 skipped`。
- Assessment gradebook：`56 passed`。
- 前端全量：`244 passed`。
- Nuxt 静态生成：成功，预渲染 22 个路由。
- 跳过项：未设置 `MYSQL_TEST_URL`，真实 MySQL 迁移测试未执行。

## 9. 待完成内容

### P0：补齐首期闭环

1. **缺考状态修改**
   - 增加 participant attendance API。
   - 仅允许 `recording` 状态修改。
   - 改为 `absent` 时明确成绩保留还是清空；建议首期清空逐题成绩并写事件，避免缺考者残留总分。
   - 增加名单页切换控件和审计事件。

2. **带原因解锁**
   - 实现 `locked -> recording`。
   - 仅 `MANAGE_ASSESSMENT` 可执行。
   - 请求必须提供非空 `reason`，写入 `ExamEvent(unlocked)`。
   - 前端使用确认对话框和原因输入，不允许静默解锁。

3. **基础统计**
   - 考试维度：参考人数、缺考人数、录入完成数、平均分、最高分、最低分、及格率。
   - 题目维度：平均得分和平均得分率。
   - 客观题在未来有作答事实后再计算正确率；当前只有得分，不应把“满分”偷换为“答对”。
   - 主观题使用平均得分率、满分率和零分率，不定义简单正确率。

### P1：管理与可追溯性

4. **审计时间线 API/UI**
   - 分页读取 `ExamEvent`，默认按 ID 倒序。
   - 展示创建、开始录入、单行保存、Excel 导入、锁定和解锁。
   - 对批量导入仅展示摘要，按需展开 payload，避免页面过载。

5. **归档状态**
   - 实现 `locked -> archived`。
   - 归档只影响业务可见性，不删除成绩事实。
   - 明确是否支持 `archived -> locked`；建议首期不支持。

6. **考试编辑与删除策略**
   - 当前没有考试重命名、删除或撤销创建 API。
   - 建议只允许删除未开始录入的 draft；已有事件或成绩的考试使用归档，不做物理删除。

### P2：规模与扩展

7. 班级超过 200 人时，成员选择改为服务端搜索和分页。
8. Gradebook 增加服务端分页、按学号/姓名搜索和录入状态过滤。
9. 支持统计导出和正式成绩单导出，不与“可回导模板”混用。
10. 接入在线考试时新增 Attempt/Submission/Answer 等作答事实，不把答案 JSON 塞入 `ExamScoreItem`。
11. 自动判分通过独立 grading service 写入成绩，并沿用 revision 和 ExamEvent。

## 10. 验收方法

### 10.1 环境准备

```bash
cd backend
uv sync
uv run alembic upgrade head
```

启动后端：

```bash
cd backend
uv run fastapi dev app/main.py
```

启动前端：

```bash
cd frontend
pnpm install
pnpm dev
```

默认前端为 `http://localhost:3000`；端口占用时 Nuxt 会选择下一个可用端口。开发环境 `/api` 代理到后端。

### 10.2 自动化验收

聚焦后端：

```bash
cd backend
uv run pytest tests/test_api_assessment_exam_sessions.py tests/test_api_assessment_gradebook.py -q
```

后端全量：

```bash
cd backend
uv run pytest -q
```

前端全量与生产生成：

```bash
cd frontend
pnpm test
pnpm generate
```

差异检查：

```bash
git diff --check
git status --short --branch
```

真实 MySQL 迁移验收需要设置独立测试库：

```bash
cd backend
MYSQL_TEST_URL='mysql+aiomysql://user:password@127.0.0.1:3306/question_bank_test' \
  uv run pytest tests/test_migrations.py -q
```

测试库必须可清理，禁止指向开发或生产数据库。

### 10.3 手工功能验收

#### A. 权限和导航

1. 使用 Manager 登录，确认侧栏显示“考试”和“学生名册”。
2. 使用 Editor 登录，确认可以查看考试和录分，但不能创建名册、创建考试、开始录入或锁定。
3. 使用 Viewer 登录，确认不显示 assessment 导航，直接访问相关 API 返回 `403`。

#### B. 名册与快照冻结

1. 在“学生名册”创建两名学生和一个班级，将学生加入班级。
2. 在共享组稿中启用赋分，为每题设置分值并创建定稿版本。
3. 从定稿版本创建考试。
4. 创建后修改学生姓名或班级成员。
5. 验证考试详情仍显示创建时冻结的姓名、学号和参与者名单。

#### C. 状态和逐题录分

1. 在 draft 状态确认分数输入只读。
2. 点击“开始录入”，确认状态变为 recording。
3. 只录一部分题目，确认总分显示为空且状态为未完成。
4. 录满所有题目，确认总分等于逐题分数之和。
5. 输入负数、超过题目满分或超过两位小数，确认后端拒绝。
6. 保留旧页面，再用另一窗口修改同一学生成绩；旧页面保存应收到冲突并刷新。
7. 所有非缺考学生录满后锁定，确认分数输入和 Excel 导入变为不可用。

#### D. Excel 工作流

1. 在 recording 状态点击“导出”，打开 `.xlsx`，确认包含学号、姓名、逐题列和总分列。
2. 修改多个学生的分数并上传。
3. 确认预检展示变更学生数和变更分数项数，预检期间数据库成绩不变化。
4. 点击“确认导入”，确认全部成绩一次更新且 revision 每行只增加一次。
5. 将任一分值改为超过满分，确认预检指出具体行和字段，应用被禁止。
6. 导出模板后先在页面修改成绩，再上传旧模板，确认提示重新导出。
7. 将另一次考试的工作簿上传到当前考试，确认被拒绝。
8. 重试完全相同的 `batch_id + 文件`，确认不重复增加 revision 或事件；同一 `batch_id` 换文件应返回 `409`。

#### E. 锁定规则

1. 存在任一非缺考学生未录满时点击锁定，确认操作失败。
2. 所有非缺考学生录满后锁定成功。
3. 锁定后调用单行保存或 Excel 应用 API，确认返回 `409`。

### 10.4 验收通过标准

- 自动化测试和 Nuxt 生成全部通过。
- SQLite 迁移无模型漂移；发布前应补跑真实 MySQL 迁移测试。
- 跨学科资源访问不可泄露资源存在性。
- 并发冲突不会覆盖较新的成绩。
- Excel 任一行失败时数据库无部分更新。
- 网络重试不会重复增加 revision 或审计事件。
- 锁定后的成绩不可写。

## 11. 已知风险和注意事项

- 当前 feature branch 工作树包含全部新增代码，尚未 commit；交接后不要重建分支或覆盖未提交文件。
- Excel `_meta` 是完整性与并发校验信息，不是防篡改签名。当前威胁模型是防误操作，不是对抗恶意教师；如需不可信客户端上传，应增加服务端签名。
- `ExamEvent.payload` 包含成绩变化信息。提供审计 API 时必须继续执行学科权限校验，并控制敏感信息暴露。
- 当前 gradebook 返回全班完整矩阵，班级和题目规模增大后响应体会快速增长，需要分页或虚拟化。
- Nuxt 生产生成存在既有的大 chunk 警告，不是本功能引入的构建失败。
- SQLAlchemy 全量测试存在既有 warning；当前无 Assessment 测试失败。

## 12. 后续实施建议顺序

建议继续按小纵向切片推进：

1. 缺考状态 API、审计、UI 和锁定规则测试。
2. 带原因解锁 API、事件和确认对话框。
3. 基础统计 API 与考试详情统计页签。
4. 审计时间线查询和 UI。
5. 归档及 draft 删除策略。

每个切片均先写状态/权限/事务失败测试，再实现 service、capability、API 和 UI，最后运行聚焦测试、全量测试和生产生成。