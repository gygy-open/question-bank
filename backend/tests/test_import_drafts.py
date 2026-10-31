"""智能导入草稿的存取与 TTL。

背景:`/upload/*` 把整篇原文交给模型,结果只放在响应体里,库里什么都不留。实测 786
题整本抽取约 268 秒,期间刷新或关页,浏览器中断请求,结果无人接收也无可恢复痕迹。
草稿让这段结果跨过刷新/关页存活。
"""
import json
import os
import time
import uuid

import pytest

from app.core import storage
from app.services import import_drafts


def _staging(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    return staging / uuid.uuid4().hex


@pytest.fixture()
def draft_store(tmp_path, monkeypatch):
    """把草稿根目录指到临时目录,避免污染真实存储。"""
    monkeypatch.setattr(storage, "_drafts_root", lambda: tmp_path / "import-drafts")
    monkeypatch.setattr(storage, "_objects_root", lambda: tmp_path / "objects")
    monkeypatch.setattr(storage, "_staging_file", lambda: _staging(tmp_path))
    return tmp_path / "import-drafts"


def test_save_then_load_roundtrip(draft_store):
    payload = {"questions": [{"content": "1+1=?", "answer": "2"}], "stimuli": []}
    draft_id = import_drafts.save_draft(payload)

    assert len(draft_id) == 64
    assert import_drafts.load_draft(draft_id) == payload


def test_same_content_reuses_one_draft(draft_store):
    payload = {"questions": [{"content": "同一份", "answer": "1"}]}
    first = import_drafts.save_draft(payload)
    second = import_drafts.save_draft(payload)

    assert first == second
    assert len(list(draft_store.glob("*/*"))) == 1


def test_unknown_draft_returns_none(draft_store):
    assert import_drafts.load_draft("0" * 64) is None
    assert import_drafts.load_draft(None) is None
    assert import_drafts.load_draft("") is None


def test_invalid_key_is_rejected_not_silently_read(draft_store):
    # 路径穿越/非法 key 不能读到任何东西
    assert import_drafts.load_draft("../../etc/passwd") is None


def test_delete_removes_draft(draft_store):
    draft_id = import_drafts.save_draft({"questions": []})
    import_drafts.delete_draft_id(draft_id)

    assert import_drafts.load_draft(draft_id) is None
    import_drafts.delete_draft_id(draft_id)  # 重复删除不报错
    import_drafts.delete_draft_id(None)


def test_attach_draft_adds_id(draft_store):
    result = import_drafts.attach_draft({"questions": [{"content": "x"}]})

    assert "draft_id" in result
    restored = import_drafts.load_draft(result["draft_id"])
    assert restored is not None
    assert restored["questions"][0]["content"] == "x"


def test_oversized_draft_is_refused(draft_store, monkeypatch):
    monkeypatch.setattr(import_drafts, "DRAFT_MAX_BYTES", 32)
    with pytest.raises(import_drafts.DraftTooLarge):
        import_drafts.save_draft({"questions": [{"content": "x" * 100}]})


def test_attach_draft_keeps_response_when_payload_too_large(draft_store, monkeypatch):
    """存不下草稿不能连带把导入搞失败——响应体本身仍然有结果。"""
    monkeypatch.setattr(import_drafts, "DRAFT_MAX_BYTES", 32)
    result = import_drafts.attach_draft({"questions": [{"content": "x" * 100}]})

    assert "draft_id" not in result
    assert result["questions"][0]["content"].startswith("xxx")


def test_expired_drafts_are_swept(draft_store):
    draft_id = import_drafts.save_draft({"questions": []})
    path = storage.draft_path(draft_id)

    stale = time.time() - import_drafts.DRAFT_TTL_SECONDS - 60
    os.utime(path, (stale, stale))

    import_drafts.save_draft({"questions": [{"content": "新草稿"}]})
    assert not path.exists()


def test_fresh_drafts_survive_sweep(draft_store):
    draft_id = import_drafts.save_draft({"questions": [{"content": "还在"}]})
    import_drafts.save_draft({"questions": [{"content": "另一个"}]})

    assert import_drafts.load_draft(draft_id) is not None


def test_drafts_are_stored_outside_media_objects(draft_store):
    """草稿不能写进 objects,否则 media_gc 会把它当孤儿对象删掉。"""
    draft_id = import_drafts.save_draft({"questions": []})

    assert storage.draft_path(draft_id).is_file()
    assert not storage.exists(draft_id)


def test_unicode_roundtrip(draft_store):
    payload = {"questions": [{"content": "已知 $\\dfrac{1}{2}$，求值。", "answer": "略"}]}
    draft_id = import_drafts.save_draft(payload)
    raw = json.loads(storage.read_draft(draft_id).decode("utf-8"))

    assert raw["questions"][0]["content"] == payload["questions"][0]["content"]
