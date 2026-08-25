"""LaTeX → OMML(Office Math)转换,全程 in-process、无 pandoc。

链路:latex ──latex2mathml──▶ MathML ──mathml2omml(MIT)──▶ OMML ──lxml──▶ <m:oMath> 元素。
调用方(DocxRenderer)把返回的元素拼进 python-docx 段落;转换失败由调用方退化为纯文本。
"""

from __future__ import annotations

import latex2mathml.converter as _l2m
import mathml2omml as _m2o
from lxml import etree

_M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"


def latex_to_omml(latex: str, display: bool = False) -> etree._Element:
    """把单条 LaTeX 公式转成独立的 <m:oMath> 元素;失败抛异常交调用方回退。"""
    mathml = _l2m.convert(latex, display="block" if display else "inline")
    omml = _m2o.convert(mathml)
    root = etree.fromstring(f'<r xmlns:m="{_M_NS}">{omml}</r>'.encode())
    math_el = root.find(f".//{{{_M_NS}}}oMath")
    if math_el is None:
        raise ValueError(f"no <m:oMath> produced for latex: {latex!r}")
    return math_el
