# PRD:题目数据模型 v2(考试系统重构)

> 状态:设计定稿 · 实施中(Phase 1)
> 范围:题目**数据接口(逻辑契约)** + **RichDoc / Tiptap schema** + **MD→Tiptap 转换规格** + **物理存储与迁移**。
> 不含:AI 导入、Paper 导出(后续独立 PRD;本期只保证数据结构可被它们消费)。

## 0. 已确认决策(实施基线,优先级高于下文旧措辞)

1. **版本编号**:`SCHEMA_VERSION = 1`(v2 内容的目标版本号)。**存量未迁移**行的 `content_schema_version = 0`。
2. **迁移闸门**:只处理 `content_schema_version < 1` 的行;转换成功置 `1`;`downgrade()` 从归档表还原并把版本拨回 `0`。下文 §8/§10/§12 中出现的 "`version < 2`" / "置 `2`" / "拨回 `1`" 为旧草稿措辞,一律以本条 `< 1 / 1 / 0` 为准。
3. **`legacy_unresolved` variant**:新增一个**只读、仅迁移期**产生的 `AnswerSpec` variant,承载无法解析的旧答案原文;正式的 `single_choice` / `multiple_choice` / `true_false` 的 `correct` 字段**保持非空**(不允许用空 `correct` 表达"未解析")。
4. **API 字段名**:对外 API 继续沿用 `content` / `thinking` / `analysis` / `summary` 等既有名称(逻辑名 `stem` / `explanation.*` 仅用于文档),不改动前端契约字段名。
5. **迁移实现**:MD→RichDoc 与答案转换统一用 **Python 转换器**(`app/services/question_content_v1.py`),Alembic data-migration 直接调用它,不再依赖前端一次性 Node 脚本。
6. **`needs_review`**:仅存在于数据库列,用于人工复核筛选,**不进入 API 响应 / pydantic schema**。
7. **AI / Paper**:本期只做**最小适配**保证可消费新结构,完整改造留后续 PRD。

## 1. 背景与目标

现状:题目的 `content` / `answer` / `thinking` / `analysis` / `summary` 存的是 **Markdown 字符串**,`options` 是 `[{label, content(md)}]`,填空答案是 `List[List[str]]` 的 JSON 串,选择题正确答案混在自由文本 `answer` 里。

问题:

- 富文本与"可判分答案"混杂,无法机器判分。
- 选择题答案是自由文本("A""答案:A,因为…"),无稳定引用。
- 填空答案与题干中的空没有明确绑定。

目标:用**考试系统**思路重构 —— 富文本内容、结构化答案、解析三层分离;答案可机器判分;对未来题型向前兼容。存量 Markdown **一次性迁移**为 Tiptap JSON,此后只维护一套渲染/导出链路。

## 2. 设计原则

1. **三层分离**:题干/选项/解析是**富文本**;答案是**结构化、可判分**的数据;不再混在一个 md 串里。
2. **RichDoc 为唯一富文本原子**:所有富文本槽位都是一个 Tiptap `doc` JSON,渲染/导出只需一套。
3. **答案用判别联合(discriminated union)**:按 `kind` 区分,新增题型只加一个 variant,不动存量行。
4. **引用用稳定 id,不用展示序号**:选项/填空用内部 `id` 绑定答案,`label`("A"/"甲")只用于展示,支持乱序、改标签不坏数据。
5. **空 = `null`**,不存空 doc。
6. **迁移不丢内容**:任何无法识别的输入降级为纯文本保留,脏数据打标记待人工复核。

## 3. 核心类型

```ts
// 富文本原子:一个 Tiptap 文档;空值用 null
type RichDoc = { type: "doc"; content: Node[] } | null

// 稳定标识(非展示序号),如 "opt_a1b2" / "blk_1"
type Id = string

// v2 内容的目标结构版本(存量未迁移行为 0,见 §0)
const SCHEMA_VERSION = 1
```

## 4. 题目通用结构(envelope)

