import json

from app.services.importing.contracts import OUTLINE_HEADING
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

    assert len(result.questions) == 1
    q = result.questions[0]
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

    q = parse_structured(text).questions[0]

    assert q["content"] == "集合题（ ）"
    assert q["q_type"] == "single_choice"
    assert q["options"] == ["A. 12", "B. 11", "C. 8", "D. 6"]


def test_pandoc_escaped_question_number_before_tag_is_recognized():
    result = parse_structured(
        "1\\. 【题目】第一道题\n"
        "【答案】甲\n"
        "2\\. 【题目】第二道题\n"
        "【答案】乙"
    )

    assert [question["content"] for question in result.questions] == [
        "第一道题",
        "第二道题",
    ]
    assert [question["source_number"] for question in result.questions] == ["1", "2"]


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

    q = parse_structured(text).questions[0]

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

    assert [q["content"] for q in result.questions] == ["第一题", "第二题"]


def test_multiple_choice_inferred_from_answer():
    text = (
        "【题目】选出正确项\n"
        "【选项】A. 甲 B. 乙 C. 丙\n"
        "【答案】AC"
    )
    q = parse_structured(text).questions[0]

    assert q["q_type"] == "multiple_choice"


def test_numeric_difficulty_is_clamped():
    text = "【题目】难题\n【难度】9"
    q = parse_structured(text).questions[0]

    assert q["difficulty"] == 5


def test_markdown_escaped_underscores_infer_fill_in_the_blank():
    text = "12．【题目】三角形的面积是\\_\\_\\_\\_\\_。"

    q = parse_structured(text).questions[0]

    assert q["q_type"] == "fill_in_the_blank"


def test_fill_in_the_blank_answer_is_importable_and_detailed_analysis_is_separate():
    text = (
        "【题目】过坐标原点且与曲线$y = - x\\ln x - 1$相切的直线方程为\\_\\_\\_。\n"
        "【答案】$x + y = 0$/$y = - x$"
        "【详解】设切线的切点为$x_0$，可得$x_0 = 1$。"
    )

    q = parse_structured(text).questions[0]

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

    q = parse_structured(text).questions[0]

    assert q["answer"] == "D"
    assert q["q_type"] == "single_choice"
    assert q["warnings"] == []


def test_choice_warns_when_answer_out_of_range():
    text = (
        "【题目】范围外答案\n"
        "【选项】A. 甲 B. 乙\n"
        "【答案】D"
    )
    q = parse_structured(text).questions[0]

    assert any("超出选项范围" in w for w in q["warnings"])


def test_trailing_answer_section_backfills_answer_and_analysis_by_number():
    text = (
        "1.【题目】1+1=?\n"
        "【选项】A. 1 B. 2 C. 3 D. 4\n"
        "2.【题目】3+3=?\n"
        "【选项】A. 5 B. 6 C. 7 D. 8\n"
        "【答案区】\n"
        "| 题号 | 1 | 2 |\n"
        "|:---:|:---:|:---:|\n"
        "| 答案 | B | B |\n"
        "1.因为1+1=2，选B。\n"
        "2.因为3+3=6，选B。"
    )
    result = parse_structured(text)

    q1, q2 = result.questions
    assert q1["answer"] == "B" and q1["analysis"] == "因为1+1=2，选B。"
    assert q2["answer"] == "B" and q2["analysis"] == "因为3+3=6，选B。"
    assert q1["warnings"] == [] and q2["warnings"] == []


def test_answer_table_outline_is_isolated_from_following_analysis_text():
    """表格与解析段落之间的原始空行会在预处理阶段被过滤掉；若把二者拼成一段
    markdown，下游表格解析器会把解析段落也吞成表格的后续行，故必须分开出块。"""
    text = (
        "1.【题目】1+1=?\n"
        "【选项】A. 1 B. 2 C. 3 D. 4\n"
        "【答案区】\n"
        "| 题号 | 1 |\n"
        "|:---:|:---:|\n"
        "| 答案 | B |\n"
        "1.因为1+1=2，选B。"
    )
    result = parse_structured(text)
    rich_text_items = [i for i in result.paper["outline"] if i["kind"] == "rich_text"]

    assert len(rich_text_items) == 2
    assert rich_text_items[0]["markdown"].startswith("| 题号 | 1 |")
    assert "因为1+1=2" not in rich_text_items[0]["markdown"]
    assert rich_text_items[1]["markdown"] == "1.因为1+1=2，选B。"


def test_analysis_paragraph_leading_answer_echo_is_stripped():
    text = (
        "1.【题目】哪些是质数（   ）\n"
        "【选项】A. 1 B. 2 C. 4 D. 5\n"
        "【答案区】\n"
        "| 题号 | 1 |\n"
        "|:---:|:---:|\n"
        "| 答案 | BD |\n"
        "1.BD对于A，1不是质数；对于B，2是质数。"
    )
    q = parse_structured(text).questions[0]

    assert q["answer"] == "BD"
    assert q["analysis"] == "对于A，1不是质数；对于B，2是质数。"


def test_answer_section_explicit_tags_win_for_fill_in_the_blank():
    text = (
        "12.【题目】三角形的面积是\\_\\_\\_\\_\\_。\n"
        "【答案区】\n"
        "12.【答案】$x=1$【解析】设边长为...\n"
    )
    q = parse_structured(text).questions[0]

    assert json.loads(q["answer"]) == [["$x=1$"]]
    assert q["analysis"] == "设边长为..."
    assert q["q_type"] == "fill_in_the_blank"
    assert q["warnings"] == []


def test_explicit_answer_inside_block_wins_over_trailing_answer_section():
    text = (
        "1.【题目】1+1=?\n"
        "【选项】A. 1 B. 2 C. 3 D. 4\n"
        "【答案】A\n"
        "【答案区】\n"
        "| 题号 | 1 |\n"
        "|:---:|:---:|\n"
        "| 答案 | B |"
    )
    q = parse_structured(text).questions[0]

    assert q["answer"] == "A"


def test_answer_section_tag_trailing_other_heading_text_is_recognized():
    text = (
        "1.【题目】1+1=?\n"
        "【选项】A. 1 B. 2 C. 3 D. 4\n"
        "**《小测》参考答案【答案区】**\n"
        "| 题号 | 1 |\n"
        "|:---:|:---:|\n"
        "| 答案 | B |\n"
        "1.因为1+1=2，选B。"
    )
    result = parse_structured(text)

    q = result.questions[0]
    assert q["answer"] == "B"
    assert q["analysis"] == "因为1+1=2，选B。"
    assert any(
        item.get("kind") == OUTLINE_HEADING and item.get("text") == "《小测》参考答案"
        for item in result.paper["outline"]
    )


def test_empty_input_returns_empty_list():
    assert parse_structured("").questions == []
