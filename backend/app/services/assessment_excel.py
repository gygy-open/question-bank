"""Excel transport for assessment gradebooks.

The visible sheet is teacher-facing. A hidden metadata sheet binds the workbook
to one exam and preserves question/result IDs plus optimistic-lock revisions.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from app.models.assessment import ExamSession

SHEET_NAME = "成绩录入"
META_SHEET_NAME = "_meta"
FORMAT_VERSION = 1


@dataclass(frozen=True)
class ImportError:
    row: int
    field: str
    message: str


@dataclass(frozen=True)
class ImportRow:
    excel_row: int
    result_id: int
    expected_revision: int
    scores: Dict[int, Optional[Decimal]]


@dataclass(frozen=True)
class ParsedImport:
    rows: List[ImportRow]
    changed_rows: int
    changed_scores: int
    unchanged_rows: int
    errors: List[ImportError]


def generate_workbook(session: ExamSession) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = SHEET_NAME
    meta = workbook.create_sheet(META_SHEET_NAME)

    questions = list(session.questions)
    participants = list(session.participants)
    headers = ["学号", "姓名"] + [
        f"第 {index} 题（满分 {question.max_score}）"
        for index, question in enumerate(questions, start=1)
    ] + ["总分"]
    sheet.append(headers)

    header_fill = PatternFill("solid", fgColor="2563EB")
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    sheet.freeze_panes = "C2"
    sheet.column_dimensions["A"].width = 18
    sheet.column_dimensions["B"].width = 16
    for column in range(3, len(headers) + 1):
        sheet.column_dimensions[get_column_letter(column)].width = 18

    meta.append(["format_version", FORMAT_VERSION])
    meta.append(["exam_session_id", session.id])
    meta.append(["record_type", "excel_row", "student_no", "result_id", "revision"])

    for excel_row, participant in enumerate(participants, start=2):
        result = participant.result
        scores = {item.exam_question_id: item.score for item in result.score_items}
        values: List[Any] = [participant.student_no, participant.name]
        values.extend(scores.get(question.id) for question in questions)
        total_column = get_column_letter(2 + len(questions) + 1)
        first_score = get_column_letter(3)
        last_score = get_column_letter(2 + len(questions))
        values.append(f'=IF(COUNT({first_score}{excel_row}:{last_score}{excel_row})={len(questions)},SUM({first_score}{excel_row}:{last_score}{excel_row}),"")')
        sheet.append(values)
        meta.append([
            "participant",
            excel_row,
            participant.student_no,
            result.id,
            result.revision,
        ])
        sheet.cell(excel_row, len(headers)).number_format = "0.00"

    meta.append(["questions"])
    meta.append(["column", "exam_question_id", "max_score"])
    for column, question in enumerate(questions, start=3):
        meta.append([column, question.id, str(question.max_score)])

    meta.sheet_state = "hidden"
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def _decimal(value: Any) -> Optional[Decimal]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise InvalidOperation
    return Decimal(str(value).strip())


def parse_workbook(file_bytes: bytes, session: ExamSession) -> ParsedImport:
    try:
        workbook = load_workbook(io.BytesIO(file_bytes), data_only=False)
    except Exception as exc:
        raise ValueError("无法读取 Excel 文件，请使用系统导出的成绩模板") from exc
    if SHEET_NAME not in workbook.sheetnames or META_SHEET_NAME not in workbook.sheetnames:
        raise ValueError("成绩模板缺少必要工作表，请重新导出")

    sheet = workbook[SHEET_NAME]
    meta = workbook[META_SHEET_NAME]
    if meta["A1"].value != "format_version" or meta["B1"].value != FORMAT_VERSION:
        raise ValueError("成绩模板版本不受支持，请重新导出")
    if meta["A2"].value != "exam_session_id" or meta["B2"].value != session.id:
        raise ValueError("成绩文件不属于当前考试")

    questions = list(session.questions)
    question_by_id = {question.id: question for question in questions}
    question_columns: Dict[int, int] = {}
    participant_meta: Dict[int, tuple[str, int, int]] = {}
    section = "participants"
    for values in meta.iter_rows(min_row=4, values_only=True):
        if values[0] == "questions":
            section = "questions_header"
            continue
        if section == "questions_header":
            section = "questions"
            continue
        if section == "participants" and values[0] == "participant":
            participant_meta[int(values[1])] = (
                str(values[2]), int(values[3]), int(values[4])
            )
        elif section == "questions" and values[0] is not None:
            question_columns[int(values[0])] = int(values[1])

    expected_questions = {question.id for question in questions}
    if set(question_columns.values()) != expected_questions:
        raise ValueError("成绩模板题目结构已损坏，请重新导出")

    participants_by_result = {
        participant.result.id: participant for participant in session.participants
    }
    errors: List[ImportError] = []
    rows: List[ImportRow] = []
    changed_rows = 0
    changed_scores = 0

    for excel_row, (student_no, result_id, expected_revision) in participant_meta.items():
        participant = participants_by_result.get(result_id)
        if participant is None or participant.student_no != student_no:
            errors.append(ImportError(excel_row, "学号", "学生不属于当前考试"))
            continue
        if sheet.cell(excel_row, 1).value != student_no:
            errors.append(ImportError(excel_row, "学号", "学号不可修改"))
            continue
        result = participant.result
        if result.revision != expected_revision:
            errors.append(ImportError(excel_row, "revision", "成绩已被修改，请重新导出模板"))
            continue

        existing = {item.exam_question_id: item.score for item in result.score_items}
        parsed_scores: Dict[int, Optional[Decimal]] = {}
        row_changes = 0
        for column, question_id in question_columns.items():
            question = question_by_id[question_id]
            try:
                score = _decimal(sheet.cell(excel_row, column).value)
            except (InvalidOperation, ValueError):
                errors.append(ImportError(excel_row, f"第 {question.position + 1} 题", "分值格式无效"))
                continue
            if score is not None:
                exponent = score.as_tuple().exponent
                if score < 0 or score > question.max_score:
                    errors.append(
                        ImportError(
                            excel_row,
                            f"第 {question.position + 1} 题",
                            f"分值必须在 0 到 {question.max_score} 之间",
                        )
                    )
                    continue
                if isinstance(exponent, int) and exponent < -2:
                    errors.append(ImportError(excel_row, f"第 {question.position + 1} 题", "分值精度最多两位小数"))
                    continue
            parsed_scores[question_id] = score
            if existing.get(question_id) != score:
                row_changes += 1

        rows.append(ImportRow(excel_row, result_id, expected_revision, parsed_scores))
        if row_changes:
            changed_rows += 1
            changed_scores += row_changes

    if len(participant_meta) != len(session.participants):
        errors.append(ImportError(0, "名单", "成绩模板的学生名单不完整"))

    return ParsedImport(
        rows=rows,
        changed_rows=changed_rows,
        changed_scores=changed_scores,
        unchanged_rows=len(session.participants) - changed_rows,
        errors=errors,
    )