```ts
interface Question {
  id: number
  q_type: QuestionType
  version: number                 // = SCHEMA_VERSION

  stem: RichDoc                   // 题干(物理列仍叫 content)
  options?: Option[]              // 仅选择类题型
  answer: AnswerSpec              // 判别联合,见 §6(可判分/参考答案)
  explanation: Explanation        // 解析三段

  // 以下结构/元数据不变
  // status / difficulty / subject_id / tags / knowledge_points / parent_id / children ...
}

type QuestionType =
  | "single_choice" | "multiple_choice" | "true_false"
  | "fill_in_the_blank" | "free_response"
  // 预留(本期不实现,schema 已可容纳):"matching" | "ordering"

interface Option {
  id: Id                          // 答案引用它,不引用 label
  label: string                   // 展示序号 "A"/"B"…
  content: RichDoc                // 选项正文(可含公式/图)
}

interface Explanation {
  thinking?: RichDoc              // 分析
  analysis?: RichDoc              // 解析
  summary?:  RichDoc              // 总结
}
```

## 5. 各字段数据接口

| 逻辑字段 | 类型 | 说明 |
|---|---|---|
| `stem` | `RichDoc` | 题干;填空题内可含行内 `blank` 节点(见 §7) |
| `options` | `Option[]` | 仅选择类;`id` 稳定、`label` 仅展示、`content` 为 RichDoc |
| `answer` | `AnswerSpec` | 判别联合,见 §6 |
| `explanation.{thinking,analysis,summary}` | `RichDoc?` | 各可空 |

- 判断题**不使用** `options`(用布尔答案,见 §6.3)。
- 顶层永远是 `doc`(选项内容、每个填空答案也是完整 `doc`),渲染/导出零特例。

## 6. AnswerSpec 判别联合(各题型答案怎么存)

```ts
type AnswerSpec =
  | SingleChoiceAnswer
  | MultipleChoiceAnswer
  | TrueFalseAnswer
  | FillBlankAnswer
  | FreeResponseAnswer
  | LegacyUnresolvedAnswer         // 只读、仅迁移期产生,见 §6.6
```

### 6.1 单选 single_choice

```ts
interface SingleChoiceAnswer {
  kind: "single_choice"
  correct: Id                     // 指向 options[].id,单个
}
```

判分:`submitted === correct`。

### 6.2 多选 multiple_choice

```ts
interface MultipleChoiceAnswer {
  kind: "multiple_choice"
  correct: Id[]                   // 指向 options[].id 的集合(无序)
  grading?: "all_or_nothing" | "partial"   // 预留,默认 all_or_nothing
}
```

判分:集合相等(`all_or_nothing`);`partial`(部分给分)本期只存不判。
**存的是选项 id 的集合,不是 "ABD" 字符串** → 乱序/改标签不坏。

### 6.3 判断 true_false

```ts
interface TrueFalseAnswer {
  kind: "true_false"
  correct: boolean                // true=对 / false=错
}
```

展示层把 boolean 映射成 对/错、√/×、正确/错误;数据只存布尔。

### 6.4 填空 fill_in_the_blank(多空 + 每空多解)

```ts
interface FillBlankAnswer {
  kind: "fill_in_the_blank"
  blanks: Blank[]                 // 有序;第 i 项对应第 i 个空
}

interface Blank {
  id: Id                          // 与 stem 内 blank 节点的 blankId 对应(新内容)
  accept: RichDoc[]               // 该空的多个可接受答案(每个都是 RichDoc,可含公式)
  match?: "exact" | "ignore_space" | "ignore_case" | "numeric"  // 预留判分策略,默认 exact
}
```

- **多个空**:`blanks` 数组,顺序 = 空在题干出现顺序。
- **绑定方式**:新内容用 stem 内 `blank` 节点的 `blankId` 精确绑定;存量迁移用数组下标顺序绑定(题干里的 `____` 视觉占位不变)。
- **答案对应**:第 `i` 个空 → `blanks[i]`;该空允许的多个答案 → `blanks[i].accept[]`(升级自旧 `List[List[str]]`,每个答案从纯字符串升级为 RichDoc,可放公式)。

示例(两空,第一空两解且含公式):

