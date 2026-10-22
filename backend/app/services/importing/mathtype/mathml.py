"""MTEF → MathML conversion entry point (pure Python).

Pipeline: OLE bytes → parse → build MTEF XML → mover → char_replacer → XSLT → MathML
"""

import re
import struct
import io
import olefile
from pathlib import Path
from lxml import etree

from .stream import ByteStream

_XSLT_DIR = Path(__file__).resolve().parent / "xslt"


def mtef_to_mathml(ole_data: bytes) -> str | None:
    """Convert OLE binary data (full compound file) to MathML."""
    try:
        return _mtef_to_mathml_impl(ole_data)
    except Exception:
        return None


def _mtef_to_mathml_impl(ole_data: bytes) -> str | None:
    # ── Open OLE container ────────────────────────────
    try:
        ole = olefile.OleFileIO(io.BytesIO(ole_data))
    except Exception:
        return None

    mtef_raw = None
    for name in ("Equation Native", "EquationNative", "Equation"):
        if ole.exists(name):
            try:
                s = ole.openstream(name)
                mtef_raw = s.read()
                break
            except Exception:
                continue
    ole.close()

    if mtef_raw is None:
        return None

    # ── Strip 28-byte EQNOLEFILEHDR ───────────────────
    try:
        header_fmt = struct.Struct("<H I H I I I I I")
        if len(mtef_raw) < 28:
            return None
        cb_hdr, _, _, cb_object, *_ = header_fmt.unpack_from(mtef_raw, 0)
        if cb_hdr == 28:
            mtef_data = mtef_raw[28:]
            if 0 < cb_object <= len(mtef_data):
                mtef_data = mtef_data[:cb_object]
        else:
            mtef_data = mtef_raw
    except Exception:
        mtef_data = mtef_raw

    if len(mtef_data) < 2:
        return None

    ver = mtef_data[0]
    if ver not in (3, 5):
        return None

    # ── Parse MTEF binary → record tree ──────────────
    stream = ByteStream(mtef_data)
    _skip_stream_header(stream, ver)

    eq = None
    try:
        if ver == 5:
            from .records5 import parse_equation
            eq = parse_equation(stream)
        else:
            from .records3 import parse_equation_v3
            eq = parse_equation_v3(stream)
    except Exception:
        # Fallback: try the other version
        try:
            stream = ByteStream(mtef_data)
            _skip_stream_header(stream, 5 if ver == 3 else 3)
            if ver == 5:
                from .records3 import parse_equation_v3
                eq = parse_equation_v3(stream)
            else:
                from .records5 import parse_equation
                eq = parse_equation(stream)
        except Exception:
            return None

    if eq is None:
        return None

    eq.setdefault("mtef_version", ver)

    # ── Build MTEF XML ───────────────────────────────
    from .builder import build_mtef_xml
    xml_root = build_mtef_xml(eq)

    # ── Mover: rearrange sub/sup elements ────────────
    from .mover import move as mover_move
    mover_move(xml_root)

    # ── Char replacer: char codes → MathML tokens ────
    from .chars import replace as chars_replace
    chars_replace(xml_root)

    # ── XSLT: MTEF XML → MathML ──────────────────────
    mathml = _xslt_transform(xml_root)
    if mathml is None:
        return None

    # ── Post-process: fix namespaces ──────────────────
    # Strip namespace PREFIXES, remove empty xmlns, and ensure the
    # MathML namespace is present so MML2OMML.XSL can find elements.
    MATHML_NS = "http://www.w3.org/1998/Math/MathML"
    try:
        # Remove XML declaration
        cleaned = re.sub(r'<\?xml[^?]*\?>', '', mathml).strip()

        out_root = etree.fromstring(cleaned.encode("utf-8"))

        # Strip namespace prefixes from tags
        for elem in out_root.iter():
            tag = elem.tag
            if isinstance(tag, str) and "}" in tag:
                elem.tag = tag.split("}", 1)[1]
            # Remove empty xmlns="" and prefixed xmlns declarations
            for attr in list(elem.attrib):
                if attr == "xmlns":
                    val = elem.attrib[attr]
                    if val == "" or (elem is not out_root and val == MATHML_NS):
                        del elem.attrib[attr]
                elif attr.startswith("xmlns:"):
                    del elem.attrib[attr]

        # Ensure root has MathML namespace.
        # Setting the attribute via lxml alone is unreliable after tag
        # stripping, so we add it via string replacement on the output.
        if "xmlns" not in out_root.attrib:
            out_root.attrib["xmlns"] = MATHML_NS

        result = etree.tostring(out_root, encoding="unicode", pretty_print=False)
        # lxml may drop the xmlns when tags have no namespace, so ensure
        # it is present via string injection if missing.
        if 'xmlns=' not in result:
            result = result.replace('<math ', '<math xmlns="' + MATHML_NS + '" ', 1)
            result = result.replace('<math>', '<math xmlns="' + MATHML_NS + '">', 1)
        return result
    except Exception:
        return mathml


def _skip_stream_header(stream, ver):
    """Skip MTEF stream header bytes before record parsing.

    V5: version(1) platform(1) product(1) product_version(1)
        product_subversion(1) app_key(zero-term) equation_options(1)
    V3: version(1) platform(1) product(1) product_version(1)
        product_subversion(1) — no app_key or options.
    """
    try:
        stream.uint8()  # version (already checked)
        stream.uint8()  # platform
        stream.uint8()  # product
        stream.uint8()  # product_version
        stream.uint8()  # product_subversion
        if ver == 5:
            # application_key: null-terminated string
            for _ in range(64):
                if stream.uint8() == 0:
                    break
            stream.uint8()  # equation_options
    except IndexError:
        pass


def _xslt_transform(xml_root: etree._Element) -> str | None:
    """Transform MTEF XML to MathML using the bundled XSLT."""
    transform_xsl = _XSLT_DIR / "transform.xsl"
    if not transform_xsl.exists():
        return None
    try:
        xsl_doc = etree.parse(str(transform_xsl))
        transform = etree.XSLT(xsl_doc)
        result = transform(xml_root)
        out = etree.tostring(result, encoding="unicode", pretty_print=False)
        return out if out.strip() else None
    except Exception:
        return None
