import pypandoc
import os
import logging
import tempfile
import json
import re
import shutil
from typing import List, Dict, Any, Callable, Optional
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from app.models.question import Question, QuestionType
from app.schemas.paper import OutputFormat, ContentPosition
from app.services.question_render import (
    answer_spec_to_markdown,
    rich_doc_to_markdown,
)
from app.core.config import settings

logger = logging.getLogger(__name__)

class PaperGenerator:
    def __init__(self):
        self.template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
        self.jinja_env = Environment(
            loader=FileSystemLoader(self.template_dir),
            block_start_string='\\BLOCK{',
            block_end_string='}',
            variable_start_string='\\VAR{',
            variable_end_string='}',
            comment_start_string='\\#{',
            comment_end_string='}',
            line_statement_prefix='%%',
            line_comment_prefix='%#',
            trim_blocks=True,
            autoescape=False,
        )

    def _process_images(self, text: str, image_handler: Optional[Callable[[Path], str]] = None) -> str:
        """Replace web image paths with absolute file system paths or custom paths via handler"""
        if not text:
            return ""
        
        def replace_match(match):
            alt = match.group(1)
            url = match.group(2)
            
            # Handle local media files
            if url.startswith('/static/media/'):
                # Remove prefix to get relative path
                rel_path = url.replace('/static/media/', '', 1)
                # settings.MEDIA_DIR is "static/media"
                file_path = settings.MEDIA_DIR / rel_path
                
                # Resolve to absolute path
                try:
                    abs_path = file_path.resolve()
                    if abs_path.exists():
                        if image_handler:
                            new_path = image_handler(abs_path)
                            return f'![{alt}]({new_path})'
                        return f'![{alt}]({abs_path.as_posix()})'
                except Exception as e:
                    logger.warning(f"Failed to resolve image path {url}: {e}")
            
            return match.group(0)

        return re.sub(r'!\[(.*?)\]\((.*?)\)', replace_match, text)

    def _format_answer(self, q: Question) -> str:
        """Format DB AnswerSpec (JSON) into human-readable Markdown."""
        return answer_spec_to_markdown(q.answer, q.options)

    def _option_text(self, opt: Dict[str, Any]) -> str:
        """Render an option's content: v2 RichDoc -> Markdown, with legacy fallback."""
        raw = opt.get('content')
        if isinstance(raw, (dict, str)) and raw:
            text = rich_doc_to_markdown(raw)
            if text:
                return text
        return str(opt.get('text', '') or "")

    def _md_to_latex(self, text: str, image_handler: Optional[Callable[[Path], str]] = None) -> str:
        """Convert markdown text to latex fragment"""
        if not text:
            return ""
        # Process images first
        text = self._process_images(text, image_handler)
        return pypandoc.convert_text(text, 'latex', format='markdown+tex_math_dollars')

    def _build_sections(
        self,
        questions: List[Question],
        section_titles: Optional[List[Optional[str]]],
    ) -> List[Dict[str, Any]]:
        """按手动 section_title 将有序题目切分为分节；无标题则合并为单一无标题节，保持提交顺序。"""
        titles = section_titles or [None] * len(questions)
        sections: List[Dict[str, Any]] = []
        current: Dict[str, Any] = {"title": None, "questions": []}
        started = False
        for q, raw_title in zip(questions, titles):
            title = (raw_title or "").strip() or None
            if title:
                if started:
                    sections.append(current)
                current = {"title": title, "questions": [q]}
                started = True
            else:
                current["questions"].append(q)
                started = True
        if current["questions"]:
            sections.append(current)
        return sections

    def generate_latex_via_jinja(self, title: str, questions: List[Question],
                                 content_position: ContentPosition = ContentPosition.AFTER_QUESTION,
                                 include_answer: bool = True, include_analysis: bool = True, 
                                 include_explanation: bool = True, include_summary: bool = True,
                                 include_source: bool = False,
                                 section_titles: Optional[List[Optional[str]]] = None,
                                 image_handler: Optional[Callable[[Path], str]] = None) -> str:
        def build_q_data(q: Question, include_details: bool = True) -> Dict[str, Any]:
            q_type = q.q_type
            if hasattr(q_type, "value"):
                q_type = q_type.value
            q_data: Dict[str, Any] = {
                "content_tex": self._md_to_latex(rich_doc_to_markdown(q.content), image_handler),
                "options_tex": [],
                "answer_tex": self._md_to_latex(self._format_answer(q), image_handler) if (include_details and include_answer) else "",
                "thinking_tex": self._md_to_latex(rich_doc_to_markdown(q.thinking), image_handler) if (include_details and include_analysis) else "",
                "analysis_tex": self._md_to_latex(rich_doc_to_markdown(q.analysis), image_handler) if (include_details and include_explanation) else "",
                "summary_tex": self._md_to_latex(rich_doc_to_markdown(q.summary), image_handler) if (include_details and include_summary) else "",
                "source_tex": self._md_to_latex(q.source, image_handler) if (include_details and include_source) else "",
                "reserve_space": q_type == QuestionType.FREE_RESPONSE.value,
            }
            if q.options:
                opts = q.options
                if isinstance(opts, str):
                    try:
                        opts = json.loads(opts)
                    except Exception:
                        pass
                if isinstance(opts, list):
                    for opt in opts:
                        # v2 option content 是 RichDoc；兼容 legacy 的 'text'/纯字符串。
                        if isinstance(opt, dict):
                            raw = opt.get('content')
                            if isinstance(raw, (dict, str)):
                                text = rich_doc_to_markdown(raw) if raw else ""
                            else:
                                text = ""
                            if not text:
                                text = str(opt.get('text', '') or "")
                        else:
                            text = str(opt)
                        q_data["options_tex"].append(self._md_to_latex(text, image_handler))
            return q_data

        raw_sections = self._build_sections(questions, section_titles)
        
        # Generate main sections (questions only or with details depending on content_position)
        include_inline_details = content_position == ContentPosition.AFTER_QUESTION
        sections = [
            {
                "title": s["title"], 
                "questions": [build_q_data(q, include_inline_details) for q in s["questions"]]
            }
            for s in raw_sections
        ]
        
        # Generate appendix if content_position is END_OF_PAPER
        appendix_sections = []
        if content_position == ContentPosition.END_OF_PAPER:
            appendix_sections = [
                {
                    "title": s["title"], 
                    "questions": [build_q_data(q, True) for q in s["questions"]]
                }
                for s in raw_sections
            ]

        template = self.jinja_env.get_template("exam_paper.tex.j2")
        return template.render(
            title=title, 
            sections=sections, 
            appendix_sections=appendix_sections,
            has_appendix=content_position == ContentPosition.END_OF_PAPER
        )

    def _append_question_details(self, md_lines: List[str], q: Question, 
                                 include_answer: bool, include_analysis: bool, 
                                 include_explanation: bool, include_summary: bool,
                                 include_source: bool):
        if include_answer and q.answer:
            formatted_answer = self._format_answer(q)
            md_lines.append(f"**【答案】** {self._process_images(formatted_answer)}")
            md_lines.append("")
        if include_analysis and q.thinking:
            md_lines.append(f"**【分析】** {self._process_images(rich_doc_to_markdown(q.thinking))}")
            md_lines.append("")
        if include_explanation and q.analysis:
            md_lines.append(f"**【解析】** {self._process_images(rich_doc_to_markdown(q.analysis))}")
            md_lines.append("")
        if include_summary and q.summary:
            md_lines.append(f"**【总结】** {self._process_images(rich_doc_to_markdown(q.summary))}")
            md_lines.append("")
        if include_source and q.source:
            md_lines.append(f"**【来源】** {self._process_images(q.source)}")
            md_lines.append("")

    def generate_markdown(self, title: str, questions: List[Question],
                          content_position: ContentPosition = ContentPosition.AFTER_QUESTION,
                          include_answer: bool = True, include_analysis: bool = True, 
                          include_explanation: bool = True, include_summary: bool = True,
                          include_source: bool = False,
                          section_titles: Optional[List[Optional[str]]] = None) -> str:
        md_lines = [f"# {title}", ""]
        sections = self._build_sections(questions, section_titles)
        
        # Generate questions section
        question_number = 1
        for section in sections:
            if section["title"]:
                md_lines.append(f"## {section['title']}")
                md_lines.append("")
            for q in section["questions"]:
                # Use bold number instead of list to avoid indentation issues
                md_lines.append(f"**{question_number}.** {self._process_images(rich_doc_to_markdown(q.content))}")
                md_lines.append("")
                question_number += 1

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
                                text = self._option_text(o)
                                # Escape dot to prevent list conversion, use double space for line break
                                md_lines.append(f"{label}\\. {self._process_images(text)}  ")
                        else:
                            for idx, opt in enumerate(opts):
                                label = chr(65 + idx)  # A, B, C...
                                text = self._option_text(opt) if isinstance(opt, dict) else str(opt)
                                md_lines.append(f"{label}\\. {self._process_images(text)}  ")
                        md_lines.append("")  # Blank line after options

                # Add details after question if position is AFTER_QUESTION
                if content_position == ContentPosition.AFTER_QUESTION:
                    self._append_question_details(
                        md_lines, q, include_answer, include_analysis, 
                        include_explanation, include_summary, include_source
                    )
                md_lines.append("")

        # Add appendix at the end if position is END_OF_PAPER
        if content_position == ContentPosition.END_OF_PAPER:
            md_lines.append("---")
            md_lines.append("")
            md_lines.append("# 参考答案与解析")
            md_lines.append("")
            
            question_number = 1
            for section in sections:
                if section["title"]:
                    md_lines.append(f"## {section['title']}")
                    md_lines.append("")
                for q in section["questions"]:
                    md_lines.append(f"**{question_number}.** ")
                    md_lines.append("")
                    question_number += 1
                    self._append_question_details(
                        md_lines, q, include_answer, include_analysis, 
                        include_explanation, include_summary, include_source
                    )
                    md_lines.append("")

        return "\n".join(md_lines)

    def generate_file(self, title: str, questions: List[Question], format: OutputFormat,
                      content_position: ContentPosition = ContentPosition.AFTER_QUESTION,
                      include_answer: bool = True, include_analysis: bool = True, 
                      include_explanation: bool = True, include_summary: bool = True,
                      include_source: bool = False,
                      section_titles: Optional[List[Optional[str]]] = None) -> str:
        logger.debug(f"Generating paper file in format: {format.value}, content_position: {content_position.value}")
        
        # When content is hidden, ignore all include flags
        if content_position == ContentPosition.HIDDEN:
            include_answer = include_analysis = include_explanation = include_summary = include_source = False
        
        if format == OutputFormat.LATEX:
            # Create a temporary directory for the build
            with tempfile.TemporaryDirectory() as tmpdirname:
                base_dir = Path(tmpdirname)
                images_dir = base_dir / "images"
                images_dir.mkdir()
                
                def latex_image_handler(src_path: Path) -> str:
                    # Copy file to images_dir
                    dst_name = src_path.name
                    # Handle duplicate names if necessary? For now assume unique names or overwrite is fine
                    shutil.copy2(src_path, images_dir / dst_name)
                    # Return relative path for latex (forward slashes)
                    return f"images/{dst_name}"

                try:
                    latex_content = self.generate_latex_via_jinja(
                        title, questions, 
                        content_position, include_answer, include_analysis, include_explanation, include_summary, include_source,
                        section_titles=section_titles,
                        image_handler=latex_image_handler
                    )
                    
                    tex_file = base_dir / f"{title}.tex"
                    with open(tex_file, 'w', encoding='utf-8') as f:
                        f.write(latex_content)
                    
                    # Create zip
                    # We want to return a persistent temp file (until cleaned up by caller)
                    zip_fd, zip_path = tempfile.mkstemp(suffix=".zip")
                    os.close(zip_fd)
                    # remove the empty temp file created by mkstemp because make_archive might complain or we overwrite
                    os.remove(zip_path)
                    
                    # make_archive appends .zip, so we strip it from base_name
                    archive_base = zip_path.replace(".zip", "")
                    
                    shutil.make_archive(archive_base, 'zip', base_dir)
                    
                    # make_archive adds .zip extension, so zip_path should be correct now if we stripped it
                    # But wait, if zip_path was /tmp/foo.zip, archive_base is /tmp/foo
                    # make_archive creates /tmp/foo.zip
                    
                    return zip_path
                except Exception as e:
                    logger.error(f"Error generating latex zip: {e}", exc_info=True)
                    raise e

        # Fallback to Pandoc for DOCX
        # Create a temp file
        suffix = f".{format.value}"
        fd, path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)

        markdown_content = self.generate_markdown(
            title, questions, content_position, include_answer, include_analysis, 
            include_explanation, include_summary, include_source, section_titles=section_titles
        )
        extra_args = ['--standalone']
        if format == OutputFormat.DOCX:
            reference_doc = os.path.join(self.template_dir, "yuanxuan-standard-math.docx")
            if os.path.exists(reference_doc):
                extra_args.append(f'--reference-doc={reference_doc}')

        try:
            pypandoc.convert_text(
                markdown_content,
                format.value,
                format='markdown+tex_math_dollars',
                outputfile=path,
                extra_args=extra_args
            )
        except Exception as e:
            # Cleanup if failed
            logger.error(f"Pandoc conversion failed: {e}", exc_info=True)
            if os.path.exists(path):
                os.remove(path)
            raise e
        
        return path

paper_generator = PaperGenerator()
