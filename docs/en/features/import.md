# Smart Import

Smart Import lets you upload raw materials and extract them into structured questions through a three-step **Upload → Review → Save** flow. Two **parsing methods** are supported:

- **AI Extraction**: AI automatically recognizes question structure; suited to documents and images without a fixed format.
- **Tag-Based Parsing**: parses precisely by tags such as `【题目】【选项】【答案】`, **without AI** — instant and fully controllable.

## Supported Formats

| Type | Extensions | AI Extraction | Tag-Based Parsing |
|------|--------|:---:|:---:|
| Word | `.docx` | ✅ | ✅ |
| Markdown | `.md` / pasted text | ✅ | ✅ |
| Image | `.png` `.jpg` `.jpeg` `.webp` | ✅ (vision model OCR) | — |

::: tip Prerequisites
**AI Extraction** relies on AI models: text content uses the text model, and images use the **vision model**. Configure and activate the corresponding models in [AI Providers & Models](/en/admin/ai-config) first. **Tag-Based Parsing** requires no AI configuration.
:::

## Tag-Based Parsing

If you already have an electronic draft and are willing to format it with fixed tags, this method is recommended — **zero cost, instant, and 100% controllable**.

### Tag Syntax

Use `【题目】` to separate questions: a question starts at `【题目】` and ends at the next `【题目】` (or the end of the file). Standalone questions only need `【题目】`; material-based question groups additionally need structural tags to declare the material and the group boundaries.

| Tag | Field | Notes |
|------|------|------|
| `【题目】` | Stem | **Required**; also serves as the separator between questions |
| `【题目材料】` | Material | Required for groups; the name is optional — give one when reusing the same material |
| `【题组】` | Group start | Required for groups; if the name is omitted, it refers to the most recently declared material |
| `【题组结束】` | Group end | Optional; questions after it become standalone again |
| `【题型】` | Question type | Write 单选/多选/判断/填空/解答 (single choice / multiple choice / true-false / fill in the blank / free response); inferred automatically if omitted |
| `【选项】` | Options | Write `A. … B. … C. …` inside the block, or use `【选项A】【选项B】` one by one |
| `【答案】` | Answer | Letters for choice questions (e.g. `AB` for multiple choice); `对/错` (true/false) for true/false questions |
| `【解析】` | Explanation | Can span multiple lines |
| `【思路】` | Approach | Can span multiple lines |
| `【难度】` | Difficulty | 1–5, or 简单/中等/困难 (easy/medium/hard) |
| `【小结】` | Summary | Can span multiple lines |

### Example

```
【题目】下列关于集合的说法正确的是
【选项】A. 空集是任何集合的子集  B. 0 是空集  C. {0} 是空集  D. 以上都不对
【答案】A
【解析】空集是任何集合的子集。

【题目】判断：0 是自然数
【答案】对

【题目】1 + 1 = ____
【答案】2
```

### Mixing Material Groups and Standalone Questions

Sub-questions in a group are saved in the order they appear. Questions after `【题组结束】` become standalone again; the current group also ends automatically when a new group starts, a new material is declared, a question-type section heading is encountered, or the end of the file is reached.

```
【题目】卷首独立题
【答案】略

【题目材料】材料一
阅读下面的文字，完成后续题目。

这里可以包含多段 Markdown 内容。

【题组】材料一
1.【题目】请概括题目材料的主要内容
【题型】解答
【答案】略

2.【题目】下列理解正确的是
【题型】单选
【选项】A. 选项一  B. 选项二
【答案】A
【题组结束】

【题目】题组后的独立题
【答案】略
```

Material names are only used within the current file; the system generates internal temporary IDs automatically. The same material can be reused by multiple groups: just write `【题组】材料一` again. A `【题目】` inside a group is only a sub-question of that group and does not produce a duplicate standalone question in the composition.

Structural tags must be on a line of their own. Duplicate material names, references to unknown materials, empty materials, or empty groups block the import during the review pre-check, so the structure of the original file is never silently changed.

### Unified Answer Section (Optional)

