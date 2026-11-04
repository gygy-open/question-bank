"""题干拆解体检与纯文本快照。包含 PR #28 评审中发现的反例。"""
from app.services.structure.check import CheckItem, check_structure, effective_text, locate, symbols_of
from app.services.structure.text import BLANK_PLACEHOLDER, IMAGE_PLACEHOLDER, build_stem_text

CUBIC = "已知函数$f(x)=x^{3}+ax+2$存在3个零点，则$a$的取值范围是（ ）"


def _codes(report, severity=None):
    return [i.code for i in report.issues if severity is None or i.severity == severity]


# --------------------------------------------------------------------------- #
# 纯文本快照
# --------------------------------------------------------------------------- #
def test_stem_text_keeps_math_delimiters_and_placeholders():
    doc = {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [
                {"type": "text", "text": "已知"},
                {"type": "inlineMath", "attrs": {"latex": "f(x)=x^2"}},
                {"type": "text", "text": "，如图"},
                {"type": "image", "attrs": {"src": "/x.png"}},
                {"type": "text", "text": "，则 a="},
                {"type": "blank", "attrs": {"blankId": "b1"}},
            ]},
            {"type": "blockMath", "attrs": {"latex": "y=1"}},
        ],
    }
    options = [
        {"id": "o1", "label": "A", "content": {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "1"}]}]}},
        {"id": "o2", "label": "B", "content": {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "inlineMath", "attrs": {"latex": "2"}}]}]}},
    ]
    text = build_stem_text(doc, options)
    assert text == f"已知$f(x)=x^2$，如图{IMAGE_PLACEHOLDER}，则 a={BLANK_PLACEHOLDER}\n$$y=1$$\nA. 1\nB. $2$"


# --------------------------------------------------------------------------- #
# 正常拆解
# --------------------------------------------------------------------------- #
def test_correct_decomposition_passes():
    report = check_structure(
        CUBIC,
        [CheckItem("f(x)=x^3+ax+2", source="f(x)=x^{3}+ax+2"), CheckItem("f(x) 存在 3 个零点", source="存在3个零点")],
        [CheckItem("求 a 的取值范围", source="$a$的取值范围")],
    )
    assert report.ok, report.to_dict()
    assert report.element_spans[0] == (CUBIC.index("f(x)"), CUBIC.index("$存在"))
    # “函数”“是”这类描述词不进任何条目,只作为提示留给人看。
    assert report.residual == "函数是" and report.coverage > 0.85


def test_quote_with_different_spacing_is_still_located():
    stem = "已知 $x > 0$ ，求 $x$"
    assert locate(stem, "$x>0$") == (stem.index("$x"), stem.index("$ ，") + 1)


# --------------------------------------------------------------------------- #
# 设问符号悬空(漏拆的可靠信号)
# --------------------------------------------------------------------------- #
def test_missing_parametric_condition_leaves_symbol_dangling():
    report = check_structure(CUBIC, [CheckItem("存在3个零点")], [CheckItem("求 a 的取值范围", source="$a$的取值范围")])
    assert "dangling_symbol" in _codes(report, "error")


def test_latex_commands_do_not_carry_symbols():
    # 评审反例:元素里的 \frac 含字母 a,旧实现因此误判“a 已有条件承载”。
    stem = "已知 $\\frac{1}{2}$ 且 $x>0$，求 $a$"
    report = check_structure(stem, [CheckItem("\\frac{1}{2}"), CheckItem("x>0")], [CheckItem("求 a")])
    assert [i.detail for i in report.issues if i.code == "dangling_symbol"] == ["a"]


def test_adjacent_letters_are_a_product_but_function_names_are_not_symbols():
    # 数学里 ax 是 a 乘 x;sin、ln 是函数名,不是 s、i、n、l。
    assert symbols_of("ax+2") == {"a", "x"}
    assert symbols_of("sin x + ln y + \\log_2 z") == {"x", "y", "z"}


def test_axis_names_and_euler_constant_are_not_variables():
    assert symbols_of("与 x 轴交于点 A") == {"A"}
    report = check_structure("已知 $f(x)=e^x$，求 $f(1)$ 的值", [CheckItem("f(x)=e^x")], [CheckItem("求 f(1)")])
    assert "dangling_symbol" not in _codes(report)


