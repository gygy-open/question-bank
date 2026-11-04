"""元素拆解体检测试。

这里的每条用例都对应一种真实出现过的拆解错误：AI 改写原文、把两条元素写成
同一件事、一条元素塞两个断言、漏掉含参式子导致设问符号悬空。
"""

import pytest

from app.services.question_structure import (
    Element,
    Issue,
    check_structure,
    effective_text,
)

# 一道可以完整拆开的小题：三个元素 + 一条设问
STEM = "已知函数 f(x)=x^3+ax+2 有三个零点，求 a 的取值范围。"
ASK = "求 a 的取值范围"

GOOD_ELEMENTS = [
    Element("f(x)=x^3+ax+2"),
    Element("有三个零点"),
    Element(ASK, role="ask"),
]


def _codes(report):
    return {issue.code for issue in report.issues}


def _by_code(report, code):
    return [issue for issue in report.issues if issue.code == code]


class TestGoodDecomposition:
    def test_correct_decomposition_passes(self):
        report = check_structure(STEM, GOOD_ELEMENTS, asks=[ASK])
        assert report.ok
        assert "duplicate" not in _codes(report)
        assert "span_not_found" not in _codes(report)

    def test_plain_strings_are_accepted(self):
        report = check_structure(STEM, ["f(x)=x^3+ax+2", "有三个零点", ASK])
        assert report.ok

    def test_coverage_is_reported(self):
        report = check_structure(STEM, GOOD_ELEMENTS)
        assert 0 < report.coverage <= 1.0


class TestMissingSource:
    def test_rewritten_element_reports_span_not_found(self):
        """AI 常把原文写“顺”一点：加了个原文没有的限定。"""
        elements = [
            Element("f(x)=x^3+ax+2"),
            Element("有三个零点并且零点互不相同"),
        ]
        report = check_structure(STEM, elements)
        assert not report.ok
        assert "span_not_found" in _codes(report)

    def test_span_out_of_range_reports_span_not_found(self):
        elements = [Element("f(x)=x^3+ax+2", start=0, end=99999)]
        report = check_structure(STEM, elements)
        assert "span_not_found" in _codes(report)


class TestDuplicate:
    def test_same_span_twice(self):
        elements = [
            Element("f(x)=x^3+ax+2", start=4, end=18),
            Element("f(x)=x^3+ax+2", start=4, end=18),
        ]
        report = check_structure(STEM, elements)
        assert not report.ok
        assert "duplicate" in _codes(report)

    def test_overlapping_span(self):
        elements = [
            Element("f(x)=x^3+ax+2", start=4, end=18),
            Element("x^3+ax+2", start=6, end=18),
        ]
        report = check_structure(STEM, elements)
        assert "duplicate" in _codes(report)

    def test_identical_text_without_span(self):
        report = check_structure(STEM, ["有三个零点", "有三个零点"])
        assert "duplicate" in _codes(report)

    def test_different_elements_are_not_duplicate(self):
        report = check_structure(STEM, ["有三个零点", "求 a 的取值范围"])
        assert "duplicate" not in _codes(report)


class TestCompound:
    def test_conjunction_is_flagged(self):
        report = check_structure(STEM, ["f(x) 连续并且有三个零点"])
        issues = _by_code(report, "compound")
        assert issues and issues[0].severity == "warning"

    @pytest.mark.parametrize("word", ["并且", "同时", "另外"])
    def test_common_joiners(self, word):
        report = check_structure(STEM, ["f(x) 连续%s有三个零点" % word])
        assert "compound" in _codes(report)

    def test_enumeration_is_not_compound(self):
        """顿号并列同类条件是正常的，不该报。"""
        report = check_structure(STEM, ["a、b 均为正数"])
        assert "compound" not in _codes(report)

    def test_warning_does_not_fail_the_report(self):
        report = check_structure("已知函数 g(x) 连续并且有三个零点。", ["g(x) 连续并且有三个零点"])
        assert report.ok  # 只有 warning
        assert report.errors == ()


