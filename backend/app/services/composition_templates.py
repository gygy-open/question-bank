"""系统预置模板 (硬编码, 不入库, 不可增删改).

模板只负责"新建时的初始填充": 提供默认文档级显示策略 (meta_data.display) 与初始块骨架。
用户自定义模板另存为 is_template=True 的组稿, 按 subject + scope 隔离, 不在此文件。
"""
from typing import Dict, List, Any

from app.services.composition_display import make_display, REGION_INLINE, REGION_APPENDIX, REGION_HIDDEN


class SystemTemplate:
    def __init__(
        self,
        key: str,
        label: str,
        icon: str,
        description: str,
        meta_data: Dict[str, Any],
        blocks: List[Dict[str, Any]],
    ):
        self.key = key
        self.label = label
        self.icon = icon
        self.description = description
        self.meta_data = meta_data
        self.blocks = blocks


SYSTEM_TEMPLATES: Dict[str, SystemTemplate] = {
    "question_group": SystemTemplate(
        key="question_group",
        label="教学模块",
        icon="Blocks",
        description="围绕一个教学方法沉淀讲解与配套题目, 可被克隆到其他文档",
        meta_data={"display": make_display({
            "answer": REGION_INLINE, "analysis": REGION_INLINE, "explanation": REGION_INLINE,
            "summary": REGION_HIDDEN, "source": REGION_HIDDEN,
        })},
        blocks=[],
    ),
    "exam_paper": SystemTemplate(
        key="exam_paper",
        label="试卷",
        icon="FileText",
        description="标准试卷, 答案与解析默认收纳到卷末",
        meta_data={"display": make_display({
            "answer": REGION_APPENDIX, "analysis": REGION_HIDDEN, "explanation": REGION_APPENDIX,
            "summary": REGION_HIDDEN, "source": REGION_HIDDEN,
        })},
        blocks=[],
    ),
    "study_guide": SystemTemplate(
        key="study_guide",
        label="学案",
        icon="BookOpen",
        description="讲练结合的学案, 答案与解析随题展示",
        meta_data={"display": make_display({
            "answer": REGION_INLINE, "analysis": REGION_INLINE, "explanation": REGION_INLINE,
            "summary": REGION_HIDDEN, "source": REGION_HIDDEN,
        })},
        blocks=[],
    ),
    "handout": SystemTemplate(
        key="handout",
        label="讲义",
        icon="ScrollText",
        description="图文混排的讲义, 答案与解析随题展示",
        meta_data={"display": make_display({
            "answer": REGION_INLINE, "analysis": REGION_INLINE, "explanation": REGION_INLINE,
            "summary": REGION_HIDDEN, "source": REGION_HIDDEN,
        })},
        blocks=[],
    ),
}
