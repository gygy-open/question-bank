import zipfile
from pathlib import Path

import pytest
from docx import Document

from app.core.config import settings
from app.services.importing.docx_math import (
    MathTypeResult,
    build_warnings,
    count_vector_images,
    preprocess_mathtype,
    restore_math_tokens,
)
from app.services.importing.ingest import DocxIngestor
from app.services.importing.mathtype import mtef_to_mathml

FIXTURES = Path(__file__).parent / "fixtures" / "mathtype"

_OBJECT_RUN = (
    '<w:r><w:object w:dxaOrig="400" w:dyaOrig="600">'
    '<v:shape id="_x0000_i10{n}" type="#_x0000_t75" style="width:20pt;height:30pt">'
    '<v:imagedata r:id="rIdImg{n}" o:title=""/></v:shape>'
    '<o:OLEObject Type="Embed" ProgID="{prog_id}" ShapeID="_x0000_i10{n}" '
    'DrawAspect="Content" ObjectID="_10{n}" r:id="rIdOle{n}"/>'
    "</w:object></w:r>"
)
_NS_DECL = (
    'xmlns:v="urn:schemas-microsoft-com:vml" '
    'xmlns:o="urn:schemas-microsoft-com:office:office" '
)


def _build_docx(path: Path, ole_payloads: list[bytes], prog_id: str = "Equation.DSMT4") -> None:
    """生成带 MathType OLE 公式(及其 WMF 预览图)的最小 docx。"""
    doc = Document()
    doc.add_paragraph("设随机变量MARKER，求值")
    doc.save(path)

    with zipfile.ZipFile(path) as zf:
        entries = {i.filename: zf.read(i.filename) for i in zf.infolist()}

    document = entries["word/document.xml"].decode("utf-8")
    if 'xmlns:v="' not in document:
        document = document.replace("<w:document ", f"<w:document {_NS_DECL}", 1)
    elif 'xmlns:o="' not in document:
        document = document.replace(
            "<w:document ", '<w:document xmlns:o="urn:schemas-microsoft-com:office:office" ', 1
        )
    runs = "".join(_OBJECT_RUN.format(n=i, prog_id=prog_id) for i in range(len(ole_payloads)))
    document = document.replace("<w:t>设随机变量MARKER，求值</w:t></w:r>", f"<w:t>设随机变量</w:t></w:r>{runs}<w:r><w:t>，求值</w:t></w:r>", 1)
    assert runs in document
    entries["word/document.xml"] = document.encode("utf-8")

    rels = entries["word/_rels/document.xml.rels"].decode("utf-8")
    extra = ""
    for i, payload in enumerate(ole_payloads):
        entries[f"word/embeddings/oleObject{i}.bin"] = payload
        entries[f"word/media/image{i}.wmf"] = b"\xd7\xcd\xc6\x9a" + b"\x00" * 40
        extra += (
            f'<Relationship Id="rIdOle{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/oleObject" Target="embeddings/oleObject{i}.bin"/>'
            f'<Relationship Id="rIdImg{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image{i}.wmf"/>'
        )
    entries["word/_rels/document.xml.rels"] = rels.replace("</Relationships>", extra + "</Relationships>").encode()

    ct = entries["[Content_Types].xml"].decode("utf-8")
    ct = ct.replace(
        "<Default ",
        '<Default Extension="bin" ContentType="application/vnd.openxmlformats-officedocument.oleObject"/>'
        '<Default Extension="wmf" ContentType="image/x-wmf"/><Default ',
        1,
    )
    entries["[Content_Types].xml"] = ct.encode()

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)


def test_vendored_parser_converts_fixture():
    mathml = mtef_to_mathml((FIXTURES / "oleObject3.bin").read_bytes())
    assert mathml and "<msqrt" in mathml