```json
{
  "kind": "fill_in_the_blank",
  "blanks": [
    { "id": "blk_1", "accept": [
        {"type":"doc","content":[{"type":"paragraph","content":[{"type":"text","text":"2"}]}]},
        {"type":"doc","content":[{"type":"paragraph","content":[{"type":"inlineMath","attrs":{"latex":"\\sqrt2"}}]}]}
    ]},
    { "id": "blk_2", "accept": [
        {"type":"doc","content":[{"type":"paragraph","content":[{"type":"text","text":"3"}]}]}
    ]}
  ]
}
```

### 6.5 解答 free_response

```ts
interface FreeResponseAnswer {
  kind: "free_response"
  reference: RichDoc              // 参考答案(可判分性弱,人工/未来 rubric)
  rubric?: RubricItem[]           // 预留评分点,本期不实现
}
```

### 6.6 迁移兜底 legacy_unresolved(只读,仅迁移期)

```ts
interface LegacyUnresolvedAnswer {
  kind: "legacy_unresolved"
  expected_kind: QuestionType     // 迁移前预期题型
  raw: RichDoc                    // 无法解析的旧答案原文(不丢弃)
}
```

- **只读**:仅由存量迁移产生,前端不提供该 variant 的编辑分支;人工复核后应改成正式 variant。
- 该行同时在数据库 `needs_review = 1`(§0.6:`needs_review` 不进 API,仅供后台筛选)。
- 正式 choice/true_false 的 `correct` 永远非空;"未解析"只用这个 variant 表达,不用空 `correct`。

## 7. RichDoc / Tiptap Schema 白名单 + MD→Tiptap 映射

MD→Tiptap 转换器的**目标节点集必须 = 编辑器/渲染器 schema**(`frontend/app/components/rich-editor/schemaExtensions.ts`),否则跑版丢内容。

### 7.1 节点 / Mark 白名单

| Tiptap 节点/Mark | 来源(Markdown) | 状态 |
|---|---|---|
| `doc` / `paragraph` / `text` | 段落 | 已有 |
| `bold` mark | `**x**` / `__x__` | 已有 |
| `italic` mark | `*x*` / `_x_` | 已有 |
| `superscript` | `<sup>` | 已有 |
| `subscript` | `<sub>` | 已有 |
| `bulletList` / `orderedList` / `listItem` | `- ` / `1. ` | 已有 |
| `hardBreak` | 行尾两空格 / 换行 | 已有 |
| `inlineMath`(attr `latex`) | `$...$` | 已有 |
| `blockMath`(attr `latex`) | `$$...$$` | 已有 |
| `image`(attr `src`,`alt`) | `![alt](url)` | 已有 |
| `textAlign`(paragraph 属性) | 无 md 对应,保持默认 | 已有 |
| `table` / `tableRow` / `tableCell` | `\| a \| b \|` | **需补扩展** |
| `blank`(attr `blankId`) | 无 md 对应(填空新节点) | **需新增** |

### 7.2 转换决策(已定稿)

- **降级策略(已决定)**:`heading(#)`、`blockquote(>)`、`strike(~~x~~)`、`code`/代码块、`horizontalRule(---)` 一律**降级为纯文本段落**,保留其可见文字,**不启用对应节点**。
- **兜底规则**:任何无法识别的 Markdown / HTML → 包成 `paragraph` + `text` 保留原文,**绝不静默丢字符**。
- **空 / 边界**:空字段 → DB `NULL`;`Blank.accept[]` 至少 1 项;`Option` 必有 `id`。

### 7.3 MD→Tiptap 映射细则

- 行内公式 `$...$` → `inlineMath { attrs.latex }`;块公式 `$$...$$` → `blockMath { attrs.latex }`。latex 原样保留,不做转义处理。
- 图片 `![alt](url)` → `image { attrs.src=url, attrs.alt=alt }`;`/static/media/` 路径原样保留。
- 上/下标源为 HTML `<sup>` / `<sub>`(旧编辑器产出)→ 对应 mark。
- 列表 / 加粗 / 斜体按标准 CommonMark 语义映射。
- 降级项按 §7.2 处理。

> 实现约束:存量迁移的 MD→Tiptap 使用 **Python 转换器**,由 Alembic data revision 直接调用,确保桌面无人值守迁移不依赖 Node.js。前端使用共享 fixtures 验证转换结果与 Tiptap schema 兼容。

## 8. 物理存储映射与模型改动

逻辑接口 → 现有列(**列基本不变,语义升级**):