def test_shared_material_conditions_carry_symbols():
    report = check_structure(
        "(1) 求 $a_2$", [], [CheckItem("求 a_2")], shared_texts=["数列 a_n 满足 a_1=1"]
    )
    assert "dangling_symbol" not in _codes(report)


# --------------------------------------------------------------------------- #
# 原文定位与重复
# --------------------------------------------------------------------------- #
def test_rewritten_quote_is_reported_as_not_found():
    report = check_structure(CUBIC, [CheckItem("有三个零点并且零点互不相同")], [])
    assert "span_not_found" in _codes(report, "error")


def test_repeated_text_is_located_in_order_not_flagged_duplicate():
    # 评审反例:原文两处都是“1”,旧实现都定位到第一处并判为重复。
    stem = "已知 a=1，b=1，求 a+b"
    report = check_structure(stem, [CheckItem("a=1", source="1"), CheckItem("b=1", source="1")], [])
    assert report.element_spans == [(5, 6), (9, 10)]
    assert "duplicate" not in _codes(report)


def test_two_conditions_from_one_sentence_may_share_a_span():
    stem = "抛物线与 x 轴交于 A(-1,0)、B(3,0)"
    sentence = "与 x 轴交于 A(-1,0)、B(3,0)"
    report = check_structure(
        stem, [CheckItem("过点 A(-1,0)", source=sentence), CheckItem("过点 B(3,0)", source=sentence)], []
    )
    assert "duplicate" not in _codes(report)


def test_same_condition_twice_is_duplicate():
    report = check_structure(CUBIC, [CheckItem("存在3个零点"), CheckItem("存在 3 个零点")], [])
    assert "duplicate" in _codes(report, "error")


# --------------------------------------------------------------------------- #
# 提示类
# --------------------------------------------------------------------------- #
def test_compound_condition_is_a_warning_only():
    report = check_structure("已知 x>0且y>0", [CheckItem("x>0且y>0")], [])
    assert _codes(report, "warning") == ["compound"] and report.ok


def test_uncovered_text_is_info_unless_strict():
    stem = "已知 $a=1$，$b=2$，求 $a$"
    elements = [CheckItem("a=1")]
    asks = [CheckItem("求 a", source="$a$")]
    loose = check_structure(stem, elements, asks)
    strict = check_structure(stem, elements, asks, strict=True)
    assert loose.ok and "b=2" in loose.residual
    assert not strict.ok


def test_effective_text_drops_fillers_labels_and_blanks():
    assert effective_text("已知 x>0，则 y=____\nA. 1") == "x>0y=1"


# --------------------------------------------------------------------------- #
# 真实试跑中发现的误报(40 道小测题,qwen3.7-max)
# --------------------------------------------------------------------------- #
def test_option_labels_are_not_symbols_only_when_talking_about_options():
    assert symbols_of("从选项A、B、C、D中选出函数的图象") == set()
    assert symbols_of("下列 A、B、C 中正确的是") == set()
    # 几何里「A、B 两点」是变量,仍要求条件给出。
    assert symbols_of("求 A、B 两点间的距离") == {"A", "B"}


def test_probability_operators_are_not_symbols():
    assert symbols_of("求$P\\left( X = 1 \\right)$的值") == {"X"}
    assert symbols_of("求 E(X) 与 D(X)") == {"X"}


def test_equivalent_latex_quotes_are_located():
    stem = "已知$S_{n}$是等比数列$\\left\\{ a_{n} \\right\\}$的前n项和"
    span = locate(stem, "等比数列${ a_{n} }$")
    assert span is not None and stem[span[0]:span[1]] == "等比数列$\\left\\{ a_{n} \\right\\}$"
    stem = "已知函数$f(x)$的导函数为$f^{\\prime}(x)$，且"
    span = locate(stem, "导函数为$f^{′}(x)$")
    assert span is not None and stem[span[0]:span[1]].endswith("f^{\\prime}(x)$")