def test_preprocess_replaces_ole_with_tokens(tmp_path):
    src = tmp_path / "in.docx"
    _build_docx(src, [(FIXTURES / "oleObject1.bin").read_bytes(), (FIXTURES / "oleObject3.bin").read_bytes()])

    result = preprocess_mathtype(src, tmp_path / "out.docx")

    assert result.total == 2 and result.failed == 0
    assert result.docx_path == tmp_path / "out.docx"
    assert result.formulas == {"QBEQ0Z": r"\frac{1}{6}", "QBEQ1Z": r"\sqrt{\frac{2}{3}}"}
    with zipfile.ZipFile(result.docx_path) as zf:
        xml = zf.read("word/document.xml").decode("utf-8")
    assert "w:object" not in xml and "QBEQ0Z" in xml and "QBEQ1Z" in xml


def test_preprocess_leaves_broken_ole_in_place(tmp_path):
    src = tmp_path / "in.docx"
    _build_docx(src, [b"not an ole file"])

    result = preprocess_mathtype(src, tmp_path / "out.docx")

    assert result.total == 1 and result.failed == 1
    assert result.formulas == {}
    assert result.docx_path == src
    assert not (tmp_path / "out.docx").exists()


def test_preprocess_ignores_non_equation_ole(tmp_path):
    src = tmp_path / "in.docx"
    _build_docx(src, [(FIXTURES / "oleObject1.bin").read_bytes()], prog_id="Excel.Sheet.12")

    result = preprocess_mathtype(src, tmp_path / "out.docx")

    assert result.total == 0 and result.docx_path == src


def test_restore_math_tokens_handles_multiple_and_unknown():
    md = "若QBEQ0Z且QBEQ1Z，则QBEQ9Z"
    out = restore_math_tokens(md, {"QBEQ0Z": "x>1", "QBEQ1Z": r"\frac{1}{2}"})
    assert out == r"若$x>1$且$\frac{1}{2}$，则QBEQ9Z"


def test_build_warnings():
    assert build_warnings(MathTypeResult(docx_path=Path("x")), 0) == []
    msgs = build_warnings(MathTypeResult(docx_path=Path("x"), total=3, failed=1), 2)
    assert len(msgs) == 2 and "1/3" in msgs[0] and "2 处" in msgs[1]
    assert count_vector_images("![](/a/image1.wmf) ![](/a/b.EMF) ![](/a/c.png)") == 2


class _RecordingStore:
    """记录入库的图片文件名,按顺序发放不带扩展名的假资产 URL。"""

    def __init__(self) -> None:
        self.received: list[str] = []

    async def __call__(self, data: bytes, filename: str):
        self.received.append(filename)
        return f"/api/v1/media/{len(self.received)}/content"


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    root = tmp_path / "data"
    (root / "static").mkdir(parents=True)
    monkeypatch.setattr(settings, "DATA_DIR", root)
    return root


@pytest.mark.asyncio
async def test_docx_ingestor_converts_mathtype_to_latex(tmp_path, data_dir):
    src = tmp_path / "paper.docx"
    _build_docx(src, [(FIXTURES / "oleObject1.bin").read_bytes(), (FIXTURES / "oleObject3.bin").read_bytes()])
    store = _RecordingStore()

    doc = await DocxIngestor().ingest(src, store=store, task_id="t1")

    assert r"设随机变量$\frac{1}{6}$$\sqrt{\frac{2}{3}}$，求值" in doc.markdown
    assert ".wmf" not in doc.markdown
    assert doc.warnings == []
    assert not [name for name in store.received if name.lower().endswith(".wmf")]


@pytest.mark.asyncio
async def test_docx_ingestor_warns_on_unconvertible_formula(tmp_path, data_dir):
    src = tmp_path / "paper.docx"
    _build_docx(src, [b"broken"])
    store = _RecordingStore()

    doc = await DocxIngestor().ingest(src, store=store, task_id="t2")

    # 残留的 WMF 预览图被入库并改写为资产 URL,警告仍需基于改写前的引用统计。
    assert [name for name in store.received if name.lower().endswith(".wmf")]
    assert "/api/v1/media/" in doc.markdown
    assert len(doc.warnings) == 2
