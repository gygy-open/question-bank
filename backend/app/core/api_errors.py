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
    # composition
    COMPOSITION_NOT_FOUND = "composition.not_found"
    COMPOSITION_FOLDER_NOT_FOUND = "composition.folder_not_found"
    COMPOSITION_PARENT_FOLDER_NOT_FOUND = "composition.parent_folder_not_found"
    COMPOSITION_NODE_NOT_FOUND = "composition.node_not_found"
    COMPOSITION_SUBJECT_NOT_FOUND = "composition.subject_not_found"
    COMPOSITION_FOLDER_SELF_PARENT = "composition.folder_self_parent"
    COMPOSITION_FOLDER_CYCLE = "composition.folder_cycle"
    COMPOSITION_FOLDER_NOT_EMPTY = "composition.folder_not_empty"
    COMPOSITION_REVISION_MISMATCH = "composition.revision_mismatch"
    COMPOSITION_FINALIZE_DELETED = "composition.finalize_deleted"
    COMPOSITION_VERSION_CONFLICT = "composition.version_conflict"
    COMPOSITION_SCORING_REQUIRES_NUMBERING = "composition.scoring_requires_numbering"
    COMPOSITION_QUESTION_UNAVAILABLE = "composition.question_unavailable"
    COMPOSITION_QUESTION_OTHER_SUBJECT = "composition.question_other_subject"
    COMPOSITION_PRIVATE_QUESTION_IN_SHARED = "composition.private_question_in_shared"
    COMPOSITION_QUESTION_NEEDS_GROUP = "composition.question_needs_group"
    COMPOSITION_STIMULUS_UNAVAILABLE = "composition.stimulus_unavailable"
    COMPOSITION_PRIVATE_STIMULUS = "composition.private_stimulus"
    # ai_config
    AI_CONFIG_ACTIVE_ID_INVALID = "ai_config.active_id_invalid"
    AI_CONFIG_ACTIVE_MODEL_NOT_FOUND = "ai_config.active_model_not_found"
    AI_CONFIG_GLOBAL_PROVIDER_ONLY = "ai_config.global_provider_only"
    AI_CONFIG_NOT_EMBEDDING_MODEL = "ai_config.not_embedding_model"
    AI_CONFIG_EMBEDDING_NOT_FOR_TEXT_VISION = "ai_config.embedding_not_for_text_vision"
    AI_CONFIG_EMBEDDING_NOT_FOR_TEXT = "ai_config.embedding_not_for_text"
    AI_CONFIG_MODEL_NO_VISION = "ai_config.model_no_vision"
    AI_CONFIG_IN_USE_CONFIRM = "ai_config.in_use_confirm"
    AI_CONFIG_PROVIDER_NOT_FOUND = "ai_config.provider_not_found"
    AI_CONFIG_MODEL_NOT_FOUND = "ai_config.model_not_found"
    AI_CONFIG_PROVIDER_IN_USE = "ai_config.provider_in_use"
    AI_CONFIG_MODEL_IN_USE = "ai_config.model_in_use"
    AI_CONFIG_UNSUPPORTED_INTERFACE = "ai_config.unsupported_interface"
    AI_CONFIG_PROVIDER_NAME_TAKEN = "ai_config.provider_name_taken"
    AI_CONFIG_API_KEY_REQUIRED = "ai_config.api_key_required"
    AI_CONFIG_INTERFACE_AND_KEY_REQUIRED = "ai_config.interface_and_key_required"
    AI_CONFIG_MODEL_NAME_REQUIRED = "ai_config.model_name_required"
    AI_CONFIG_MODEL_NAME_TAKEN = "ai_config.model_name_taken"
    AI_CONFIG_EMBEDDING_FLAG_LOCKED = "ai_config.embedding_flag_locked"
    AI_CONFIG_CANNOT_BECOME_EMBEDDING = "ai_config.cannot_become_embedding"
    AI_CONFIG_VISION_FLAG_LOCKED = "ai_config.vision_flag_locked"
    AI_CONFIG_MODEL_UNUSABLE = "ai_config.model_unusable"
    AI_CONFIG_MODEL_PURPOSE_UNSUPPORTED = "ai_config.model_purpose_unsupported"
    AI_CONFIG_API_KEY_UNDECRYPTABLE = "ai_config.api_key_undecryptable"
    # chat
    CHAT_SESSION_NOT_FOUND = "chat.session_not_found"
    CHAT_MODEL_UNUSABLE = "chat.model_unusable"
    CHAT_RUN_NOT_FOUND = "chat.run_not_found"
    CHAT_TICKET_NOT_PENDING = "chat.ticket_not_pending"
    CHAT_MESSAGE_NOT_FOUND = "chat.message_not_found"
    # prompt
    PROMPT_TEMPLATE_NOT_FOUND = "prompt.template_not_found"
    PROMPT_UNKNOWN_KEY = "prompt.unknown_key"
    PROMPT_SUBJECT_NOT_FOUND = "prompt.subject_not_found"


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