| 逻辑字段 | 物理列 | 变化 |
|---|---|---|
| `stem` | `content` | `TEXT` → `LONGTEXT`,存 RichDoc JSON 字符串 |
| `options` | `options`(已 JSON) | 结构升级为 `{id,label,content:RichDoc}` |
| `answer`(AnswerSpec) | `answer` | `TEXT` → `LONGTEXT`,**统一存判别联合 JSON**(取代旧 md 串 / `List[List[str]]`) |
| `explanation.*` | `thinking` / `analysis` / `summary` | `TEXT` → `LONGTEXT`,各存 RichDoc JSON |
| — | 新增 `content_schema_version SMALLINT NOT NULL DEFAULT 0` | 结构 revision 标记存量行未迁移;data revision 完成后将新行默认值改为 1 |
| — | 新增 `needs_review BOOL NOT NULL DEFAULT 0` | 迁移无法解析行的人工复核标记(见 §10) |

`Question` 主键 / 关系 / 父子(材料题)/ 元数据一律不动。

### 8.1 原始数据保全:快照归档表(方案二,已定稿)

本项目是**开源、有存量用户**,且以**桌面 App** 形态自动在用户本机 MySQL 上无人值守跑迁移(`run.py` 启动即 migrate),外部备份指望不上。因此迁移必须自带**库内后悔药**。

**做法**:`questions` **原地升级**(不新建 `questions_v2`,避免拖动 tags / knowledge_points / papers / activity_log 多态 / self-ref 这整张 FK 关系图);迁移前先把 v1 原文**快照**进一张无 FK 的纯归档表 `questions_content_archive_v1`。

归档表(迁移内联定义,**不进 ORM 模型**):

| 列 | 类型 | 说明 |
|---|---|---|
| `question_id` | `INT` PK | = `questions.id`,**不加外键**(纯快照,避免级联/删除耦合) |
| `content` / `answer` / `thinking` / `analysis` / `summary` | `LONGTEXT` | v1 原文快照 |
| `options` | `JSON` | v1 原 options 快照 |
| `archived_at` | `DATETIME` | 快照时间 |

- 归档表不对外暴露:无端点、无 pydantic schema、`CRUDBase` 不感知,纯保险。
- **不进 ORM / autogenerate**:`alembic/env.py` 用 `include_object` 精确忽略表名
  `questions_content_archive_v1`(仅此一张,不宽泛忽略其它对象),否则 `alembic check`
  会把它误报成"应 DROP"的漂移。
- **可重放**:任何行事后发现转错,从归档表取原文重跑 MD→RichDoc 即可,不依赖外部备份。
- **可清理**:观察期 + 抽样复核 `needs_review` 后,用独立 Alembic revision `DROP TABLE` 收尾,不留长期负担。

## 9. 向前兼容策略

1. **新增题型**:只加 `AnswerSpec` 一个 `kind` variant + 前端一个编辑/渲染分支,存量行不受影响。
2. **填空绑定双模式**:新内容用 `blank` 节点 `blankId` 精确绑定;旧内容按 `blanks[]` 下标顺序绑定 → 平滑升级。
3. **稳定 id**:选项/空用 `id` 引用,允许改 `label`、乱序、洗牌。
4. **legacy 兜底**:迁移期无法解析的旧数据(见 §10)原文进兜底字段并打 `needs_review` 标记,不丢弃;且**全部 v1 原文另存快照归档表 `questions_content_archive_v1`(§8.1),可随时重放转换**。
5. **版本列**:`content_schema_version` 让下一次 schema 演进可定向迁移。

## 10. 存量迁移映射规则(v1 → v2)

> 前置:转换**之前**先把每行 v1 原文快照入 `questions_content_archive_v1`(§8.1);转换以 `content_schema_version` 为幂等闸门(只处理 `version < 1` 的行),可安全重跑。

- **stem / explanation / option.content**:`MD → RichDoc`(§7 转换器),直译。
- **选择题 answer**(旧为自由 md 串,如 "A" / "答案:A,因为…"):
  - 抽取字母 → 映射到对应 `option.label` → 得 `option.id` → 填 `correct`;
  - 多余解释性文字 → 迁移进 `analysis`;
  - **无法解析** → 写入 `legacy_unresolved`(包含预期题型与原答案 RichDoc),原文同时并入 `analysis`,打 `needs_review` 标记。
