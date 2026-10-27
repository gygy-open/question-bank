"""带错误码的 HTTP 异常。

响应体保持向后兼容:``{"detail": "<原文>", "code": "<错误码>", "params": {...}}``。
``detail`` 作为未迁移客户端和日志的回退;前端优先按 ``code`` 翻译(``apiErrors.<code>``),
并用 ``params`` 做插值。新增错误码必须同步在 ``frontend/i18n/locales/zh-CN.json``
的 ``apiErrors`` 下登记(tests/test_api_error_codes.py 会校验)。
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any, Dict, Optional

from fastapi import HTTPException


class ErrorCode(StrEnum):
    # auth
    AUTH_INVALID_CREDENTIALS = "auth.invalid_credentials"
    AUTH_INACTIVE_PENDING = "auth.inactive_pending"
    AUTH_TOKEN_INVALID = "auth.token_invalid"
    AUTH_USER_NOT_FOUND = "auth.user_not_found"
    AUTH_NOT_AUTHENTICATED = "auth.not_authenticated"
    AUTH_INACTIVE_USER = "auth.inactive_user"
    AUTH_FORBIDDEN = "auth.forbidden"
    AUTH_REGISTRATION_CLOSED = "auth.registration_closed"
    AUTH_USERNAME_TAKEN = "auth.username_taken"
    # setup
    SETUP_MYSQL_REQUIRED = "setup.mysql_required"
    SETUP_CONNECTION_FAILED = "setup.connection_failed"
    SETUP_MIGRATION_FAILED = "setup.migration_failed"
    SETUP_DB_ALREADY_CONFIGURED = "setup.db_already_configured"
    SETUP_DB_NOT_CONFIGURED = "setup.db_not_configured"
    SETUP_USERNAME_REQUIRED = "setup.username_required"
    SETUP_ADMIN_INITIALIZED = "setup.admin_initialized"
    SETUP_USERNAME_EXISTS = "setup.username_exists"
    # upload
    UPLOAD_SUBJECT_NOT_FOUND = "upload.subject_not_found"
    UPLOAD_FILE_REQUIRED = "upload.file_required"
    UPLOAD_ONLY_DOCX = "upload.only_docx"
    UPLOAD_ONLY_MARKDOWN = "upload.only_markdown"
    UPLOAD_ONLY_ZIP = "upload.only_zip"
    UPLOAD_ONLY_IMAGE = "upload.only_image"
    # paper_import
    PAPER_IMPORT_GROUP_DUPLICATE_MEMBER = "paper_import.group_duplicate_member"
    PAPER_IMPORT_GROUP_EMPTY = "paper_import.group_empty"
    PAPER_IMPORT_GROUP_MEMBER_MISSING = "paper_import.group_member_missing"
    PAPER_IMPORT_GROUP_STIMULUS_MISSING = "paper_import.group_stimulus_missing"
    PAPER_IMPORT_GROUP_TEMP_ID_DUPLICATE = "paper_import.group_temp_id_duplicate"
    PAPER_IMPORT_GROUP_TEMP_ID_MISSING = "paper_import.group_temp_id_missing"
    PAPER_IMPORT_GROUP_VISIBILITY_CONFLICT = "paper_import.group_visibility_conflict"
    PAPER_IMPORT_NOTHING_TO_IMPORT = "paper_import.nothing_to_import"
    PAPER_IMPORT_NO_QUESTIONS = "paper_import.no_questions"
    PAPER_IMPORT_NONE_IMPORTABLE = "paper_import.none_importable"
    PAPER_IMPORT_OUTLINE_CONVERT_FAILED = "paper_import.outline_convert_failed"
    PAPER_IMPORT_OUTLINE_GROUP_MISSING = "paper_import.outline_group_missing"
    PAPER_IMPORT_OUTLINE_QUESTION_MISSING = "paper_import.outline_question_missing"
    PAPER_IMPORT_PARTIAL_SKIPPED = "paper_import.partial_skipped"
    PAPER_IMPORT_PRIVATE_IN_SHARED = "paper_import.private_in_shared"
    PAPER_IMPORT_QUESTION_IN_MULTIPLE_GROUPS = "paper_import.question_in_multiple_groups"
    PAPER_IMPORT_QUESTION_TEMP_ID_DUPLICATE = "paper_import.question_temp_id_duplicate"
    PAPER_IMPORT_RELATION_CYCLE = "paper_import.relation_cycle"
    PAPER_IMPORT_RELATION_PARENT_MISSING = "paper_import.relation_parent_missing"
    PAPER_IMPORT_RELATION_SELF = "paper_import.relation_self"
    PAPER_IMPORT_STIMULUS_INVALID = "paper_import.stimulus_invalid"
    PAPER_IMPORT_STIMULUS_TEMP_ID_DUPLICATE = "paper_import.stimulus_temp_id_duplicate"
    PAPER_IMPORT_STIMULUS_TEMP_ID_MISSING = "paper_import.stimulus_temp_id_missing"
    PAPER_IMPORT_SUBJECT_MISMATCH = "paper_import.subject_mismatch"
    # import_task
    IMPORT_TASK_NO_FILES = "import_task.no_files"
    IMPORT_TASK_SUBJECT_REQUIRED = "import_task.subject_required"
    IMPORT_TASK_NO_VALID_FILES = "import_task.no_valid_files"
    IMPORT_TASK_NOT_FOUND = "import_task.not_found"
    IMPORT_TASK_FORBIDDEN = "import_task.forbidden"
    IMPORT_TASK_ALREADY_FINISHED = "import_task.already_finished"
    IMPORT_TASK_NOT_RETRYABLE = "import_task.not_retryable"
    IMPORT_TASK_SOURCE_UNAVAILABLE = "import_task.source_unavailable"


class ApiError(HTTPException):
    def __init__(
        self,
        status_code: int,
        code: ErrorCode,
        detail: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = str(code)
        self.params = params
