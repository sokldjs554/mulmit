"""Collect: adapter → ``documents`` (idempotent upsert keyed by (source, external_id)).

A document is re-processed only when its content hash changes (e.g. a 정정공고 edits a notice),
so hourly syncs over overlapping windows are cheap and safe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mulmit.db.models import Document, IngestRun, Source
from mulmit.log import get_logger
from mulmit.runtime import Runtime
from mulmit.sources.base import FetchWindow, RawRecord, SourceAdapter
from mulmit.storage import store_raw

log = get_logger(__name__)


@dataclass(slots=True)
class IngestStats:
    fetched: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    changed_ids: list[int] = field(default_factory=list)


def default_window(source: Source, today: date, *, backfill_days: int = 30) -> FetchWindow:
    """Resume from the cursor with a small overlap (providers publish late)."""
    last = source.cursor.get("until")
    if last:
        since = date.fromisoformat(last) - timedelta(days=3)
    else:
        since = today - timedelta(days=backfill_days)
    return FetchWindow(since=since, until=today)


async def upsert_record(
    session: AsyncSession, source: Source, rec: RawRecord, runtime: Runtime
) -> tuple[Document, str]:
    """Returns (document, "created" | "updated" | "skipped")."""
    content_hash = rec.content_hash()
    existing = await session.scalar(
        select(Document).where(
            Document.source_id == source.id, Document.external_id == rec.external_id
        )
    )
    if existing is not None and existing.content_hash == content_hash:
        return existing, "skipped"

    resolution = runtime.registry.resolve(
        rec.publisher_raw, code_hint=rec.institution_code_hint, sido_hint=rec.sido_hint
    )
    raw_uri = await store_raw(source.key, rec.external_id, rec.content) if rec.content else None
    fields = {
        "doc_type": rec.doc_type,
        "title": rec.title,
        "url": rec.url,
        "publisher_raw": rec.publisher_raw,
        "institution_code": resolution.institution.code if resolution.institution else None,
        "department": resolution.department or rec.structured.get("department"),
        "published_at": rec.published_at,
        "content_hash": content_hash,
        "mime": rec.mime,
        "raw_uri": raw_uri,
        "structured": rec.structured | {"institution_resolution": resolution.method},
        "parse_status": "pending",
        "parse_error": None,
    }
    if existing is None:
        doc = Document(source_id=source.id, external_id=rec.external_id, **fields)
        session.add(doc)
        await session.flush()
        return doc, "created"
    for key, value in fields.items():
        setattr(existing, key, value)
    existing.text = None
    await session.flush()
    return existing, "updated"


async def run_ingest(
    session: AsyncSession,
    source: Source,
    adapter: SourceAdapter,
    runtime: Runtime,
    window: FetchWindow,
) -> IngestStats:
    run = IngestRun(source_id=source.id, status="running")
    session.add(run)
    await session.flush()
    stats = IngestStats()
    try:
        async for rec in adapter.fetch(window):
            stats.fetched += 1
            doc, outcome = await upsert_record(session, source, rec, runtime)
            if outcome == "skipped":
                stats.skipped += 1
            else:
                setattr(stats, outcome, getattr(stats, outcome) + 1)
                stats.changed_ids.append(doc.id)
        run.status = "succeeded"
        source.cursor = {"until": window.until.isoformat()}
        source.last_success_at = datetime.now(UTC)
        source.consecutive_failures = 0
    except Exception as exc:
        run.status = "partial" if stats.fetched else "failed"
        run.error = f"{type(exc).__name__}: {exc}"[:2000]
        source.consecutive_failures += 1
        raise
    finally:
        run.finished_at = datetime.now(UTC)
        run.fetched, run.created, run.updated, run.skipped = (
            stats.fetched,
            stats.created,
            stats.updated,
            stats.skipped,
        )
        run.stats = {"window": [window.since.isoformat(), window.until.isoformat()]}
        source.last_run_at = datetime.now(UTC)
        await adapter.aclose()
    log.info(
        "ingest.done",
        source=source.key,
        **{k: getattr(stats, k) for k in ("fetched", "created", "updated", "skipped")},
    )
    return stats