Some papers put all answers and explanations together at the end instead of following each question with `【答案】【解析】`. In that case, add an `【答案区】` tag after the questions (aliases: `【答案表】`/`【统一答案】`/`【答案速查】`). Content after the tag is parsed in the following two structures:

```
【答案区】
| 题号 | 1 | 2 |
|:---:|:---:|:---:|
| 答案 | B | C |

1．B因为……
2．C因为……
```

- **Answers**: taken by question number from the `题号 | 答案` (number | answer) table.
- **Explanations**: each numbered paragraph (`1．……` `2．……`) is used in full as the explanation for that question number. If a paragraph begins by repeating the answer (e.g. `10．ACD对于……`), that repeated prefix is removed automatically.
- If a question's answer is not in the table (common for fill-in-the-blank and free-response questions, where the answer is written at the start of the explanation and is hard to separate), you can add `【答案】`/`【解析】` tags under that question number. These take precedence over the table and numbered paragraphs:

  ```
  12．【答案】20/21【解析】此人患色盲的概率……
  ```

- `【答案区】` may be preceded by other heading text (e.g. "参考答案【答案区】"); the tag does not need to be at the start of the line.

### Automatic Question Type Inference

When `【题型】` is omitted, the type is determined as follows: options + a single answer letter → single choice; options + multiple letters → multiple choice; no options + answer is `对/错/√/×` → true/false; no options + stem contains `____` → fill in the blank; everything else → free response.

### Fault Tolerance and Warnings

The parser **does its best and does not stop because of formatting problems in individual questions**. Missing answers, out-of-range answers, empty stems, stray text at the beginning, and similar issues are flagged with a **yellow warning** on the affected question in the review page, so you can fix them on the spot.

## Three-Step Flow

### 1. Upload

First choose the **parsing method** (AI Extraction / Tag-Based Parsing), then choose a data source to upload a file or paste content.

When you choose **AI Extraction**, you can also pick a processing mode:

- **Extract (extract)**: the default; extracts existing questions from the material.
- **Solve (solve)**: has the AI solve the questions.

### 2. Review

After AI extraction, the results are shown question by question in editable form, with fields including:

- Stem, question type, options, answer, explanation, approach, difficulty
- AI-suggested tags (year, source, grade, semester, exam type, feature, etc.)

You can edit, delete, or adjust each question before confirming.

### 3. Save

After you confirm, the questions are written to the question bank in bulk and linked to this **Import Task**, so you can later filter and manage them by batch.

### Duplicate Check

On the review page, every question is automatically compared with the question bank and with the other questions in this import (same rules as [Question Bank · Duplicate Check](/en/features/questions#duplicate-check)):

- A summary at the top shows how many questions are duplicates or highly similar; each question is marked "Duplicate / Similar xx%" and can be expanded to compare with existing questions.
- Standalone questions that **duplicate** an existing question, or an earlier question in this import, are **unselected by default**; highly similar questions stay selected with a warning.
- **Keeping a question selected confirms importing it.** Sub-questions of a material can't be unselected individually and are only marked.
- The server checks again on submit; duplicates added by others during your review are skipped unless confirmed, and the result explains why.

## Import Task Status

Each import creates an Import Task, with the following statuses:

| Status | Meaning |
|------|------|
| `PENDING` | Queued |
| `PROCESSING` | Processing |
| `COMPLETED` | Completed |
| `FAILED` | Failed |
| `CANCELLED` | Cancelled |

## Batch Management

- **Queue status**: view counts of queued / processing / completed / failed / cancelled tasks, plus active tasks.
- **Import history**: browse past imports with pagination, filterable by status and user.
- **Permissions**: Super Administrators can see all Import Tasks; regular users only see their own.
- **Possible duplicates**: background batch imports run unattended, so possible duplicates are imported as usual and flagged as "Possible duplicates" in the task result. Open it to compare each question and delete the new ones you don't need.

## FAQ

- **Inaccurate extraction results?** Adjust the [Prompt Templates](/en/admin/prompts) or switch to a stronger model.
- **Image recognition fails?** Make sure a **vision model** is activated and the image is clear.
- **Stuck in processing?** (Server edition) Check the [Worker logs](/en/server/operations#background-worker).
