"""Regression tests for problems that only appear at production volume (docs/performance.md).

At demo size the planner scans tables sequentially, so these tests force the index paths the
planner chooses at 100k+ rows.
"""

import random
from datetime import date

from sqlalchemy import text

from app.db.models import CompanyProfile, Opportunity
from app.db.session import session_scope
from app.pipeline.recommend import _candidates


async def test_semantic_candidates_are_not_capped_by_hnsw_ef_search(demo_world) -> None:  # type: ignore[no-untyped-def]
    rnd = random.Random(3)  # noqa: S311 - test vectors

    def vec() -> list[float]:
        return [rnd.random() - 0.5 for _ in range(512)]

    async with session_scope() as s:
        # More open opportunities than hnsw.ef_search's default (40), among many closed ones.
        opps = [
            Opportunity(
                title=f"회귀 테스트 공고 {i}",
                category="other",
                stage="council_mention",
                status="open" if i < 60 else "closed",
                first_seen_at=date(2026, 1, 1),
                last_signal_at=date(2026, 1, 1),
                signal_count=1,
                conversion_prob=0.5,
                embedding=vec(),
            )
            for i in range(300)
        ]
        s.add_all(opps)
        await s.flush()
        open_ids = {o.id for o in opps[:60]}
        # The path taken at volume: an ordered HNSW index scan, no sequential scan or sort.
        for setting in ("enable_seqscan", "enable_sort", "enable_bitmapscan"):
            await s.execute(text(f"SET LOCAL {setting} = off"))
        profile = CompanyProfile(org_id=0, embedding=vec(), keywords=[], categories=[])
        got = {o.id for o in await _candidates(s, profile)}
        await s.rollback()
    assert open_ids <= got


async def test_reference_lookup_uses_the_gin_index(demo_world) -> None:  # type: ignore[no-untyped-def]
    async with session_scope() as s:
        await s.execute(text("SET LOCAL enable_seqscan = off"))
        plan = "\n".join(
            row[0]
            for row in await s.execute(
                text(
                    "EXPLAIN SELECT id FROM signals "
                    """WHERE external_refs @> '{"order_plan_no": "R-UNSEEN"}'::jsonb"""
                )
            )
        )
    assert "ix_signals_external_refs_gin" in plan
