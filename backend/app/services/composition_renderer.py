import os
import logging
import tempfile
import json
import re
import shutil
from typing import List, Dict, Any, Callable, Optional
from pathlib import Path

import pypandoc

from app.models.question import Question, QuestionType
from app.models.composition import CompositionBlock, BlockType
from app.schemas.composition import OutputFormat, ContentPosition
from app.core.config import settings

logger = logging.getLogger(__name__)


class CompositionRenderer:
    """基于内容块 (Block) 的按需导出渲染引擎。

    渲染管线: Blocks -> 中间态 Markdown -> Pandoc -> DOCX / LaTeX(zip)。
    每种 block_type 由独立的渲染函数负责序列化, 不再依赖固化的整页模板。
    """

    def __init__(self):
        self.template_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "templates"
        )

    # ------------------------------------------------------------------
    # Shared helpers (ported from the legacy generator)
    # ------------------------------------------------------------------
    def _process_images(
        self, text: str, image_handler: Optional[Callable[[Path], str]] = None
    ) -> str:
        """Replace web image paths with absolute file system paths or handler output."""
        if not text:
            return ""

        def replace_match(match):
            alt = match.group(1)
            url = match.group(2)
            if url.startswith('/static/media/'):
                rel_path = url.replace('/static/media/', '', 1)
                file_path = settings.MEDIA_DIR / rel_path
                try:
                    abs_path = file_path.resolve()
                    if abs_path.exists():
                        if image_handler:
                            return f'![{alt}]({image_handler(abs_path)})'
                        return f'![{alt}]({abs_path.as_posix()})'
                except Exception as e:
                    logger.warning(f"Failed to resolve image path {url}: {e}")
            return match.group(0)

        return re.sub(r'!\[(.*?)\]\((.*?)\)', replace_match, text)

    def _format_answer(self, q: Question) -> str:
        answer = q.answer
        if not answer:
            return ""
        q_type = q.q_type.value if hasattr(q.q_type, "value") else q.q_type
        if q_type == QuestionType.FILL_IN_THE_BLANK.value:
            try:
                ans_obj = json.loads(answer)
                if isinstance(ans_obj, list):
                    parts = []
                    for item in ans_obj:
                        if isinstance(item, list):
                            parts.append(" 或 ".join(str(x) for x in item))
                        else:
                            parts.append(str(item))
                    return "；".join(parts)
            except Exception:
                pass
        return answer

    # ------------------------------------------------------------------
    # Block -> Markdown
    # ------------------------------------------------------------------
    def _append_question_details(
        self,
        md_lines: List[str],
        q: Question,
        include_answer: bool,
        include_analysis: bool,
        include_explanation: bool,
        include_summary: bool,
        include_source: bool,
        image_handler: Optional[Callable[[Path], str]] = None,
    ):
        if include_answer and q.answer:
            md_lines.append(
                f"**【答案】** {self._process_images(self._format_answer(q), image_handler)}"
            )
            md_lines.append("")
        if include_analysis and q.thinking:
            md_lines.append(f"**【分析】** {self._process_images(q.thinking, image_handler)}")
            md_lines.append("")
        if include_explanation and q.analysis:
            md_lines.append(f"**【解析】** {self._process_images(q.analysis, image_handler)}")
            md_lines.append("")
        if include_summary and q.summary:
            md_lines.append(f"**【总结】** {self._process_images(q.summary, image_handler)}")
            md_lines.append("")
        if include_source and q.source:
            md_lines.append(f"**【来源】** {self._process_images(q.source, image_handler)}")
            md_lines.append("")

    def _render_question_body(
        self,
        md_lines: List[str],
        q: Question,
        number: int,
        image_handler: Optional[Callable[[Path], str]] = None,
    ):
        md_lines.append(f"**{number}.** {self._process_images(q.content, image_handler)}")
        md_lines.append("")
        if q.options:
            opts = q.options
            if isinstance(opts, str):
                try:
                    opts = json.loads(opts)
                except Exception:
                    pass
            if isinstance(opts, list):
                if opts and isinstance(opts[0], dict) and "label" in opts[0]:
                    for o in opts:
                        label = o.get('label', '')
                        text = o.get('content') or o.get('text', '')
                        md_lines.append(f"{label}\\. {self._process_images(text, image_handler)}  ")
                else:
                    for idx, opt in enumerate(opts):
                        label = chr(65 + idx)
                        text = opt
                        if isinstance(opt, dict):
                            text = opt.get('content') or opt.get('text', '')
                        md_lines.append(f"{label}\\. {self._process_images(str(text), image_handler)}  ")
                md_lines.append("")

    def _block_content_text(self, block: CompositionBlock) -> str:
        content = block.content or {}
        if isinstance(content, str):
            return content
        return content.get("text", "") if isinstance(content, dict) else ""

    def generate_markdown(
        self,
        title: str,
        blocks: List[CompositionBlock],
        content_position: ContentPosition = ContentPosition.AFTER_QUESTION,
        include_answer: bool = True,
        include_analysis: bool = True,
        include_explanation: bool = True,
        include_summary: bool = True,
        include_source: bool = False,
        image_handler: Optional[Callable[[Path], str]] = None,
    ) -> str:
        md_lines: List[str] = [f"# {title}", ""]
        counter = 0
        appendix_questions: List[Question] = []

        for block in blocks:
            btype = block.block_type
            if btype == BlockType.HEADING.value:
                text = self._block_content_text(block).strip()
                if text:
                    counter = 0
                    md_lines.append(f"## {self._process_images(text, image_handler)}")
                    md_lines.append("")
            elif btype == BlockType.TEXT.value:
                text = self._block_content_text(block).strip()
                if text:
                    md_lines.append(self._process_images(text, image_handler))
                    md_lines.append("")
            elif btype == BlockType.PAGE_BREAK.value:
                md_lines.append("```{=latex}")
                md_lines.append("\\newpage")
                md_lines.append("```")
                md_lines.append("")
            elif btype == BlockType.QUESTION.value:
                q = block.question
                if not q:
                    continue
                counter += 1
                self._render_question_body(md_lines, q, counter, image_handler)
                if content_position == ContentPosition.AFTER_QUESTION:
                    self._append_question_details(
                        md_lines, q, include_answer, include_analysis,
                        include_explanation, include_summary, include_source, image_handler,
                    )
                elif content_position == ContentPosition.END_OF_PAPER:
                    appendix_questions.append(q)
                md_lines.append("")

        if content_position == ContentPosition.END_OF_PAPER and appendix_questions:
            md_lines.append("```{=latex}")
            md_lines.append("\\newpage")
            md_lines.append("```")
            md_lines.append("")
            md_lines.append("# 参考答案与解析")
            md_lines.append("")
            for idx, q in enumerate(appendix_questions, start=1):
                md_lines.append(f"**{idx}.** ")
                md_lines.append("")
                self._append_question_details(
                    md_lines, q, include_answer, include_analysis,
                    include_explanation, include_summary, include_source, image_handler,
                )
                md_lines.append("")

        return "\n".join(md_lines)

    # ------------------------------------------------------------------
    # File generation
    # ------------------------------------------------------------------
    def generate_file(
        self,
        title: str,
        blocks: List[CompositionBlock],
        format: OutputFormat,
        content_position: ContentPosition = ContentPosition.AFTER_QUESTION,
        include_answer: bool = True,
        include_analysis: bool = True,
        include_explanation: bool = True,
        include_summary: bool = True,
        include_source: bool = False,
    ) -> str:
        logger.debug(
            f"Rendering publication '{title}' as {format.value}, position={content_position.value}"
        )
        if content_position == ContentPosition.HIDDEN:
            include_answer = include_analysis = include_explanation = include_summary = include_source = False

        if format == OutputFormat.LATEX:
            return self._generate_latex_zip(
                title, blocks, content_position, include_answer, include_analysis,
                include_explanation, include_summary, include_source,
            )

        # DOCX via pandoc
        fd, path = tempfile.mkstemp(suffix=f".{format.value}")
        os.close(fd)
        markdown_content = self.generate_markdown(
            title, blocks, content_position, include_answer, include_analysis,
            include_explanation, include_summary, include_source,
        )
        extra_args = ['--standalone']
        reference_doc = os.path.join(self.template_dir, "yuanxuan-standard-math.docx")
        if os.path.exists(reference_doc):
            extra_args.append(f'--reference-doc={reference_doc}')
        try:
            pypandoc.convert_text(
                markdown_content,
                format.value,
                format='markdown+tex_math_dollars+raw_attribute',
                outputfile=path,
                extra_args=extra_args,
            )
        except Exception as e:
            logger.error(f"Pandoc conversion failed: {e}", exc_info=True)
            if os.path.exists(path):
                os.remove(path)
            raise
        return path

    def _generate_latex_zip(
        self,
        title: str,
        blocks: List[CompositionBlock],
        content_position: ContentPosition,
        include_answer: bool,
        include_analysis: bool,
        include_explanation: bool,
        include_summary: bool,
        include_source: bool,
    ) -> str:
        with tempfile.TemporaryDirectory() as tmpdirname:
            base_dir = Path(tmpdirname)
            images_dir = base_dir / "images"
            images_dir.mkdir()

            def latex_image_handler(src_path: Path) -> str:
                dst_name = src_path.name
                shutil.copy2(src_path, images_dir / dst_name)
                return f"images/{dst_name}"

            markdown_content = self.generate_markdown(
                title, blocks, content_position, include_answer, include_analysis,
                include_explanation, include_summary, include_source,
                image_handler=latex_image_handler,
            )
            tex_file = base_dir / f"{title}.tex"
            preamble = self._load_preamble()
            body = pypandoc.convert_text(
                markdown_content,
                'latex',
                format='markdown+tex_math_dollars+raw_attribute',
            )
            with open(tex_file, 'w', encoding='utf-8') as f:
                f.write(preamble.replace("%%BODY%%", body))

            zip_fd, zip_path = tempfile.mkstemp(suffix=".zip")
            os.close(zip_fd)
            os.remove(zip_path)
            archive_base = zip_path.replace(".zip", "")
            shutil.make_archive(archive_base, 'zip', base_dir)
            return zip_path

    def _load_preamble(self) -> str:
        preamble_path = os.path.join(self.template_dir, "preamble.tex")
        if os.path.exists(preamble_path):
            with open(preamble_path, 'r', encoding='utf-8') as f:
                return f.read()
        # Minimal fallback preamble with CJK + math support
        return (
            "\\documentclass[12pt]{article}\n"
            "\\usepackage{ctex}\n"
            "\\usepackage{amsmath,amssymb}\n"
            "\\usepackage{graphicx}\n"
            "\\usepackage[margin=2.5cm]{geometry}\n"
            "\\usepackage{enumitem}\n"
            "\\begin{document}\n"
            "%%BODY%%\n"
            "\\end{document}\n"
        )


publication_renderer = CompositionRenderer()
composition_renderer = publication_renderer
