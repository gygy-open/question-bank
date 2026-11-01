"""公式里"能解析但没有字形"的字符。

KaTeX 对这几种字符不报语法错误，只在控制台打 `No character metrics for 'X'`，
页面上是空白或方框——所以按"渲染是否抛异常"来查是查不到的。

一本 786 题的教辅实测：12,245 个行内公式 + 26 个块级公式，语法失败 0 个，
这类告警 174 个，构成为 ⏜×162、⫫×3、公式内圈数字×9。
"""
import pytest

from app.services.question_content_converter import markdown_to_rich_doc

NO_METRICS = ["⏜", "⫫"]


def _latex_list(doc):
    out = []

    def walk(node):
        if node.get("type") in ("inlineMath", "blockMath"):
            out.append(node.get("attrs", {}).get("latex", ""))
        for child in node.get("content") or []:
            if isinstance(child, dict):
                walk(child)

    walk(doc)
    return out


@pytest.mark.parametrize("ch", NO_METRICS)
def test_glyph_without_metrics_is_replaced(ch):
    doc = markdown_to_rich_doc(f"$\\text{{ {ch} }}AB$")
    latex = " ".join(_latex_list(doc))

    assert ch not in latex
    assert "\\frown" in latex or "\\parallel" in latex


def test_arc_symbol_becomes_frown():
    doc = markdown_to_rich_doc(r"$\overset{\text{ ⏜ }}{AB}$")
    assert _latex_list(doc) == [r"\overset{\frown }{AB}"]


def test_parallel_and_equal_keeps_meaning():
    """⫫ 在中文教材里是"平行且相等",不能只剩 \\parallel;也不能拼成 \\parallelA。"""
    doc = markdown_to_rich_doc(r"${AM}\text{ ⫫ }A{A}^{\prime}$")
    latex = _latex_list(doc)[0]

    assert latex == r"{AM}\underline{\parallel}A{A}^{\prime}"


def test_circled_digits_inside_math_untouched():
    """\\textcircled 在 Word 导出里会变成字面量;KaTeX 能用系统字体显示 ①,保持原样。"""
    doc = markdown_to_rich_doc(r"$① + ② = ③$")
    assert _latex_list(doc) == [r"① + ② = ③"]


@pytest.mark.parametrize(
    "source",
    [
        r"$\overset{\text{ ⏜ }}{AB}$",
        r"${AM}\text{ ⫫ }A{A}^{\prime}$",
        r"$① + ②$",
    ],
)
def test_normalized_latex_exports_to_omml_without_raw_commands(source):
    import re

    from lxml import etree

    from app.services.exporting.richdoc.omml import latex_to_omml

    latex = _latex_list(markdown_to_rich_doc(source))[0]
    xml = etree.tostring(latex_to_omml(latex), encoding="unicode")
    text = "".join(re.findall(r"<m:t[^>]*>([^<]*)</m:t>", xml))
    assert "\\" not in text


def test_circled_digits_outside_math_untouched():
    """正文里的圈数字不进公式,浏览器字体有字形,不能改。"""
    doc = markdown_to_rich_doc("① 先化简，② 再代入，$x=1$")
    text = " ".join(
        n["text"]
        for n in _all_nodes(doc)
        if n.get("type") == "text"
    )

    assert "① 先化简" in text
    assert "② 再代入" in text


def _all_nodes(doc):
    out = []
    stack = [doc]
    while stack:
        node = stack.pop()
        out.append(node)
        stack.extend(c for c in (node.get("content") or []) if isinstance(c, dict))
    return out


def test_block_math_also_normalized():
    doc = markdown_to_rich_doc("$$\n\\text{ ⏜ } AB\n$$")
    latex = _latex_list(doc)[0]

    assert "⏜" not in latex
    assert "\\frown" in latex


def test_plain_latex_untouched():
    """不含这些字符的公式必须逐字不变。"""
    original = r"\dfrac{1}{2}x^2 + \sqrt{3} \leq 4"
    doc = markdown_to_rich_doc(f"${original}$")

    assert _latex_list(doc) == [original]


def test_idempotent_on_already_fixed_latex():
    doc = markdown_to_rich_doc(r"$\overset{\frown }{AB}$")
    assert _latex_list(doc) == [r"\overset{\frown }{AB}"]
