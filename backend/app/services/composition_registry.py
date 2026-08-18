"""comp_type 注册表: 数据驱动的组稿版式定义.

在此集中定义各类组合文档的默认元数据。取消了 kind 的强验证，仅依靠业务定义。
"""
from typing import Dict


class CompTypeSpec:
    def __init__(
        self,
        comp_type: str,
        label: str,
        default_export: Dict | None = None,
    ):
        self.comp_type = comp_type
        self.label = label
        self.default_export = default_export or {}


COMPOSITION_TYPES: Dict[str, CompTypeSpec] = {
    "question_group": CompTypeSpec(
        "question_group", "教学模块",
        default_export={"content_position": "after_question"},
    ),
    "exam_paper": CompTypeSpec(
        "exam_paper", "试卷",
        default_export={"content_position": "end_of_paper"},
    ),
    "study_guide": CompTypeSpec(
        "study_guide", "学案",
        default_export={"content_position": "after_question"},
    ),
    "handout": CompTypeSpec(
        "handout", "讲义",
        default_export={"content_position": "after_question"},
    ),
}
