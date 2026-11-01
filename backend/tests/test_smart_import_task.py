"""智能导入补登导入记录的测试（不连接数据库）。

动机：`/upload/*` 以前只把结果放进响应体，库里什么都不留，响应里的 `task_id` 是
随机 uuid，拿它去 `GET /imports/{id}` 永远 404。补一条真实任务行之后，这次导入
可追溯，且 `content_sha256` 使同文件重复导入的提示真正生效。
"""
import json
from types import SimpleNamespace

import pytest

from app.api.v1.endpoints.upload import _record_import_task
from app.models.import_task import ImportTaskStatus


class _StubDB:
    def __init__(self):
        self.added = []
        self.flushed = 0

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushed += 1
        for obj in self.added:          # 模拟数据库分配自增主键
            if getattr(obj, "id", None) is None:
                obj.id = 42


@pytest.fixture()
def stub():
    return _StubDB()


USER = SimpleNamespace(id=7)


def _run(coro):
    import asyncio
    return asyncio.run(coro)


def test_records_a_completed_task(stub):
    result = {"questions": [{"content": "x"}], "stimuli": []}

    _run(_record_import_task(
        stub, USER,
        subject_id=1, filename="book.md", sha256="a" * 64,
        file_type="markdown", mode="extract", result=result,
    ))

    assert len(stub.added) == 1
    task = stub.added[0]
    assert task.status == ImportTaskStatus.COMPLETED
    assert task.source == "smart_upload"
    assert task.file_type == "markdown"
    assert task.mode == "extract"
    assert task.subject_id == 1
    assert task.user_id == 7


def test_result_carries_the_real_task_id(stub):
    """以前响应里的 task_id 是 uuid、库里没有；现在多一个真实整数 id。"""
    result = {"questions": []}

    _run(_record_import_task(
        stub, USER,
        subject_id=None, filename="t.md", sha256="b" * 64,
        file_type="markdown", mode="extract", result=result,
    ))

    assert result["import_task_id"] == 42


def test_content_sha256_enables_duplicate_hint(stub):
    """智能导入此前从不建任务，`_attach_duplicate_hint` 按 sha256 查永远查不到。"""
    _run(_record_import_task(
        stub, USER,
        subject_id=None, filename="t.md", sha256="c" * 64,
        file_type="markdown", mode="extract", result={},
    ))

    assert stub.added[0].content_sha256 == "c" * 64
    assert stub.added[0].source_sha256 == "c" * 64


def test_result_summary_counts(stub):
    result = {"questions": [1, 2, 3], "stimuli": [1]}

    _run(_record_import_task(
        stub, USER,
        subject_id=None, filename="t.md", sha256="d" * 64,
        file_type="markdown", mode="solve", result=result,
    ))

    summary = json.loads(stub.added[0].result_summary)
    assert summary == {"questions": 3, "stimuli": 1}
    assert stub.added[0].mode == "solve"


def test_long_filename_is_truncated(stub):
    _run(_record_import_task(
        stub, USER,
        subject_id=None, filename="x" * 400, sha256=None,
        file_type="markdown", mode="extract", result={},
    ))

    assert len(stub.added[0].original_filename) == 255


def test_missing_filename_gets_a_placeholder(stub):
    _run(_record_import_task(
        stub, USER,
        subject_id=None, filename=None, sha256=None,
        file_type="image", mode="extract", result={},
    ))

    assert stub.added[0].original_filename == "smart-import"


def test_no_sha256_is_allowed(stub):
    """文本粘贴与图片识别没有源文件对象，sha256 为空也必须能登记。"""
    _run(_record_import_task(
        stub, USER,
        subject_id=None, filename="paste", sha256=None,
        file_type="markdown", mode="extract", result={},
    ))

    assert stub.added[0].content_sha256 is None
    assert stub.flushed == 1
