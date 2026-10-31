"""两阶段抽取的降级路径测试。

两阶段的全部风险都在"该降级却没降级"上：多切一条会让后面的答案整体错位，
少切一条会静默丢题。这里逐条钉住降级条件，不连数据库、不连模型。
"""
import asyncio

import pytest

from app.services.importing import two_phase
from app.services.importing.contracts import ExtractionResult
from app.services.importing.two_phase import MIN_Q, TwoPhaseExtractor, _options_to_list


class _StubFallback:
    """记录被调用的原始抽取器替身。"""

    def __init__(self):
        self.calls = 0
        self.last_kwargs = None

    async def extract(self, content, db, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        return ExtractionResult(questions=[{"id": "fallback"}], stimuli=[], question_groups=[], paper=None)


class _StubEnricher:
    async def enrich(self, questions, **kwargs):
        return None


def _extractor():
    ex = object.__new__(TwoPhaseExtractor)
    ex._fallback = _StubFallback()
    ex.enricher = _StubEnricher()
    return ex


def _plain_doc(n):
    return "\n".join(f"{i}. 第 {i} 题的题干，求值。" for i in range(1, n + 1))


def _run(coro):
    return asyncio.run(coro)


def test_mode_solve_falls_back():
    ex = _extractor()
    _run(ex.extract(_plain_doc(MIN_Q + 5), db=None, mode="solve"))
    assert ex._fallback.calls == 1
    assert ex._fallback.last_kwargs["mode"] == "solve"


def test_image_input_falls_back():
    ex = _extractor()
    _run(ex.extract("ignored", db=None, image_data=b"\x89PNG", mode="extract"))
    assert ex._fallback.calls == 1
    assert ex._fallback.last_kwargs["image_data"] == b"\x89PNG"


@pytest.mark.parametrize(
    "marker",
    ["【题目材料】材料一", "【题组】第一组", "本卷满分 120 分", "考试时间 120 分钟"],
)
def test_whole_paper_document_falls_back(marker):
    ex = _extractor()
    _run(ex.extract(marker + "\n" + _plain_doc(MIN_Q + 5), db=None, mode="extract"))
    assert ex._fallback.calls == 1


def test_too_few_segments_falls_back():
    ex = _extractor()
    _run(ex.extract(_plain_doc(MIN_Q - 1), db=None, mode="extract"))
    assert ex._fallback.calls == 1


def test_ord_gap_falls_back(monkeypatch):
    """AI 少回一条时必须降级，不能让后面的答案按 ord 错位对齐。"""
    ex = _extractor()

    async def fake_resolve(db, is_vision=False, user_id=None):
        return "openai", {}

    async def fake_ask(segments, config):
        n = len(segments)
        # 故意漏掉第 7 条
        return [{"ord": i, "answer": None} for i in range(1, n + 1) if i != 7]

    monkeypatch.setattr(
        "app.services.importing.provider_config.resolve_active_provider", fake_resolve
    )
    monkeypatch.setattr(ex, "_ask_answers_batched", fake_ask)

    _run(ex.extract(_plain_doc(MIN_Q + 5), db=None, mode="extract"))
    assert ex._fallback.calls == 1


def test_ord_order_in_list_does_not_matter(monkeypatch):
    """返回顺序无所谓：对齐只认 ord 值，不认列表位置。"""
    ex = _extractor()

    async def fake_resolve(db, is_vision=False, user_id=None):
        return "openai", {}

    async def fake_ask(segments, config):
        n = len(segments)
        items = [{"ord": i, "answer": None} for i in range(1, n + 1)]
        items[0], items[1] = items[1], items[0]
        return items

    monkeypatch.setattr(
        "app.services.importing.provider_config.resolve_active_provider", fake_resolve
    )
    monkeypatch.setattr(ex, "_ask_answers_batched", fake_ask)
    monkeypatch.setattr(two_phase, "get_ai_provider", lambda name: object())

    _run(ex.extract(_plain_doc(MIN_Q + 5), db=None, mode="extract"))
    assert ex._fallback.calls == 0


def test_ord_complete_does_not_fall_back(monkeypatch):
    """反向用例：ord 齐全时必须走两阶段，避免降级条件写得过宽。"""
    ex = _extractor()

    async def fake_resolve(db, is_vision=False, user_id=None):
        return "openai", {}

    async def fake_ask(segments, config):
        return [{"ord": i, "answer": "B"} for i in range(1, len(segments) + 1)]

    monkeypatch.setattr(
        "app.services.importing.provider_config.resolve_active_provider", fake_resolve
    )
    monkeypatch.setattr(ex, "_ask_answers_batched", fake_ask)
    monkeypatch.setattr(two_phase, "get_ai_provider", lambda name: object())

    result = _run(ex.extract(_plain_doc(MIN_Q + 5), db=None, mode="extract"))
    assert ex._fallback.calls == 0
    assert len(result.questions) == MIN_Q + 5


@pytest.mark.parametrize(
    "block,expected",
    [
        ("A. 甲\nB. 乙\nC. 丙\nD. 丁", 4),
        ("A. 甲\nB. 乙\nC. 丙", 3),
        ("A. 甲\nC. 丙", 0),          # 不连续 → 整块丢弃
        ("B. 乙\nC. 丙", 0),          # 不从 A 开始 → 整块丢弃
        ("", 0),
    ],
)
def test_option_contiguity_required(block, expected):
    assert len(_options_to_list(block)) == expected
