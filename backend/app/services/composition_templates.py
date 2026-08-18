"""系统预置模板 (硬编码, 不入库, 不可增删改).

模板只负责"新建时的初始填充": 提供默认文档级设置 (meta_data) 与初始块骨架。
用户自定义模板另存为 is_template=True 的组稿, 按 subject + scope 隔离, 不在此文件。
"""
from typing import Dict, List, Any


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


# answer_position: after_question / end_of_paper / hidden
SYSTEM_TEMPLATES: Dict[str, SystemTemplate] = {
    "question_group": SystemTemplate(
        key="question_group",
        label="教学模块",
        icon="Blocks",
        description="围绕一个教学方法沉淀讲解与配套题目, 可被克隆到其他文档",
        meta_data={"show_answers": True, "answer_position": "after_question"},
        blocks=[],
    ),
    "exam_paper": SystemTemplate(
        key="exam_paper",
        label="试卷",
        icon="FileText",
        description="标准试卷, 答案默认收纳到卷末",
        meta_data={"show_answers": False, "answer_position": "end_of_paper"},
        blocks=[],
    ),
    "study_guide": SystemTemplate(
        key="study_guide",
        label="学案",
        icon="BookOpen",
        description="讲练结合的学案, 答案随题展示",
        meta_data={"show_answers": True, "answer_position": "after_question"},
        blocks=[],
    ),
    "handout": SystemTemplate(
        key="handout",
        label="讲义",
        icon="ScrollText",
        description="图文混排的讲义, 答案随题展示",
        meta_data={"show_answers": True, "answer_position": "after_question"},
        blocks=[],
    ),
}
