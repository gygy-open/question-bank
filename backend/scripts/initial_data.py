import logging
import sys
import os
import asyncio

# Add the parent directory to sys.path to allow importing app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import SessionLocal, engine
from app.crud.crud_subject import subject as crud_subject
from app.crud.crud_system_setting import system_setting as crud_system_setting
from app.schemas.subject import SubjectCreate
from app.schemas.system_setting import SystemSettingCreate
from app.models.subject import Subject
from app.models.system_setting import SystemSetting

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def init_db(db: AsyncSession) -> None:
    # Initialize Subjects
    subjects = [
        {"name": "数学", "slug": "math", "description": "数学科目"},
        {"name": "英语", "slug": "english", "description": "英语科目"},
        {"name": "物理", "slug": "physics", "description": "物理科目"},
    ]

    for subject_data in subjects:
        slug = subject_data["slug"]
        name = subject_data["name"]
        result = await db.execute(select(Subject).filter(
            (Subject.slug == slug) | (Subject.name == name)
        ))
        existing_subject = result.scalars().first()
        if not existing_subject:
            logger.info(f"Creating subject: {subject_data['name']}")
            subject_in = SubjectCreate(**subject_data)
            await crud_subject.create(db, obj_in=subject_in)
        else:
            logger.info(f"Subject already exists: {subject_data['name']} (slug: {existing_subject.slug})")

    # Initialize System Settings
    settings_data = [
        {
            "key": "AI_EXTRACT_PROMPT",
            "value": r"""你是一个专业的数学题目提取助手。请分析下面的 Markdown 内容，提取出所有的数学题目。

## 核心任务
提取 Markdown 中的所有数学题目，并将其转换为结构化的 JSON 数据。

## 提取规则

### 1. 基础信息提取
- **题目类型 (q_type)**：识别为 `single_choice` (单选), `multiple_choice` (多选), `fill_in_the_blank` (填空), `free_response` (解答), `true_false` (判断)。
- **题干 (content)**：
    - **必须**去除开头的题号（如 "1.", "2、", "(1)" 等）。
    - **必须**保留图片链接（如 `/static/media/...`）。
- **选项 (options)**：如果是选择题，提取选项列表。
- **答案 (answer)**：
    - **填空题**：必须返回一个二维数组 `[["答案1A", "答案1B"], ["答案2"]]`。
        - 外层列表对应空的顺序。
        - 内层列表对应每个空允许的备选答案。
        - **重要**：如果原答案中包含“或”、“；”、“,”、“/”等分隔符，**必须**将其拆分为多个备选答案放入内层列表。例如 "1或2" 应转换为 `["1", "2"]`。
        - **格式要求**：所有数学内容（包括数字、变量、公式）**必须**使用 LaTeX 格式包裹（例如 `$1$`, `$x$`, `$\sqrt{2}$`）。纯文本不需要包裹。
    - **其他题型**：返回标准答案字符串。
- **完整性保留**：原样保留 分析 (thinking)、解析 (analysis) 和 总结 (summary)，**严禁修改**。
- **难度评估 (difficulty)**：范围 1-5 (1最易，5最难)。

### 2. 格式规范
- **LaTeX 公式**：检查所有文本字段。如果包含数学公式且未格式化，**必须**转换为 LaTeX 格式（行内用 `$...$`，多行用 `$$...$$`）。

### 3. 知识点提取 (knowledge_points)
- 为每个题目提取 3-5 个核心知识点。
- **要求**：
    - 使用标准学科术语（如"勾股定理"、"二次函数性质"）。
    - 覆盖关键概念、公式、题型或解题方法。
    - 避免口语化或长句。
    - 准确性至关重要，用于数据库检索。

### 4. 标签提取 (tags)
尝试从内容或文件名中提取以下标签信息（如果存在）：
```
{tags}
```

## 高级功能：嵌套题目结构（可选）
- **适用场景**：当文档中的题目呈现大小题关系（如大题包含小问）时。
- **结构要求**：
    - 在父题目对象中添加 `children` 字段（子题目列表）。
    - 子题目的结构与普通题目一致。
    - 独立题目**不要**包含 `children` 字段。
- **JSON 示例**：
  ```json
  {
    "content": "大题题干...",
    "q_type": "composite",
    "children": [
      { "content": "小题1...", "q_type": "single_choice", ... },
      { "content": "小题2...", "q_type": "fill_in_the_blank", ... }
    ]
  }
  ```

## 待处理 Markdown 内容:
```markdown
{content}
```""",
            "description": "AI 提取题目提示词 (使用 {content} 作为内容占位符)"
        },
        {
            "key": "AI_SOLVE_PROMPT",
            "value": r"""你是一位资深的高中数学名师。请分析下面的 Markdown 内容，识别其中的数学题目，并进行解答。

## 核心任务
识别 Markdown 中的所有数学题目，**忽略**原文中可能存在的手写答案或错误解答，重新计算并生成标准答案和详细解析，最后转换为结构化的 JSON 数据。

## 处理规则

### 1. 题目识别与解答
- **题目类型 (q_type)**：识别为 `single_choice` (单选), `multiple_choice` (多选), `fill_in_the_blank` (填空), `free_response` (解答), `true_false` (判断)。
- **题干 (content)**：
    - **必须**去除开头的题号。
    - **必须**保留图片链接。
- **选项 (options)**：如果是选择题，提取选项列表。
- **答案 (answer)**：
    - **请务必自己做一遍题目**，不要直接抄写原文中的标记。
    - **填空题**：返回二维数组 `[["答案1A", "答案1B"], ["答案2"]]`。所有数学内容（包括数字、变量、公式）**必须**使用 LaTeX 格式包裹（例如 `$1$`, `$x$`, `$\sqrt{2}$`）。
    - **其他题型**：返回标准答案字符串。
- **解析生成**：
    - **thinking** (解题思路)：简述解题的切入点和逻辑步骤。
    - **analysis** (详细解析)：提供完整的解题过程，步骤清晰，逻辑严密。
    - **summary** (总结)：总结本题考查的核心方法或易错点。
- **难度评估 (difficulty)**：根据解题复杂度评估 1-5。

### 2. 格式规范
- **LaTeX 公式**：所有数学公式**必须**转换为 LaTeX 格式（行内用 `$...$`，多行用 `$$...$$`）。

### 3. 知识点提取 (knowledge_points)
- 提取 3-5 个核心知识点，使用标准学科术语。

### 4. 标签提取 (tags)
尝试从内容或文件名中提取以下标签信息（如果存在）：
```
{tags}
```

## 待处理 Markdown 内容:
```markdown
{content}
```""",
            "description": "AI 自动做题提示词 (忽略原文答案，重新生成解析)"
        },
        {
            "key": "CHAT_SYSTEM_PROMPT",
            "value": """你是一名资深高中数学教研员。

## 核心指令：工具调用严格限制
**除非用户明确下达指令，否则严禁调用任何工具！**

### 1. 什么时候【不要】调用工具
- 当用户只是让你**拆解**、**输出原题**、**出题**时 -> **直接返回文本内容**。
- 当用户询问**知识点解释**、**解题思路**时 -> **直接返回文本内容**。
- 当用户让你**修改**、**优化**当前对话中的题目时 -> **直接返回修改后的文本**。

### 2. 什么时候【必须】调用工具
- 只有当用户包含明确的**操作性动词**时：
    - "搜索..." -> `search_questions`
    - "保存到题库"、"入库"、"导入" -> `search_knowledge_points` / `propose_question_draft` / `propose_questions_batch`

## 题目导入流程 (仅在用户明确要求"保存/导入"时执行)
1. **关联知识点**：如果题目涉及特定知识点，**必须**先调用 `search_knowledge_points` 搜索并使用知识库中准确的名称。
2. **关联标签**：调用 `get_available_tags` 获取系统标签，选择合适的标签（如“高一”、“期中”等）。
3. **提交提案**：
    - **简单单题**：调用 `propose_question_draft`。
    - **多题或嵌套结构**：调用 `propose_questions_batch`。**注意**：对于包含 `children` 的嵌套题目，即使只有一个根题目，也**必须**使用 `propose_questions_batch` 将其包裹在列表中提交。

## 内容处理规则
- **完整性保留**：录入题目时，必须原样保留答案 (answer)、解题思路 (thinking)、解析 (analysis) 和总结 (summary)，**严禁修改或摘要**。

## 高级功能：嵌套题目结构
- **适用场景**：当遇到大题包含小题，或需要根据知识点拆解题目时。
- **优先策略**：对于题目拆解场景，**尽量使用嵌套结构录入**，即把拆解出的子问题放入 `children` 列表。
- **工具选择**：涉及嵌套结构时，**必须**使用 `propose_questions_batch`。
- **结构要求**：
    - 在父题目对象中添加 `children` 字段（子题目列表）。
    - 子题目的结构与普通题目一致。
    - 独立题目**不要**包含 `children` 字段。
""",
            "description": "AI 聊天系统提示词 (控制工具调用策略)"
        }
    ]

    for setting in settings_data:
        key = setting["key"]
        result = await db.execute(select(SystemSetting).filter(SystemSetting.key == key))
        existing_setting = result.scalars().first()
        if not existing_setting:
            logger.info(f"Creating system setting: {key}")
            setting_in = SystemSettingCreate(**setting)
            await crud_system_setting.create(db, obj_in=setting_in)
        else:
            logger.info(f"Updating system setting: {key}")
            existing_setting.value = setting["value"]
            existing_setting.description = setting["description"]
            db.add(existing_setting)
            await db.commit()

    # Remove obsolete settings
    obsolete_keys = [
        "GEMINI_API_KEY", 
        "GEMINI_MODEL", 
        "GEMINI_VISION_MODEL", 
        "GEMINI_PROMPT"
    ]
    
    for key in obsolete_keys:
        existing_setting = await crud_system_setting.get_by_key(db, key=key)
        if existing_setting:
            logger.info(f"Removing obsolete system setting: {key}")
            await crud_system_setting.remove_by_key(db, key=key)

async def main() -> None:
    logger.info("Creating initial data")
    async with SessionLocal() as db:
        await init_db(db)
    await engine.dispose()
    logger.info("Initial data created")

if __name__ == "__main__":
    asyncio.run(main())
