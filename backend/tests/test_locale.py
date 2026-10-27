"""请求语言解析与 AI 提示词的输出语言指令。"""
import pytest

from app.core.locale import (
    DEFAULT_LOCALE,
    LocaleMiddleware,
    get_locale,
    normalize_locale,
    parse_accept_language,
    set_locale,
)
from app.services.importing.prompt import PromptBuilder
from app.services.prompt_utils import apply_output_language
from app.services.prompts import CHAT_SYSTEM_PROMPT, get_default_prompt


@pytest.mark.parametrize(
    "header, expected",
    [
        (None, DEFAULT_LOCALE),
        ("", DEFAULT_LOCALE),
        ("en-US", "en-US"),
        ("en", "en-US"),
        ("en-GB,en;q=0.8", "en-US"),
        ("zh-CN", "zh-CN"),
        ("zh-TW,zh;q=0.9", "zh-CN"),
        ("fr-FR,en;q=0.5", "en-US"),
        ("en;q=0.2,zh;q=0.9", "zh-CN"),
        ("fr-FR", DEFAULT_LOCALE),
        ("*", DEFAULT_LOCALE),
        ("en;q=0", DEFAULT_LOCALE),
    ],
)
def test_parse_accept_language(header, expected):
    assert parse_accept_language(header) == expected


def test_normalize_locale_handles_underscore_and_unknown():
    assert normalize_locale("en_US") == "en-US"
    assert normalize_locale("ja-JP") == DEFAULT_LOCALE
    assert normalize_locale(None) == DEFAULT_LOCALE


def test_chat_directive_names_target_language():
    prompt = apply_output_language("base", "chat", "en-US")
    assert prompt.startswith("base")
    assert "Reply to the user in English" in prompt
    assert "Simplified Chinese" in apply_output_language("base", "chat", "zh-CN")


def test_extract_directive_never_translates_regardless_of_locale():
    assert apply_output_language("base", "extract", "en-US") == apply_output_language(
        "base", "extract", "zh-CN"
    )
    assert "never translate" in apply_output_language("base", "extract", "en-US")


def test_placeholder_is_replaced_in_place_not_appended():
    prompt = apply_output_language("a\n{output_language}\nb", "solve", "en-US")
    assert prompt.startswith("a\n## Output language")
    assert prompt.endswith("\nb")
    assert "{output_language}" not in prompt


def test_default_prompts_declare_the_placeholder():
    assert "{output_language}" in get_default_prompt("AI_EXTRACT_PROMPT")
    assert "{output_language}" in get_default_prompt("AI_SOLVE_PROMPT")
    assert "{output_language}" not in CHAT_SYSTEM_PROMPT


async def test_prompt_builder_solve_follows_current_locale(db_session):
    set_locale("en-US")
    try:
        prompt = await PromptBuilder().build(db_session, mode="solve", subject_id=None)
    finally:
        set_locale(None)
    assert "in English" in prompt
    assert "{output_language}" not in prompt
    assert prompt.rstrip().endswith("```")


async def test_middleware_sets_locale_from_header():
    seen = []

    async def inner(scope, receive, send):
        seen.append(get_locale())

    middleware = LocaleMiddleware(inner)
    for headers in ([(b"accept-language", b"en-US,en;q=0.9")], []):
        await middleware({"type": "http", "headers": headers}, None, None)
    assert seen == ["en-US", "zh-CN"]


def test_app_registers_locale_middleware():
    from app.main import app

    assert any(m.cls is LocaleMiddleware for m in app.user_middleware)
