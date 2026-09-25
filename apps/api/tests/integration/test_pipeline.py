from datetime import UTC, date, datetime

import pytest
from sqlalchemy import func, select

from app.db.models import (
    JobRun,
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


async def test_demo_run_leaves_job_history(demo_world) -> None:  # type: ignore[no-untyped-def]
    async with session_scope() as s:
        demo = JobRun.job_id.like("demo:%")  # other tests in this database run jobs too
        jobs = dict(
            (
                await s.execute(select(JobRun.job, func.count()).where(demo).group_by(JobRun.job))
            ).all()
        )
        assert jobs.get("process_document", 0) >= demo_world.documents
        assert jobs.get("link_signals", 0) >= 1 and jobs.get("refresh_recommendations", 0) >= 1
        running = select(JobRun).where(demo, JobRun.status == "running")
        assert not (await s.scalars(running)).all()


async def test_a_failed_demo_step_is_still_recorded(demo_world) -> None:  # type: ignore[no-untyped-def]
    from app.demo.seed import _job

    with pytest.raises(RuntimeError):
        async with _job("link_signals", signals=3):
            raise RuntimeError("linker blew up")
    async with session_scope() as s:
        row = await s.scalar(select(JobRun).where(JobRun.error == "RuntimeError: linker blew up"))
        assert row is not None and row.status == "failed" and row.finished_at is not None


async def test_demo_digest_goes_out_at_eight_kst_through_the_daily_path(
    demo_world,
    runtime,
    monkeypatch: pytest.MonkeyPatch,  # type: ignore[no-untyped-def]
) -> None:
    from app.demo import seed

    calls: list[tuple[int, str | None, datetime]] = []

    async def fake_enqueue(_s, org_id, *, web_url, mode_filter=None, now=None):  # type: ignore[no-untyped-def]
        calls.append((org_id, mode_filter, now))
        return 1

    async def fake_deliver(_s, channels, *, now=None, limit=100):  # type: ignore[no-untyped-def]
        assert set(channels) == {"email", "slack", "kakao"}
        return {"sent": len(calls), "retry": 0, "failed": 0, "deferred": 0}

    monkeypatch.setattr(seed, "enqueue_alerts", fake_enqueue)
    monkeypatch.setattr(seed, "deliver_pending", fake_deliver)
    async with session_scope() as s:
        stats = await seed.send_morning_digest(s, runtime, [1, 2], anchor=date(2026, 9, 25))
    assert stats["sent"] == 2
    assert {(org, mode) for org, mode, _ in calls} == {(1, "daily"), (2, "daily")}
    assert {now for _, _, now in calls} == {datetime(2026, 9, 24, 23, 0, tzinfo=UTC)}  # 08:00 KST


async def test_alert_lines_quote_speech_and_explain_budget_rows(demo_world) -> None:  # type: ignore[no-untyped-def]
    from app.notify.dispatch import build_items

    async with session_scope() as s:
        stages = (
            select(OpportunitySignal.opportunity_id)
            .join(Signal, Signal.id == OpportunitySignal.signal_id)
            .group_by(OpportunitySignal.opportunity_id)
        )
        budget_only = stages.having(
            func.bool_and(Signal.stage == "budget_line")
            & func.bool_or(Signal.budget_krw.is_not(None))
        )
        with_council = stages.having(
            func.bool_or(Signal.stage == "council_mention")
            & ~func.bool_or(Signal.stage == "budget_line")
        )
        pairs = []
        for query in (budget_only, with_council):
            opp_id = await s.scalar(query.limit(1))
            assert opp_id is not None
            rec = await s.scalar(select(Recommendation).limit(1))
            opp = await s.get(Opportunity, opp_id)
            assert rec is not None and opp is not None
            pairs.append((rec, opp))
        budget_item, council_item = await build_items(s, pairs, "https://app.example")
    assert budget_item["evidence"] is None
    assert (
        "예산서에" in budget_item["evidence_note"]
        and "편성돼 있어요" in budget_item["evidence_note"]
    )
    assert council_item["evidence"] and council_item["evidence_note"] is None
    assert "\n" not in council_item["evidence"]
    # a worker rolled back to the previous release reads item["window"]
    assert budget_item["window"] and council_item["window"]