- **多选**:解析 "ABD" / "A、B、D" → 多个 id 集合。
- **判断**:识别 对/错/√/×/T/F → boolean。
- **填空**(旧 `List[List[str]]`):按顺序生成 `blanks[i].id = blk_{i+1}`,每个 str → `accept[j]` 的 RichDoc;题干 `____` 保留(下标绑定)。
- **解答**:旧 md answer → `reference` RichDoc。

## 11. 校验规则(pydantic)

- `answer.kind` 必须与 `q_type` 一致。
- choice:`correct` 引用的 id 必须存在于 `options`。
- fill:`blanks` 非空、每空 `accept` 非空;题干含 `blank` 节点时,`blankId` 与 `blanks[].id` 一一对应。
- 每个 RichDoc 根节点 `type === "doc"`。

## 12. 实施顺序(建议,验证优先)

1. 写 **MD→Tiptap Python 转换器**,并用前端共享 fixtures 做 Tiptap schema 契约测试;对生产数据副本 **dry-run**;`to_plain_text(convert(md))` 与原文去格式后文本等价,抽样人工比对渲染。转换器对同一 md 结果确定、迁移可重跑。
2. 定 **pydantic schema**(§3–§6)与校验(§11)。
3. **Revision 1(结构)**:`just make_migration` 改列类型(LONGTEXT)+ 新增 `content_schema_version` / `needs_review`(§8)。revision `f1a2b3c4d5e6`,方言感知(MySQL `LONGTEXT` / SQLite `TEXT`),SQLite 走 batch 重建。
4. **Revision 2(快照 + 数据转换,data-only,内联 `sa.table`)**— revision `a7b8c9d0e1f2`,down_revision `f1a2b3c4d5e6`,全程幂等、可重跑:

  - a. `CREATE TABLE questions_content_archive_v1`(用 inspector 检测,已存在则跳过)。
  - b. **分批**(`LIMIT 500`,以 `version < 1` 为滚动闸门)读待转换行;先把其中**尚未入归档表**的行快照进归档表(逐批 `NOT IN archive` 去重,而非一次性 `INSERT ... SELECT`,以便同批直接喂 Python 转换器且不重复归档)。
  - c. 逐行调 `app/services/question_content_v1.py` 转换六个内容字段 + options 写回 `questions`(内容字段存 JSON **字符串**、`options` 存 JSON **对象**;全程 Core,JSON 参数在 SQLite/MySQL 一致),成功即置 `content_schema_version = 1`。
  - d. 转换失败/无法解析的行:原文降级保留(§10)+ `needs_review = 1`,`version` **仍置 1**(避免重跑死循环)。选择/判断的 `legacy_unresolved` 用确定性 RichDoc 合并 helper `merge_legacy_answer_into_analysis` 把原答案原文**追加**进 `analysis`(不覆盖既有解析)。事后从归档表人工救。
  - e. upgrade 末尾把 `content_schema_version` 的 server_default 从 0 改为 1(与 ORM `SCHEMA_VERSION=1` 对齐)。`downgrade()`:从归档表逐批还原**仍存在**的 `question_id` 的六个内容字段 + options,`version` 拨回 0、`needs_review` 清 0,server_default 改回 0;**归档表保留不 drop**(真可回滚,因原文还在)。

  > MySQL DDL 非事务(隐式 commit),建表/回填/转换不是原子事务;靠上述 "inspector 建表跳过 + `version<1` + `NOT IN archive`" 的幂等设计兜底,而非依赖事务回滚。

5. 前端切 `RichEditor` + `renderRichContentToHTML`,移除 Markdown 分支。
6. **清理(独立 Revision,下一个发布版才合入)**:观察期 + 抽样复核 `needs_review` 后 `DROP TABLE questions_content_archive_v1`。

## 13. 后续 PRD(依赖本模型,本期不做)

- AI 导入:AI 产出 Markdown → 复用 §7 转换器入库。
- Paper 导出:`RichDoc → LaTeX`(纯 Python 遍历,math 节点已带 `latex`)替换现有 `_md_to_latex`。
- 判分引擎:基于 §6 的 `AnswerSpec` 做自动判分(选择/判断/填空)。



