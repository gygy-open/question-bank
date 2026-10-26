"""DOCX 中非 OMML 公式(MathType / Equation Editor 3.0 OLE 对象)→ LaTeX。

pandoc 只认 Word 原生 OMML 公式;MathType 公式以 OLE 对象(``w:object`` + ``oleObjectN.bin``)
存储，pandoc 只会输出其 WMF/EMF 预览图，浏览器无法显示。这里在 pandoc 之前预处理 docx:
把每个 MathType OLE 解析为 MathML,替换成纯 ASCII 占位符文本;再用一次 pandoc 调用把
全部 MathML 批量转成 LaTeX,pandoc 正文转换完成后把占位符换回 ``$latex$``。
"""
from __future__ import annotations

import logging
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional

import pypandoc
from lxml import etree

from app.services.importing.mathtype import mtef_to_mathml

logger = logging.getLogger(__name__)

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_O_NS = "urn:schemas-microsoft-com:office:office"
_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_XML_NS = "http://www.w3.org/XML/1998/namespace"

# 只处理正文类 part(正文、脚注、尾注、页眉页脚);它们各自有独立的 rels。
_PART_RE = re.compile(r"^word/(document|footnotes|endnotes|header\d*|footer\d*)\.xml$")

_TOKEN_FMT = "QBEQ{}Z"
_TOKEN_RE = re.compile(r"QBEQ(\d+)Z")
_BATCH_LINE_RE = re.compile(r"^QBEQ(\d+)Z\s+\$+(.+?)\$+$", re.DOTALL)
_DIGIT_MTEXT_RE = re.compile(r"<mtext>\s*(\d+(?:\.\d+)?)\s*</mtext>")
_DISPLAY_ATTR_RE = re.compile(r'\sdisplay="block"')
_LEFTOVER_VECTOR_IMG_RE = re.compile(r"!\[[^\]]*\]\([^)\s]+\.(?:wmf|emf)\)", re.IGNORECASE)


@dataclass
class MathTypeResult:
    docx_path: Path
    formulas: Dict[str, str] = field(default_factory=dict)  # token → LaTeX
    total: int = 0
    failed: int = 0


def _is_equation_prog_id(prog_id: Optional[str]) -> bool:
    # Equation.DSMT4 / Equation.DSMT6 (MathType)、Equation.3 (Equation Editor 3.0)
    return bool(prog_id) and prog_id.startswith("Equation.")


def _rels_path_for(part: str) -> str:
    p = PurePosixPath(part)
    return str(p.parent / "_rels" / f"{p.name}.rels")


def _load_rels(zf: zipfile.ZipFile, part: str) -> Dict[str, str]:
    rels_name = _rels_path_for(part)
    if rels_name not in zf.namelist():
        return {}
    root = etree.fromstring(zf.read(rels_name))
    base = PurePosixPath(part).parent
    rels: Dict[str, str] = {}
    for rel in root.iter(f"{{{_PKG_REL_NS}}}Relationship"):
        if rel.get("TargetMode") == "External":
            continue
        target = rel.get("Target", "")
        resolved = target.lstrip("/") if target.startswith("/") else _normalize(base / target)
        rels[rel.get("Id", "")] = resolved
    return rels


def _normalize(path: PurePosixPath) -> str:
    parts: List[str] = []
    for seg in path.parts:
        if seg == "..":
            if parts:
                parts.pop()
        elif seg not in (".", ""):
            parts.append(seg)
    return "/".join(parts)


def _normalize_mathml(mathml: str) -> str:
    # 公式在题干中均为行内；MathType 的纯数字常被放在 <mtext>,pandoc 会转成 \text{6}。
    mathml = _DISPLAY_ATTR_RE.sub("", mathml, count=1)
    return _DIGIT_MTEXT_RE.sub(r"<mn>\1</mn>", mathml)


