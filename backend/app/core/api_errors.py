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
