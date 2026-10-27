from typing import Optional

from app.models.subject import Subject

SUBJECT_NAME_PLACEHOLDER = "{subject_name}"
SUBJECT_DESCRIPTION_PLACEHOLDER = "{subject_description}"


def render_subject_prompt(template: Optional[str], subject: Optional[Subject]) -> Optional[str]:
    """Fill {subject_name}/{subject_description} so one generic template fits any subject."""
    if not template:
        return template
    name = subject.name if subject and subject.name else ""
    desc = subject.description if subject and subject.description else ""
    desc_text = f" (Subject notes: {desc})" if desc else ""
    if not name:
        # 默认提示词里占位符后总跟一个空格；学科为空时一并去掉，避免出现双空格。
        template = template.replace(f"{SUBJECT_NAME_PLACEHOLDER} ", "")
    return (
        template
        .replace(SUBJECT_NAME_PLACEHOLDER, name)
        .replace(SUBJECT_DESCRIPTION_PLACEHOLDER, desc_text)
    )


OUTPUT_LANGUAGE_PLACEHOLDER = "{output_language}"

# 提示词正文只维护一份;输出语言用一段指令补充,不为每种界面语言复制整套提示词。
# 抽取不跟界面语言走:英文界面的用户完全可能导入中文试卷,翻译会破坏题目数据。
_LANGUAGE_DIRECTIVES = {
    "chat": (
        "## Output language\n"
        "Reply to the user in {language}. Keep quoted source text, question content, "
        "formulas and code in their original language; do not translate them."
    ),
    "solve": (
        "## Output language\n"
        "Write explanations, analysis and answers in {language}. "
        "Keep the question stem and options exactly as in the source; do not translate them."
    ),
    "extract": (
        "## Output language\n"
        "Keep all extracted content in the language of the source document; never translate it."
    ),
}


def render_language_directive(kind: str, locale: Optional[str] = None) -> str:
    from app.core.locale import language_name

    return _LANGUAGE_DIRECTIVES[kind].format(language=language_name(locale))


def apply_output_language(prompt: str, kind: str, locale: Optional[str] = None) -> str:
    """填充 {output_language};模板(如用户的学科覆盖)没有占位符时追加到末尾。"""
    directive = render_language_directive(kind, locale)
    if OUTPUT_LANGUAGE_PLACEHOLDER in prompt:
        return prompt.replace(OUTPUT_LANGUAGE_PLACEHOLDER, directive)
    return f"{prompt}\n\n{directive}"