---

## 验收测试

建议分成四层验证：自动测试、迁移演练、UI 手测、回滚验证。**不要先在唯一的生产数据库上试迁移**。

**1. 自动验证**

后端：

```bash
cd /home/rafi/code/for_mei/question-bank/backend

uv run pytest -q
uv run pytest tests/test_migrations.py -q
uv run alembic heads
```

预期：

- `125 passed`
- 只有真实 MySQL 测试因未设置 `MYSQL_TEST_URL` 而跳过
- Alembic 只有一个 head：`a7b8c9d0e1f2`

前端：

```bash
cd /home/rafi/code/for_mei/question-bank/frontend

pnpm test
pnpm generate
```

预期：

- `29 passed`
- `pnpm generate` 成功生成 `.output/public`

**2. 在测试数据库演练迁移**

推荐新建独立 MySQL 数据库，例如 `question_bank_v2_test`，不要复用正式库。

设置测试连接：

```bash
cd /home/rafi/code/for_mei/question-bank/backend

export DB_URL='mysql+aiomysql://用户名:密码@127.0.0.1:3306/question_bank_v2_test'
```

先确认当前迁移状态：

```bash
uv run alembic current
uv run alembic history --verbose
```

若测试从空库开始，先停在 v2 之前：

```bash
uv run alembic upgrade 326519e83a77
```

然后用 MySQL 客户端插入几条 v1 题目。至少准备：

- 单选：答案 `A`
- 多选：答案 `A、C`
- 判断：答案 `对`
- 填空：答案 `[["北京"], ["中国"]]`
- 解答：Markdown 参考答案
- 脏单选：答案 `见解析`

示例：

```sql
INSERT INTO questions
(content, options, answer, thinking, analysis, summary, q_type, status, difficulty)
VALUES
(
  '下列哪项等于 **2**？',
  JSON_ARRAY(
    JSON_OBJECT('label', 'A', 'content', '1+1'),
    JSON_OBJECT('label', 'B', 'content', '1+2')
  ),
  'A',
  NULL,
  '基础计算',
  NULL,
  'single_choice',
  'published',
  1
);
```

执行完整升级：

```bash
uv run alembic upgrade head
```

检查结果：

```sql
SELECT
    id,
    q_type,
    content_schema_version,
    needs_review,
    LEFT(content, 100) AS content_preview,
    LEFT(answer, 100) AS answer_preview
FROM questions
ORDER BY id;

SELECT question_id, content, answer, options
FROM questions_content_archive_v1
ORDER BY question_id;
```

验收标准：

- 所有迁移行 `content_schema_version = 1`
- 正常题目 `needs_review = 0`
- 脏答案题目 `needs_review = 1`
- `content` 是以 `{"type":"doc"...}` 开头的 JSON
- `answer` 是包含 `kind` 的 AnswerSpec JSON
- 选择题答案引用 `options[].id`，不再引用 `A/B`
- 归档表行数与迁移前 v1 题目数一致
- 归档表内容仍是原始 Markdown 和旧答案

可执行：

```sql
SELECT COUNT(*) FROM questions_content_archive_v1;
SELECT COUNT(*) FROM questions WHERE content_schema_version = 1;
SELECT id, q_type FROM questions WHERE needs_review = 1;
```

**3. 验证迁移幂等和回滚**

只回滚数据 revision，保留 v2 结构：

```bash
uv run alembic downgrade f1a2b3c4d5e6
```

检查：

```sql
SELECT
    id,
    content,
    answer,
    content_schema_version,
    needs_review
FROM questions;
```

预期：

- 原始 Markdown 和旧答案恢复
- `content_schema_version = 0`
- `needs_review = 0`
- `questions_content_archive_v1` 仍然存在

重新升级：

```bash
uv run alembic upgrade head
```

确认第二次转换结果与第一次一致，归档表没有重复行。

需要完整验证结构回滚时，可以在测试库运行：

```bash
uv run alembic downgrade 326519e83a77
```

确认新列被删除，原始字段仍已恢复。随后再次：

```bash
uv run alembic upgrade head
```

