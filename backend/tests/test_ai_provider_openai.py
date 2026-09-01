"""OpenAI 兼容 provider 的 JSON 解析容错(app.services.ai_provider.OpenAIProvider)。"""

import sys
import types

import pytest

from app.services.ai_provider import OpenAIProvider


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, content):
        self._content = content

    async def create(self, **kwargs):
        return _FakeResponse(self._content)


class _FakeChat:
    def __init__(self, content):
        self.completions = _FakeCompletions(content)


class _FakeAsyncOpenAI:
    def __init__(self, response_content):
        self._content = response_content

    def __call__(self, *args, **kwargs):
        self.chat = _FakeChat(self._content)
        return self


def _install_fake_openai(monkeypatch, response_content):
    module = types.ModuleType("openai")
    module.AsyncOpenAI = _FakeAsyncOpenAI(response_content)
    monkeypatch.setitem(sys.modules, "openai", module)


@pytest.mark.parametrize(
    "response_content,expected",
    [
        # 标准包裹形态
        ('{"questions": [{"q_type": "single_choice", "content": "a"}, {"q_type": "single_choice", "content": "b"}]}', 2),
        # 裸列表
        ('[{"q_type": "single_choice", "content": "a"}]', 1),
        # 裸单题对象(dashscope/Qwen 实测会这样返回)
        ('{"q_type": "free_response", "content": "Q", "thinking": "t"}', 1),
    ],
)
async def test_openai_extract_normalizes_response_shapes(monkeypatch, response_content, expected):
    _install_fake_openai(monkeypatch, response_content)

    provider = OpenAIProvider()
    result = await provider.extract_questions("内容", None, {"API_KEY": "k"})

    assert len(result) == expected
