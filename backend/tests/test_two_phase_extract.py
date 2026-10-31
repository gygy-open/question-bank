"""两阶段抽取的纯函数测试（不调用 AI，不访问数据库）。

覆盖切段、选项剥离、内联答案剥离、题型推断、答案合并优先级。
"""
from __future__ import annotations

from app.services.importing.two_phase import (
    build_questions,
    split_segments,
)

# 注意：原文题号每章从 1 重开，所以题号值会重复；切段只依赖出现顺序。
SAMPLE = """## 知识点 1 一元二次方程

1. 下列方程中是一元二次方程的有( B )

A. $x^2=0$ B. $2x(x+2)=2x^2-3$ C. $\\frac{1}{x}=4$ D. $x+y=1$

2. 方程 ${x}^2 - 1 = {3x}$ 的常数项是 -1，则二次项和一次项分别是（B）

A. $x^2$ 和 $3x$ B. $x^2$ 和 $-3x$ C. 1 和 -3 D. 1 和 3

## 知识点 2 解方程

1. 若 $x^2=16$，则 $x=$ ____．

2. 如图，正方形 $ABCD$ 的边长为 4，求 $DF$ 的最小值。

![a.jpg](images/a.jpg)
"""


def test_split_keeps_duplicate_numbers_by_order():
    """题号重复（每章从 1 重开）不影响切段：786 个题号就该切 786 段。"""
    segs = split_segments(SAMPLE)
    assert len(segs) == 4
    # 第一段和第三段原文题号都是 1，但它们是不同的题
    assert segs[0][0].startswith("下列方程")
    assert segs[2][0].startswith("若 $x^2=16$")


def test_split_strips_leading_number_only():
    segs = split_segments(SAMPLE)
    for block in segs:
        assert not block[0].lstrip().startswith(("1.", "2."))


def test_options_split_from_same_line_block():
    """A. … B. … C. … D. … 写在同两行里也要拆成 4 项。"""
    qs = build_questions(split_segments(SAMPLE), [])
    first = qs[0]
    assert len(first["options"]) == 4
    assert first["options"][0].startswith("A.")
    assert first["options"][3].startswith("D.")
    assert "A. $x^2=0$" not in first["content"]


def test_inline_answer_stripped_from_stem():
    """题干末尾的 ( B ) / （B） 要剥成 answer，并从题干里删掉。"""
    qs = build_questions(split_segments(SAMPLE), [])
    assert qs[0]["answer"] == "B"
    assert "( B )" not in qs[0]["content"]
    assert "（B）" not in qs[1]["content"]
    assert qs[1]["answer"] == "B"


def test_q_type_inferred_from_structure():
    """题型由结构判断：有选项→选择题；有 ___ →填空；否则解答。"""
    qs = build_questions(split_segments(SAMPLE), [])
    assert qs[0]["q_type"] == "single_choice"
    assert qs[2]["q_type"] == "fill_in_the_blank"
    assert qs[3]["q_type"] == "free_response"


def test_image_reference_preserved_in_stem():
    """题干里的图片引用必须原样保留。"""
    qs = build_questions(split_segments(SAMPLE), [])
    assert "![a.jpg](images/a.jpg)" in qs[3]["content"]


def test_script_answer_wins_over_ai_answer():
    """脚本剥出的答案优先；脚本没有时才用 AI 的 ord 对齐答案。"""
    segs = split_segments(SAMPLE)
    ai = [
        {"ord": 1, "answer": "A"},   # 脚本已剥出 B，应保留 B
        {"ord": 3, "answer": "4"},   # 脚本剥不到，用 AI 的 4
    ]
    qs = build_questions(segs, ai)
    assert qs[0]["answer"] == "B"
    assert qs[2]["answer"] == "4"
    assert qs[1]["answer"] == "B"   # AI 没给，脚本剥出


def test_ai_ord_is_sequential_not_source_number():
    """AI 的 ord 是出现顺序（第几题），不是原文题号。

    原文第 3 段题号又是 1，若按题号对齐会错位；按 ord=3 对齐才对。
    """
    segs = split_segments(SAMPLE)
    ai = [{"ord": 3, "answer": "±4"}]
    qs = build_questions(segs, ai)
    assert qs[2]["answer"] == "±4"
    assert qs[0]["answer"] == "B"
