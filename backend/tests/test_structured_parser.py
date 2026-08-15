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
