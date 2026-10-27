"""
Knowledge point batch import service.

Handles Excel template generation, preflight checks (for the rebuild mode),
and importing an .xlsx file into the knowledge point tree.
"""
import asyncio
import time
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.crud_knowledge_point import knowledge_point as crud_kp
from app.core.vector_store import VectorStore
from app.models.knowledge_point import KnowledgePoint
from app.models.question import question_knowledge_points
from app.models.subject import Subject
from app.services import excel_import
from app.services.excel_import import MissingColumnsError, clean as _clean, text as _t
from app.schemas.knowledge_point import (
    KPImportPreflight,
    KPImportResult,
    KPImportRowError,
)

LEVEL_KEYS = [f"level_{i}" for i in range(1, excel_import.KP_LEVELS + 1)]


def generate_template() -> bytes:
    """Generate the .xlsx import template in the request locale."""
    return excel_import.generate_template(excel_import.KP_SCHEMA)


async def preflight(db: AsyncSession, subject_id: int) -> Optional[KPImportPreflight]:
    """
    Impact assessment for the rebuild mode: how many knowledge points exist and
    how many distinct questions are linked to them.
    """
    subject = await db.get(Subject, subject_id)
    if not subject:
        return None

    existing = await db.execute(
        select(func.count(KnowledgePoint.id)).where(
            KnowledgePoint.subject_id == subject_id
        )
    )
    existing_count = existing.scalar_one()

    affected = await db.execute(
        select(func.count(func.distinct(question_knowledge_points.c.question_id)))
        .select_from(question_knowledge_points)
        .join(
            KnowledgePoint,
            KnowledgePoint.id == question_knowledge_points.c.knowledge_point_id,
        )
        .where(KnowledgePoint.subject_id == subject_id)
    )
    affected_questions = affected.scalar_one()

    return KPImportPreflight(
        subject_id=subject_id,
        subject_name=subject.name,
        existing_count=existing_count,
        affected_questions=affected_questions,
    )


async def import_excel(
    db: AsyncSession,
    *,
    file_bytes: bytes,
    mode: str,
    user_id: Optional[int] = None,
) -> KPImportResult:
    """
    Import knowledge points from an .xlsx file.

    mode = "incremental": skip existing nodes, create new ones.
    mode = "rebuild": clear the target subject(s) first, then import.
    """
    started = time.perf_counter()

    try:
        df = excel_import.read_rows(file_bytes, excel_import.KP_SCHEMA)
    except MissingColumnsError as e:
        return KPImportResult(
            status="failed",
            mode=mode,
            errors=[KPImportRowError(row=0, message=excel_import.missing_columns_message(e))],
        )

    # Cache subjects by name and slug for fast lookup.
    subjects_result = await db.execute(select(Subject))
    subjects = subjects_result.scalars().all()
    subject_by_key: Dict[str, Subject] = {}
    for s in subjects:
        subject_by_key[s.name.strip()] = s
        subject_by_key[s.slug.strip()] = s

    errors: List[KPImportRowError] = []
    # Parsed valid rows: (subject, [path parts]). Also track which subjects are touched.
    parsed: List[Tuple[Subject, List[str]]] = []
    touched_subject_ids: set = set()

    for idx, row in df.iterrows():
        excel_row = int(idx) + 2  # +1 header, +1 for 1-based
        subject_name = _clean(row.get("subject"))
        if not subject_name:
            errors.append(KPImportRowError(row=excel_row, message=_t("knowledge_point.err.subject_required")))
            continue
        subject = subject_by_key.get(subject_name)
        if not subject:
            errors.append(KPImportRowError(
                row=excel_row, message=_t("knowledge_point.err.subject_not_found", subject=subject_name)
            ))
            continue

        path = [p for p in (_clean(row.get(c)) for c in LEVEL_KEYS) if p]
        if not path:
            errors.append(KPImportRowError(row=excel_row, message=_t("knowledge_point.err.level_1_required")))
            continue

        parsed.append((subject, path))
        touched_subject_ids.add(subject.id)

    subject_name_out = None
    if len(touched_subject_ids) == 1:
        only_id = next(iter(touched_subject_ids))
        subject_name_out = next(s.name for s in subjects if s.id == only_id)

    # Rebuild mode: clear touched subjects up-front.
    if mode == "rebuild":
        for sid in touched_subject_ids:
            await crud_kp.clear_by_subject(db, subject_id=sid)

    # Build an in-memory cache of existing nodes keyed by (subject_id, parent_id, name).
    # After a rebuild the subject is empty, so this naturally starts fresh.
    cache: Dict[Tuple[int, Optional[int], str], int] = {}
    used_slugs_by_subject: Dict[int, set] = {}
    for sid in touched_subject_ids:
        existing = await crud_kp.get_by_subject(db, subject_id=sid, limit=None)
        used = set()
        for kp in existing:
            cache[(kp.subject_id, kp.parent_id, kp.name)] = kp.id
            used.add(kp.slug)
        used_slugs_by_subject[sid] = used

    created = 0
    skipped = 0
    new_ids: List[int] = []

    for subject, path in parsed:
        parent_id: Optional[int] = None
        row_created_any = False
        for name in path:
            key = (subject.id, parent_id, name)
            if key in cache:
                parent_id = cache[key]
                continue
            slug = await crud_kp.make_unique_slug(
                db, subject.id, name, used_slugs_by_subject[subject.id]
            )
            created_objs = await crud_kp.create_batch(
                db,
                nodes=[{
                    "name": name,
                    "slug": slug,
                    "subject_id": subject.id,
                    "parent_id": parent_id,
                }],
                user_id=user_id,
            )
            new_kp = created_objs[0]
            cache[key] = new_kp.id
            new_ids.append(new_kp.id)
            parent_id = new_kp.id
            created += 1
            row_created_any = True
        if not row_created_any:
            skipped += 1

    # Batch vectorization (only if embedding configured; otherwise deferred).
    vector_synced = False
    if new_ids and VectorStore.is_available():
        try:
            items = []
            for kp_id in new_ids:
                kp = await crud_kp.get(db, kp_id)
                if not kp:
                    continue
                path_text = await crud_kp._build_path_text(db, kp)
                items.append({
                    "id": kp.id,
                    "text": path_text,
                    "metadata": {
                        "id": kp.id,
                        "subject_id": kp.subject_id,
                        "name": kp.name,
                        "slug": kp.slug,
                    },
                })
            await asyncio.to_thread(VectorStore.upsert_knowledge_points_batch, items)
            vector_synced = True
        except Exception as e:
            print(f"Batch vectorization failed (can reindex manually later): {e}")

    total = len(parsed) + len(errors)
    if errors and created == 0 and skipped == 0:
        status = "failed"
    elif errors:
        status = "partial"
    else:
        status = "success"

    return KPImportResult(
        status=status,
        subject_name=subject_name_out,
        mode=mode,
        created=created,
        skipped=skipped,
        failed=len(errors),
        total=total,
        duration=round(time.perf_counter() - started, 2),
        vector_synced=vector_synced,
        errors=errors,
    )