class TestDanglingSymbol:
    def test_missing_parameter_element_is_caught(self):
        """漏掉含参式子时，设问里的 a 会彻底悬空——这是最可靠的漏拆信号。"""
        elements = [Element("有三个零点"), Element(ASK, role="ask")]
        report = check_structure(STEM, elements, asks=[ASK])
        assert not report.ok
        dangling = _by_code(report, "dangling_symbol")
        assert dangling and "a" in dangling[0].message

    def test_ask_element_does_not_satisfy_itself(self):
        """设问自身含 a，不能算作 a 已被承载。"""
        elements = [Element("有三个零点"), Element(ASK, role="ask")]
        report = check_structure(STEM, elements, asks=[ASK])
        assert "dangling_symbol" in _codes(report)

    def test_parameter_present_is_not_reported(self):
        elements = [Element("f(x)=x^3+ax+2"), Element(ASK, role="ask")]
        report = check_structure(STEM, elements, asks=[ASK])
        assert "dangling_symbol" not in _codes(report)

    def test_no_asks_means_no_symbol_check(self):
        report = check_structure(STEM, [Element("有三个零点")])
        assert "dangling_symbol" not in _codes(report)


class TestEmptyAndValidation:
    def test_blank_element(self):
        report = check_structure(STEM, ["f(x)=x^3+ax+2", "   "])
        assert "empty" in _codes(report)

    def test_half_span_is_rejected(self):
        with pytest.raises(ValueError):
            Element("x", start=1)

    def test_report_is_serializable(self):
        report = check_structure(STEM, ["有三个零点"], asks=[ASK])
        payload = report.to_dict()
        assert payload["ok"] is False
        assert isinstance(payload["issues"], list)
        assert {"code", "severity", "index", "message", "detail"} <= set(payload["issues"][0])


class TestResidualAndStrictMode:
    def test_residual_lists_uncovered_text(self):
        report = check_structure(STEM, ["f(x)=x^3+ax+2"])
        assert "有三个零点" in report.residual
        assert report.ok  # 默认不算错

    def test_strict_mode_turns_residual_into_error(self):
        report = check_structure(STEM, ["f(x)=x^3+ax+2"], strict=True)
        assert not report.ok
        assert _by_code(report, "uncovered")[0].severity == "error"

    def test_filler_words_are_not_counted(self):
        assert effective_text("已知函数f(x)有三个零点，") == "函数fx有三个零点"

    def test_ordinal_is_not_counted(self):
        # “求”本身是题面套话，一并去掉，只留实义部分
        assert effective_text("3．求 a 的值") == "a的值"
        assert effective_text("（2）求 a 的值") == "a的值"


class TestRealQuestions:
    """拿两道真题实跑，确认判据在真实语料上不误报。"""

    def test_cubic_question(self):
        report = check_structure(STEM, GOOD_ELEMENTS, asks=[ASK])
        assert report.ok

    def test_parabola_question(self):
        stem = (
            "如图，在平面直角坐标系 xOy 中，抛物线 y=-x^2+bx+c 与 x 轴交于点 "
            "A(-1,0)、B(3,0)，与 y 轴交于点 C。"
        )
        elements = [
            Element("抛物线 y=-x^2+bx+c"),
            Element("A(-1,0)"),
            Element("B(3,0)"),
            Element("与 y 轴交于点 C"),
        ]
        report = check_structure(stem, elements, asks=["求 b、c 的值及点 C 的坐标"])
        assert report.ok, report.to_dict()

    def test_parabola_without_formula_reports_dangling(self):
        stem = (
            "如图，在平面直角坐标系 xOy 中，抛物线 y=-x^2+bx+c 与 x 轴交于点 "
            "A(-1,0)、B(3,0)，与 y 轴交于点 C。"
        )
        elements = [Element("A(-1,0)"), Element("B(3,0)"), Element("与 y 轴交于点 C")]
        report = check_structure(stem, elements, asks=["求 b、c 的值及点 C 的坐标"])
        symbols = {issue.message for issue in _by_code(report, "dangling_symbol")}
        assert any("b" in m for m in symbols)
        assert any("c" in m for m in symbols)