**4. 启动应用手动测试**

后端：

```bash
cd /home/rafi/code/for_mei/question-bank/backend
uv run fastapi dev app/main.py
```

前端：

```bash
cd /home/rafi/code/for_mei/question-bank/frontend
pnpm dev
```

打开 [http://localhost:3000](http://localhost:3000)。

当前前端开发服务器可能已经占用 `3000`。若提示端口冲突，可直接使用现有服务，或换端口：

```bash
pnpm dev --port 3001
```

**5. 五种题型 UI 清单**

单选题：

1. 新建单选题。
2. 输入带粗体、公式和图片的题干。
3. 填写至少两个选项。
4. 选择一个正确答案。
5. 保存并重新打开。
6. 确认答案仍指向原选项。
7. 删除已选中的选项，确认前端阻止无效保存或要求重新选择。

多选题：

1. 勾选两个以上答案。
2. 保存并重新打开。
3. 确认答案集合保持正确。
4. 删除一个已选选项，确认答案引用被同步清理。

判断题：

1. 分别保存“正确”和“错误”。
2. 确认请求中的 `correct` 是布尔值，而非字符串。
3. 确认判断题没有 options。

填空题：

1. 在题干编辑器中点击“插入填空”。
2. 插入两个空，确认答案区自动出现两个对应项。
3. 为第一个空添加两个可接受答案。
4. 输入公式答案。
5. 删除题干中的一个 blank，确认答案区同步。
6. 保存并重新打开，确认 `blankId` 顺序一致。

解答题：

1. 输入富文本参考答案。
2. 加入公式、列表和图片。
3. 保存并重新打开。
4. 确认内容没有退化成 JSON 字符串或 Markdown 源码。

**6. 富文本节点验证**

至少测试：

- 粗体、斜体
- 上标、下标
- 行内公式、块公式
- 无序列表、有序列表
- 图片上传
- 表格
- 填空节点
- 空字段保存为 `null`

重点检查：

- 编辑器中正常显示
- 列表页正常显示
- 试卷题目页正常显示
- 重新打开编辑器后结构没有丢失
- 页面上不出现原始 `{"type":"doc"...}` JSON

**7. 智能导入验证**

在智能导入页准备两道题：

- 一道答案明确，例如单选答案 `A`
- 一道无法解析，例如答案 `见解析`

提交后预期：

- 明确题目成功导入
- 无法解析题目被跳过并显示 warning
- 不会创建 `legacy_unresolved` 新题目
- 返回结果表现为部分成功
- 数据库只增加成功题目

接口是：

```text
POST /api/v1/questions/batch-legacy
```

**8. Paper 导出验证**

创建包含五种题型的试卷，分别测试：

- Markdown 导出
- LaTeX/PDF 或现有支持的文档格式
- 包含答案
- 包含分析、解析、总结
- 题干和答案含公式
- 题干或选项含图片
- 填空题含多个可接受答案

重点确认：

- 选择答案显示 `A/B`，而不是 `opt_xxx`
- 判断答案显示“对/错”
- RichDoc JSON 不会进入导出文件
- 图片路径可正常解析
- 表格至少不导致导出异常

**9. 发布前数据库核对**

```sql
SELECT content_schema_version, COUNT(*)
FROM questions
GROUP BY content_schema_version;

SELECT q_type, COUNT(*)
FROM questions
WHERE needs_review = 1
GROUP BY q_type;

SELECT COUNT(*) AS archive_count
FROM questions_content_archive_v1;
```

发布前应满足：

- 没有版本为 `0` 的题目
- 所有 `needs_review=1` 行都有归档记录
- 抽样确认归档原文能够恢复
- 本发布不要删除归档表

真实 MySQL 自动化验证可再运行：

```bash
cd /home/rafi/code/for_mei/question-bank/backend

MYSQL_TEST_URL='mysql+aiomysql://用户名:密码@127.0.0.1:3306/question_bank_v2_test' \
uv run pytest tests/test_migrations.py -q
```

这一步是发布前最重要的补充，因为本地自动测试目前只完整跑过 SQLite，MySQL 的 `LONGTEXT`、DDL 隐式提交和实际 downgrade 仍应在独立测试库验证。