def _mathml_to_latex_batch(mathml_by_token: Dict[str, str]) -> Dict[str, str]:
    """一次 pandoc 调用把多条 MathML 转成 LaTeX;批量结果对不上的条目逐条重试。"""
    if not mathml_by_token:
        return {}

    html = "\n".join(f"<p>{tok} {mml}</p>" for tok, mml in mathml_by_token.items())
    result: Dict[str, str] = {}
    try:
        out = pypandoc.convert_text(html, "markdown", format="html", extra_args=["--wrap=none"])
        for block in re.split(r"\n\s*\n", out.strip()):
            m = _BATCH_LINE_RE.match(block.strip())
            if m:
                tok = _TOKEN_FMT.format(m.group(1))
                if tok in mathml_by_token:
                    result[tok] = m.group(2).strip()
    except Exception as e:  # noqa: BLE001 - 失败时逐条重试
        logger.warning("Batch MathML→LaTeX conversion failed: %s", e)

    for tok, mml in mathml_by_token.items():
        if tok in result:
            continue
        try:
            out = pypandoc.convert_text(
                f"<p>{mml}</p>", "markdown", format="html", extra_args=["--wrap=none"]
            ).strip()
            m = re.fullmatch(r"\$+(.+?)\$+", out, re.DOTALL)
            if m:
                result[tok] = m.group(1).strip()
        except Exception as e:  # noqa: BLE001
            logger.warning("MathML→LaTeX conversion failed for %s: %s", tok, e)
    return result


def _replace_with_token(obj: etree._Element, token: str) -> None:
    t = etree.Element(f"{{{_W_NS}}}t")
    t.set(f"{{{_XML_NS}}}space", "preserve")
    t.text = token
    parent = obj.getparent()
    parent.replace(obj, t)


def preprocess_mathtype(docx_path: Path, output_path: Path) -> MathTypeResult:
    """把 docx 里的 MathType OLE 公式替换为占位符，写出到 output_path。

    没有任何公式被转换时不写新文件，返回原路径。转换失败的公式保持原样(pandoc 仍输出预览图)。
    """
    result = MathTypeResult(docx_path=docx_path)

    with zipfile.ZipFile(docx_path) as zf:
        names = zf.namelist()
        roots: Dict[str, etree._Element] = {}
        mathml_by_token: Dict[str, str] = {}
        objects_by_token: Dict[str, tuple[str, etree._Element]] = {}

        for part in names:
            if not _PART_RE.match(part):
                continue
            root = etree.fromstring(zf.read(part))
            objects = list(root.iter(f"{{{_W_NS}}}object"))
            if not objects:
                continue
            roots[part] = root
            rels = _load_rels(zf, part)
            for obj in objects:
                ole = obj.find(f"{{{_O_NS}}}OLEObject")
                if ole is None or not _is_equation_prog_id(ole.get("ProgID")):
                    continue
                result.total += 1
                target = rels.get(ole.get(f"{{{_R_NS}}}id", ""))
                mathml = None
                if target and target in names:
                    mathml = mtef_to_mathml(zf.read(target))
                if not mathml:
                    result.failed += 1
                    continue
                token = _TOKEN_FMT.format(len(mathml_by_token))
                mathml_by_token[token] = _normalize_mathml(mathml)
                objects_by_token[token] = (part, obj)

        latex_by_token = _mathml_to_latex_batch(mathml_by_token)
        changed_parts: set[str] = set()
        for token, (part, obj) in objects_by_token.items():
            latex = latex_by_token.get(token)
            if not latex:
                result.failed += 1
                continue
            _replace_with_token(obj, token)
            result.formulas[token] = latex
            changed_parts.add(part)

        if not changed_parts:
            return result

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as out:
            for item in zf.infolist():
                if item.filename in changed_parts:
                    data = etree.tostring(
                        roots[item.filename], xml_declaration=True, encoding="UTF-8", standalone=True
                    )
                else:
                    data = zf.read(item.filename)
                out.writestr(item, data)

    result.docx_path = output_path
    return result


def restore_math_tokens(markdown: str, formulas: Dict[str, str]) -> str:
    """把占位符换回行内 LaTeX;未知占位符原样保留。"""
    if not formulas:
        return markdown

    def repl(m: re.Match[str]) -> str:
        latex = formulas.get(m.group(0))
        return f"${latex}$" if latex else m.group(0)

    return _TOKEN_RE.sub(repl, markdown)


def count_vector_images(markdown: str) -> int:
    """统计 markdown 中残留的 WMF/EMF 图片引用(浏览器无法显示)。"""
    return len(_LEFTOVER_VECTOR_IMG_RE.findall(markdown))


def build_warnings(result: MathTypeResult, leftover_vector_images: int) -> List[str]:
    warnings: List[str] = []
    if result.failed:
        warnings.append(
            f"有 {result.failed}/{result.total} 个 MathType 公式未能转换为 LaTeX,已保留为图片，请人工核对。"
        )
    if leftover_vector_images:
        warnings.append(
            f"文档中有 {leftover_vector_images} 处 WMF/EMF 图片(可能是无法识别的公式或旧式图形),浏览器可能无法显示，请人工核对。"
        )
    return warnings
