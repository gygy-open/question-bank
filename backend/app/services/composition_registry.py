"""comp_type 注册表: 数据驱动的组稿版式定义.

kind(component/deliverable) 由 comp_type 派生; 新增版式(如专题讲义)只需在此加一条,
无需改动数据库 schema.
"""
from typing import Dict, List

from app.models.composition import CompositionKind


class CompTypeSpec:
    def __init__(
        self,
        comp_type: str,
        kind: CompositionKind,
        label: str,
        default_export: Dict | None = None,
    ):
        self.comp_type = comp_type
        self.kind = kind
        self.label = label
        self.default_export = default_export or {}


COMPOSITION_TYPES: Dict[str, CompTypeSpec] = {
    "question_group": CompTypeSpec(
        "question_group", CompositionKind.COMPONENT, "题组",
        default_export={"content_position": "after_question"},
    ),
    "exam_paper": CompTypeSpec(
        "exam_paper", CompositionKind.DELIVERABLE, "试卷",
        default_export={"content_position": "end_of_paper"},
    ),
    "study_guide": CompTypeSpec(
        "study_guide", CompositionKind.DELIVERABLE, "学案",
        default_export={"content_position": "after_question"},
    ),
    "handout": CompTypeSpec(
        "handout", CompositionKind.DELIVERABLE, "专题讲义",
        default_export={"content_position": "after_question"},
    ),
}


def kind_for(comp_type: str) -> CompositionKind:
    spec = COMPOSITION_TYPES.get(comp_type)
    if not spec:
        raise ValueError(f"Unknown comp_type: {comp_type}")
    return spec.kind


def is_component(comp_type: str) -> bool:
    return kind_for(comp_type) == CompositionKind.COMPONENT


def comp_types_for_kind(kind: CompositionKind) -> List[str]:
    return [ct for ct, spec in COMPOSITION_TYPES.items() if spec.kind == kind]
