from datetime import date

from sqlalchemy import func, select

from app.db.models import (
    JobRun,
    Notification,
    Opportunity,
    OpportunitySignal,
    Recommendation,
    Signal,
    User,
)
from app.db.session import session_scope
from app.pipeline.backtest import run_backtest


async def test_pipeline_builds_multi_stage_opportunities(demo_world) -> None:  # type: ignore[no-untyped-def]
    assert demo_world.documents > 50
    assert demo_world.signals > 50
    async with session_scope() as s:
        # At least one opportunity must be threaded across ≥3 lifecycle stages.
        rows = (
            await s.execute(
                select(OpportunitySignal.opportunity_id, func.count(func.distinct(Signal.stage)))
                .join(Signal, Signal.id == OpportunitySignal.signal_id)
                .group_by(OpportunitySignal.opportunity_id)
            )
        ).all()
        assert max(n for _, n in rows) >= 3
        # Structured records carrying each other's numbers are linked deterministically.
        ref_links = await s.scalar(
            select(func.count())
            .select_from(OpportunitySignal)
            .where(OpportunitySignal.method == "ref")
        )
        assert ref_links and ref_links > 0
        # Every accepted signal is linked exactly once.
        accepted = await s.scalar(
            select(func.count()).select_from(Signal).where(Signal.verdict == "accepted")
        )
        linked = await s.scalar(select(func.count()).select_from(OpportunitySignal))
        assert accepted == linked


async def test_recommendations_are_explained_and_ranked(demo_world) -> None:  # type: ignore[no-untyped-def]
    async with session_scope() as s:
        demo = await s.scalar(select(User).where(User.email == "demo@example.com"))
        assert demo is not None
        recs = (
            await s.scalars(
                select(Recommendation)
                .where(Recommendation.org_id == demo.org_id)
                .order_by(Recommendation.score.desc())
            )
        ).all()
        assert recs, "demo tenant should get recommendations"
        top = recs[0]
        assert set(top.breakdown["features"]) >= {"semantic", "keyword", "conversion", "lead_time"}
        opp = await s.get(Opportunity, top.opportunity_id)
        assert opp is not None and opp.status in ("open", "bid_open")


async def test_backtest_measures_lead_time_and_conversion(demo_world) -> None:  # type: ignore[no-untyped-def]
    async with session_scope() as s:
        metrics = await run_backtest(s, today=date(2026, 9, 25))
    coverage = metrics["tender_early_coverage"]
    assert coverage["tenders"] > 0
    assert coverage["with_early_signal"] > 0
    assert metrics["lead_time_days"]["median"] > 60
    conv = metrics["conversion_by_first_signal"]
    assert any(k.startswith("council_mention:") for k in conv)


async def test_reprocessing_a_document_is_idempotent(demo_world, runtime) -> None:  # type: ignore[no-untyped-def]
    from app.db.models import Document
    from app.pipeline.process import process_document

    async with session_scope() as s:
        doc = await s.scalar(
            select(Document).where(Document.doc_type == "council_minutes").limit(1)
        )
        assert doc is not None
        before = await s.scalar(
            select(func.count()).select_from(Signal).where(Signal.document_id == doc.id)
        )
        await process_document(s, runtime, doc.id)
        after = await s.scalar(
            select(func.count()).select_from(Signal).where(Signal.document_id == doc.id)
        )
    assert before == after


async def test_job_cancelled_by_shutdown_is_recorded_as_retrying(demo_world) -> None:  # type: ignore[no-untyped-def]
    import asyncio
    import contextlib

    from sqlalchemy import select

    from app.db.models import JobRun
    from app.db.session import session_scope
    from app.worker.tasks import tracked

    started = asyncio.Event()

    @tracked("slow_probe")
    async def slow_probe(ctx: dict[str, object]) -> dict[str, int]:
        started.set()
        await asyncio.sleep(30)
        return {"done": 1}

    task = asyncio.create_task(slow_probe({"job_id": "probe:cancel", "job_try": 1}))
    await started.wait()
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    async with session_scope() as s:
        run = await s.scalar(select(JobRun).where(JobRun.job_id == "probe:cancel"))
    assert run is not None
    assert run.status == "retrying"
    assert run.finished_at is not None


async def test_demo_run_leaves_job_history_and_a_morning_digest(demo_world) -> None:  # type: ignore[no-untyped-def]
    async with session_scope() as s:
        demo = JobRun.job_id.like("demo:%")  # other tests in this database run jobs too
        jobs = dict(
            (
                await s.execute(select(JobRun.job, func.count()).where(demo).group_by(JobRun.job))
            ).all()
        )
        assert jobs.get("process_document", 0) == demo_world.documents
        assert jobs.get("link_signals") == 1 and jobs.get("deliver_notifications") == 1
        failed = select(JobRun).where(demo, JobRun.status != "succeeded")
        assert not (await s.scalars(failed)).all()
        digests = (
            await s.scalars(
                select(Notification).where(
                    Notification.payload["headline"].astext.like("09월 25일%")
                )
            )
        ).all()
        assert digests and all(n.kind == "daily" and n.payload["items"] for n in digests)
        # Sent when a mail server answers (Mailpit), otherwise left for retry — never faked.
        assert {n.status for n in digests} <= {"sent", "pending"}
