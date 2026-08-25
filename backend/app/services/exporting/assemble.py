"""PaperAssembler:把 Paper 的有序题目 + 分节 + 导出选项拍平成 ExportDoc。

纯逻辑,零格式依赖:分节、连续编号、答案/解析的位置(内联 / 末尾答案册 / 隐藏)
与 include_* 过滤都在此完成,渲染器只消费结果。
"""

from __future__ import annotations

from typing import Any, Optional

from app.models.question import Question, QuestionType
from app.services.exporting.contracts import (
    ExportDoc,
    ExportOption,
    ExportOptions,
    ExportQuestion,
    ExportSection,
)
from app.services.question_content import parse_json_field


def _q_type_value(q_type: Any) -> str:
    return q_type.value if hasattr(q_type, "value") else str(q_type)


def _parse_options(raw: Any) -> list[ExportOption]:
    opts = parse_json_field(raw)
    result: list[ExportOption] = []
    if isinstance(opts, list):
        for idx, opt in enumerate(opts):
            if isinstance(opt, dict):
                result.append(
                    ExportOption(
                        id=str(opt.get("id", "")),
                        label=str(opt.get("label", "") or chr(65 + idx)),
                        content=opt.get("content"),
                    )
                )
            else:
                result.append(ExportOption(id="", label=chr(65 + idx), content=None))
    return result


class PaperAssembler:
    def __init__(self, options: ExportOptions):
        self.opts = options

    def assemble(
        self,
        questions: list[Question],
        section_titles: Optional[list[Optional[str]]] = None,
    ) -> ExportDoc:
        raw_sections = self._split_sections(questions, section_titles)

        inline_details = not self.opts.details_at_end and not self.opts.hidden_details

        number = 1
        main: list[ExportSection] = []
        numbering: list[list[int]] = []  # 记录每节题号,供答案册复用
        for sec in raw_sections:
            eqs: list[ExportQuestion] = []
            nums: list[int] = []
            for q in sec["questions"]:
                eqs.append(self._build_q(q, number, show_details=inline_details))
                nums.append(number)
                number += 1
            main.append(ExportSection(title=sec["title"], questions=eqs))
            numbering.append(nums)

        appendix: list[ExportSection] = []
        if self.opts.details_at_end and not self.opts.hidden_details:
            for sec, nums in zip(raw_sections, numbering):
                eqs = [
                    self._build_q(q, n, show_details=True)
                    for q, n in zip(sec["questions"], nums)
                ]
                appendix.append(ExportSection(title=sec["title"], questions=eqs))

        return ExportDoc(
            title=self.opts.title,
            sections=main,
            appendix=appendix,
            has_appendix=bool(appendix),
        )

    def _build_q(self, q: Question, number: int, show_details: bool) -> ExportQuestion:
        o = self.opts
        return ExportQuestion(
            number=number,
            q_type=_q_type_value(q.q_type),
            stem=parse_json_field(q.content),
            options=_parse_options(q.options),
            answer=parse_json_field(q.answer) if (show_details and o.include_answer) else None,
            thinking=parse_json_field(q.thinking) if (show_details and o.include_analysis) else None,
            analysis=parse_json_field(q.analysis) if (show_details and o.include_explanation) else None,
            summary=parse_json_field(q.summary) if (show_details and o.include_summary) else None,
            source=q.source if (show_details and o.include_source) else None,
            reserve_space=_q_type_value(q.q_type) == QuestionType.FREE_RESPONSE.value,
        )

    def _split_sections(
        self,
        questions: list[Question],
        section_titles: Optional[list[Optional[str]]],
    ) -> list[dict[str, Any]]:
        """按手动 section_title 切分;无标题合并为单一无标题节,保持提交顺序。"""
        titles = section_titles or [None] * len(questions)
        sections: list[dict[str, Any]] = []
        current: dict[str, Any] = {"title": None, "questions": []}
        started = False
        for q, raw_title in zip(questions, titles):
            title = (raw_title or "").strip() or None
            if title:
                if started:
                    sections.append(current)
                current = {"title": title, "questions": [q]}
                started = True
            else:
                current["questions"].append(q)
                started = True
        if current["questions"]:
            sections.append(current)
        return sections
