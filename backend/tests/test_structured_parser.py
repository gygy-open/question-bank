import json

from app.services.question_legacy_adapter import adapt_legacy_question
from app.services.structured_parser import parse_structured


def test_single_choice_full_block():
    text = (
        "【题目】1 + 1 = ?\n"
        "【选项】A. 1 B. 2 C. 3 D. 4\n"
        "【答案】B\n"
        "【解析】显然\n"
        "【难度】简单"
    )
    result = parse_structured(text)

    assert len(result) == 1
    q = result[0]
    assert q["content"] == "1 + 1 = ?"
    assert q["q_type"] == "single_choice"
    assert q["answer"] == "B"
    assert q["analysis"] == "显然"
    assert q["difficulty"] == 1
    assert q["options"] == ["A. 1", "B. 2", "C. 3", "D. 4"]
    assert q["warnings"] == []


def test_pandoc_blockquote_options_are_not_appended_to_content():
    text = (
        "1．【题目】集合题（ ）\n"
        "> 【选项】A．12 B．11\n"
        "> C．8 D．6"
    )

    q = parse_structured(text)[0]

    assert q["content"] == "集合题（ ）"
    assert q["q_type"] == "single_choice"
    assert q["options"] == ["A. 12", "B. 11", "C. 8", "D. 6"]


def test_explicit_multiple_choice_survives_following_section_heading():
    text = (
        "11．【题目】已知函数 f(x)，则（ ）\n"
        "> 【选项】A．f(x) 是周期函数\n"
        "> B．点 (4,0) 是对称中心\n"
        "> C．f(2025) + f(2026) = 0\n"
        "> D．函数有 4 个零点\n"
        "> 【题型】多选\n"
        "**三、填空题**\n"
        "12．【题目】下一题"
    )

    q = parse_structured(text)[0]

    assert q["q_type"] == "multiple_choice"
    assert q["options"] == [
        "A. f(x) 是周期函数",
        "B. 点 (4,0) 是对称中心",
        "C. f(2025) + f(2026) = 0",
        "D. 函数有 4 个零点",
    ]


def test_multiple_questions_split_on_content_tag():
    text = (
        "【题目】第一题\n【答案】A\n"
        "【题目】第二题\n【答案】B"
    )
    result = parse_structured(text)

    assert [q["content"] for q in result] == ["第一题", "第二题"]


def test_multiple_choice_inferred_from_answer():
    text = (
        "【题目】选出正确项\n"
        "【选项】A. 甲 B. 乙 C. 丙\n"
        "【答案】AC"
    )
    q = parse_structured(text)[0]

    assert q["q_type"] == "multiple_choice"


def test_numeric_difficulty_is_clamped():
    text = "【题目】难题\n【难度】9"
    q = parse_structured(text)[0]

    assert q["difficulty"] == 5


def test_markdown_escaped_underscores_infer_fill_in_the_blank():
    text = "12．【题目】三角形的面积是\\_\\_\\_\\_\\_。"

    q = parse_structured(text)[0]

    assert q["q_type"] == "fill_in_the_blank"


def test_fill_in_the_blank_answer_is_importable_and_detailed_analysis_is_separate():
    text = (
        "【题目】过坐标原点且与曲线$y = - x\\ln x - 1$相切的直线方程为\\_\\_\\_。\n"
        "【答案】$x + y = 0$/$y = - x$"
        "【详解】设切线的切点为$x_0$，可得$x_0 = 1$。"
    )

    q = parse_structured(text)[0]

    assert json.loads(q["answer"]) == [["$x + y = 0$/$y = - x$"]]
    assert q["analysis"] == "设切线的切点为$x_0$，可得$x_0 = 1$。"
    # v2 分支下走 adapter 归一化(而非旧的 QuestionCreate 直收 legacy 字符串)。
    v2 = adapt_legacy_question(
        q_type=q["q_type"],
        status="pending",
        content=q["content"],
        answer=q["answer"],
        analysis=q.get("analysis"),
    )
    assert v2["answer"]["kind"] == "fill_in_the_blank"


def test_bold_answer_is_not_contaminated_by_following_section_heading():
    text = (
        "【题目】下列结论正确的是（ ）\n"
        "【选项】A. 甲 B. 乙 C. 丙 D. 丁\n"
        "**【答案】D**\n"
        "**二、多选题（本题共3小题，每小题6分，共**"
    )

    q = parse_structured(text)[0]

    assert q["answer"] == "D"
    assert q["q_type"] == "single_choice"
    assert q["warnings"] == []


def test_choice_warns_when_answer_out_of_range():
    text = (
        "【题目】范围外答案\n"
        "【选项】A. 甲 B. 乙\n"
        "【答案】D"
    )
    q = parse_structured(text)[0]

    assert any("超出选项范围" in w for w in q["warnings"])


def test_empty_input_returns_empty_list():
    assert parse_structured("") == []
