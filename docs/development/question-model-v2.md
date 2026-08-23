# PRD:题目数据模型 v2(考试系统重构)

> 状态:设计定稿 · 待实现
> 范围:题目**数据接口(逻辑契约)** + **RichDoc / Tiptap schema** + **MD→Tiptap 转换规格** + **物理存储与迁移**。
> 不含:AI 导入、Paper 导出(后续独立 PRD;本期只保证数据结构可被它们消费)。

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

// 顶层结构版本,便于未来再迁移
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

> 实现建议:存量迁移的 MD→Tiptap 用**前端自带管线**(复用 `tiptap-markdown` + 数学扩展)跑一次性 Node 脚本,保真度最高;桌面运行时不依赖它。运行时 Python 侧只需单向的 `to_plain_text` / `to_latex`(后续 PRD)。

## 8. 物理存储映射与模型改动

逻辑接口 → 现有列(**列基本不变,语义升级**):

| 逻辑字段 | 物理列 | 变化 |
|---|---|---|
| `stem` | `content` | `TEXT` → `LONGTEXT`,存 RichDoc JSON 字符串 |
| `options` | `options`(已 JSON) | 结构升级为 `{id,label,content:RichDoc}` |
| `answer`(AnswerSpec) | `answer` | `TEXT` → `LONGTEXT`,**统一存判别联合 JSON**(取代旧 md 串 / `List[List[str]]`) |
| `explanation.*` | `thinking` / `analysis` / `summary` | `TEXT` → `LONGTEXT`,各存 RichDoc JSON |
| — | 新增 `content_schema_version SMALLINT NOT NULL DEFAULT 1` | 未来再迁移用 |

`Question` 主键 / 关系 / 父子(材料题)/ 元数据一律不动。

## 9. 向前兼容策略

1. **新增题型**:只加 `AnswerSpec` 一个 `kind` variant + 前端一个编辑/渲染分支,存量行不受影响。
2. **填空绑定双模式**:新内容用 `blank` 节点 `blankId` 精确绑定;旧内容按 `blanks[]` 下标顺序绑定 → 平滑升级。
3. **稳定 id**:选项/空用 `id` 引用,允许改 `label`、乱序、洗牌。
4. **legacy 兜底**:迁移期无法解析的旧数据(见 §10)原文进兜底字段并打 `needs_review` 标记,不丢弃。
5. **版本列**:`content_schema_version` 让下一次 schema 演进可定向迁移。

## 10. 存量迁移映射规则(v1 → v2)

- **stem / explanation / option.content**:`MD → RichDoc`(§7 转换器),直译。
- **选择题 answer**(旧为自由 md 串,如 "A" / "答案:A,因为…"):
  - 抽取字母 → 映射到对应 `option.label` → 得 `option.id` → 填 `correct`;
  - 多余解释性文字 → 迁移进 `analysis`;
  - **无法解析** → `correct` 置空 + 原文塞入 `analysis` + 打 `needs_review` 标记。
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

1. 写 **MD→Tiptap 转换器**(前端管线),对生产数据副本 **dry-run**;`to_plain_text(convert(md))` 与原文去格式后文本等价,抽样人工比对渲染。
2. 定 **pydantic schema**(§3–§6)与校验(§11)。
3. 改 **模型**(§8:LONGTEXT + 版本列)并 `just make_migration` / `just migrate`。
4. 写 **Alembic 数据迁移**(§10),迁移前全库备份、转换器可重跑。
5. 前端切 `RichEditor` + `renderRichContentToHTML`,移除 Markdown 分支。

## 13. 后续 PRD(依赖本模型,本期不做)

- AI 导入:AI 产出 Markdown → 复用 §7 转换器入库。
- Paper 导出:`RichDoc → LaTeX`(纯 Python 遍历,math 节点已带 `latex`)替换现有 `_md_to_latex`。
- 判分引擎:基于 §6 的 `AnswerSpec` 做自动判分(选择/判断/填空)。
