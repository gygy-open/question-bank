"""答案表沿“题号”行折成多块时的回填。

长卷的参考答案表常被排成多块，每块只有几列宽：

    | 题号 | 1 | 2 | 3 |
    | 答案 | A | B | A |
    | 题号 | 4 | 5 | 6 |
    | 答案 | B | A | B |

旧实现读到第一块答案行就 return，第二块之后的题号全部丢答案，且每道题只报一条
泛化的“选择题缺少答案”，看不出真正原因是答案表没读完。
"""
from app.services.structured_parser import parse_structured


def _paper(count: int) -> str:
    return "".join(f"{i}.【题目】第{i}题\n【选项】A. 甲 B. 乙\n" for i in range(1, count + 1))


def test_wrapped_answer_table_backfills_every_block():
    text = (
        _paper(6)
        + "【答案区】\n"
        "| 题号 | 1 | 2 | 3 |\n"
        "| --- | --- | --- | --- |\n"
        "| 答案 | A | B | A |\n"
        "| 题号 | 4 | 5 | 6 |\n"
        "| --- | --- | --- | --- |\n"
        "| 答案 | B | A | B |\n"
    )
    result = parse_structured(text)
    assert [q["answer"] for q in result.questions] == ["A", "B", "A", "B", "A", "B"]
    assert all(q["warnings"] == [] for q in result.questions)


def test_three_wrapped_blocks():
    text = (
        _paper(3)
        + "【答案区】\n"
        "| 题号 | 1 |\n| --- | --- |\n| 答案 | B |\n"
        "| 题号 | 2 |\n| --- | --- |\n| 答案 | A |\n"
        "| 题号 | 3 |\n| --- | --- |\n| 答案 | B |\n"
    )
    result = parse_structured(text)
    assert [q["answer"] for q in result.questions] == ["B", "A", "B"]


def test_single_block_unchanged():
    text = (
        _paper(2)
        + "【答案区】\n"
        "| 题号 | 1 | 2 |\n| --- | --- | --- |\n| 答案 | B | A |\n"
    )
    result = parse_structured(text)
    assert [q["answer"] for q in result.questions] == ["B", "A"]


def test_wrapped_table_keeps_latex_answers():
    text = (
        _paper(2)
        + "【答案区】\n"
        "| 题号 | 1 |\n| --- | --- |\n| 答案 | $\\dfrac{1}{2}$ |\n"
        "| 题号 | 2 |\n| --- | --- |\n| 答案 | $x^2+1$ |\n"
    )
    result = parse_structured(text)
    answers = [q["answer"] for q in result.questions]
    assert "dfrac{1}{2}" in answers[0]
    assert "x^2+1" in answers[1]


def test_table_without_number_header_is_not_an_answer_table():
    text = _paper(1) + "【答案区】\n| 名称 | 值 |\n| --- | --- |\n| 甲 | B |\n"
    result = parse_structured(text)
    assert result.questions[0]["answer"] in ("", None)


def test_analysis_table_does_not_fill_blank_answer_cells():
    # 答案表里第 3 题留空;解析里的取值表不能被对齐到“题号”表头上当成答案。
    text = (
        _paper(2)
        + "3.【题目】填空\n"
        + "【答案区】\n"
        "| 题号 | 1 | 2 | 3 |\n| --- | --- | --- | --- |\n| 答案 | A | B |  |\n"
        "\n2. 解析:列表如下\n"
        "| x | 0 | 1 | 2 |\n| --- | --- | --- | --- |\n| y | 1 | 3 | 5 |\n"
    )
    result = parse_structured(text)
    assert [q["answer"] for q in result.questions][:2] == ["A", "B"]
    assert result.questions[2]["answer"] in ("", None)
