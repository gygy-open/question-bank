"""
User batch import service.

Generates the Excel import template and imports an .xlsx file of users,
validating each row and returning a per-row result.
"""
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.crud_user import user as crud_user
from app.models.user import User
from app.services import excel_import
from app.services.excel_import import MissingColumnsError, clean as _clean, text as _t
from app.schemas.user import UserCreate, UserImportResult, UserImportRowError

MIN_PASSWORD_LENGTH = 6


def generate_template() -> bytes:
    """Generate the .xlsx user import template in the request locale."""
    return excel_import.generate_template(excel_import.USER_SCHEMA)


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in excel_import.TRUE_VALUES


async def import_excel(
    db: AsyncSession,
    *,
    file_bytes: bytes,
) -> UserImportResult:
    """Import users from an .xlsx file, validating each row."""
    try:
        df = excel_import.read_rows(file_bytes, excel_import.USER_SCHEMA)
    except MissingColumnsError as e:
        return UserImportResult(
            status="failed",
            errors=[UserImportRowError(row=0, message=excel_import.missing_columns_message(e))],
        )

    total = len(df)

    # Cache existing usernames for fast duplicate detection.
    existing_result = await db.execute(select(User.username))
    existing_usernames = {u for (u,) in existing_result.all()}

    errors: List[UserImportRowError] = []
    seen_in_file: set = set()
    created = 0

    for idx, row in df.iterrows():
        excel_row = int(idx) + 2  # +1 header, +1 for 1-based
        username = _clean(row.get("username"))
        full_name = _clean(row.get("full_name"))
        password = _clean(row.get("password"))
        has_role_col = "admin" in df.columns
        is_superuser = _is_truthy(_clean(row.get("admin"))) if has_role_col else False

        if not username:
            errors.append(UserImportRowError(row=excel_row, message=_t("user.err.username_required")))
            continue
        if not full_name:
            errors.append(UserImportRowError(row=excel_row, message=_t("user.err.full_name_required")))
            continue
        if not password:
            errors.append(UserImportRowError(row=excel_row, message=_t("user.err.password_required")))
            continue
        if len(password) < MIN_PASSWORD_LENGTH:
            errors.append(UserImportRowError(
                row=excel_row, message=_t("user.err.password_too_short", min=MIN_PASSWORD_LENGTH)
            ))
            continue
        if username in seen_in_file:
            errors.append(UserImportRowError(
                row=excel_row, message=_t("user.err.duplicate_in_file", username=username)
            ))
            continue
        if username in existing_usernames:
            errors.append(UserImportRowError(
                row=excel_row, message=_t("user.err.exists", username=username)
            ))
            continue

        await crud_user.create(
            db,
            obj_in=UserCreate(
                username=username,
                full_name=full_name,
                password=password,
                is_active=True,
                is_superuser=is_superuser,
            ),
        )
        seen_in_file.add(username)
        existing_usernames.add(username)
        created += 1

    failed = len(errors)
    if created == 0 and failed > 0:
        status = "failed"
    elif failed > 0:
        status = "partial"
    else:
        status = "success"

    return UserImportResult(
        status=status, created=created, failed=failed, total=total, errors=errors
    )
