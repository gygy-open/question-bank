"""标签精准解析的整卷结构(outline)产出。

回归重点:改造前大题标题与首题之前的说明文字会被丢弃(仅留一条 warning),
导致"导入同时保存为稿件"无法还原原卷版面。此处锁定它们不再丢失。
"""
from app.services.importing.contracts import (
    OUTLINE_HEADING,
    OUTLINE_QUESTION_REF,
    OUTLINE_RICH_TEXT,
)
from app.services.structured_parser import parse_structured


def _kinds(outline):
    return [item["kind"] for item in outline]


def test_section_headings_and_notes_enter_outline():
    text = (
        "高一年级第一次周测\n"
        "考试时间 120 分钟，满分 150 分。\n"
        "一、单选题\n"
        "1.【题目】1 + 1 = ?\n"
        "【选项】A. 1 B. 2\n"
        "【答案】B\n"
        "二、填空题\n"
        "本大题共 1 小题。\n"
        "2.【题目】2 + 2 = \\_\\_\\_\n"
        "【答案】4"
    )

    result = parse_structured(text)
    outline = result.paper["outline"]

    assert result.paper["suggested_title"] == "高一年级第一次周测"
    assert _kinds(outline) == [
        OUTLINE_RICH_TEXT,      # 考试说明
        OUTLINE_HEADING,        # 一、单选题
        OUTLINE_QUESTION_REF,
        OUTLINE_HEADING,        # 二、填空题
        OUTLINE_RICH_TEXT,      # 大题说明
        OUTLINE_QUESTION_REF,
    ]
    assert outline[0]["markdown"] == "考试时间 120 分钟，满分 150 分。"
    assert outline[1]["text"] == "一、单选题"
    assert outline[4]["markdown"] == "本大题共 1 小题。"


def test_question_refs_point_at_question_temp_ids_in_order():
    text = (
        "【题目】第一题\n【答案】A\n"
        "【题目】第二题\n【答案】B"
    )

    result = parse_structured(text)
    refs = [i for i in result.paper["outline"] if i["kind"] == OUTLINE_QUESTION_REF]

    assert [q["id"] for q in result.questions] == [r["temp_id"] for r in refs]
    assert all(r["temp_id"] for r in refs)


def test_original_question_numbers_are_captured():
    text = (
        "3.【题目】标签前带题号\n【答案】A\n"
        "【题目】12. 正文里带题号\n【答案】B"
    )

    result = parse_structured(text)
    refs = [i for i in result.paper["outline"] if i["kind"] == OUTLINE_QUESTION_REF]

    assert [r["number"] for r in refs] == ["3", "12"]


def test_heading_between_questions_does_not_swallow_following_question():
    text = (
        "11.【题目】前一题（ ）\n"
        "【选项】A. 甲 B. 乙\n"
        "【题型】多选\n"
        "**三、填空题**\n"
        "12.【题目】后一题\n"
        "【答案】5"
    )

    result = parse_structured(text)

    assert [q["content"] for q in result.questions] == ["前一题（ ）", "后一题"]
    assert result.questions[0]["q_type"] == "multiple_choice"
    assert _kinds(result.paper["outline"]) == [
        OUTLINE_QUESTION_REF,
        OUTLINE_HEADING,
        OUTLINE_QUESTION_REF,
    ]


def test_empty_input_has_no_questions_and_empty_outline():
    result = parse_structured("")

    assert result.questions == []
    assert result.paper["outline"] == []
    assert result.paper["suggested_title"] is None
