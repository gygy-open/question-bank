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
    desc_text = f"（本学科说明：{desc}）" if desc else ""
    return (
        template
        .replace(SUBJECT_NAME_PLACEHOLDER, name)
        .replace(SUBJECT_DESCRIPTION_PLACEHOLDER, desc_text)
    )
