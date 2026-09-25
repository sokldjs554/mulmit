"""Seed reference data, sources and demo tenants; run the whole pipeline in-process.

``manage demo run`` is the one-command path from an empty database to a populated product: it
drives the same functions the arq jobs call, synchronously and in chronological order, so a
reviewer can see the pipeline work end to end without a queue, cron or API keys.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import hash_password
from app.billing.service import (
    build_payment_provider,
    change_plan,
    ensure_subscription,
    register_card,
)
from app.db.models import (
    AlertChannel,
    AlertRule,
    CompanyProfile,
    Document,
    EvalRun,
    InstitutionRow,
    Organization,
    Signal,
    Source,
    User,
)
from app.log import get_logger
from app.pipeline.backtest import run_backtest
from app.pipeline.ingest import run_ingest
from app.pipeline.link import link_signals
from app.pipeline.process import process_document
from app.pipeline.recommend import refresh_recommendations
from app.runtime import Runtime
from app.sources.base import FetchWindow
from app.sources.registry import FIXTURE_CATALOG, SOURCE_CATALOG, FixtureAdapter, build_adapter

log = get_logger(__name__)

DEMO_PASSWORD = "demo-pass-1234"  # noqa: S105 - documented demo credential
ADMIN_PASSWORD = "admin-pass-1234"  # noqa: S105


async def seed_institutions(session: AsyncSession, runtime: Runtime) -> int:
    rows = [
        {
            "code": i.code,
            "name": i.name,
            "kind": i.kind,
            "sido": i.sido,
            "sigungu": i.sigungu,
            "region_code": i.region_code,
            "executive_code": i.executive_code,
            "aliases": list(i.aliases),
        }
        for i in runtime.registry.all()
    ]
    stmt = insert(InstitutionRow).values(rows)
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=["code"],
            set_={
                c: stmt.excluded[c]
                for c in (
                    "name",
                    "kind",
                    "sido",
                    "sigungu",
                    "region_code",
                    "executive_code",
                    "aliases",
                )
            },
        )
    )
    return len(rows)


async def seed_sources(
    session: AsyncSession, runtime: Runtime, *, anchor: date, seed: int, scale: float
) -> None:
    s = runtime.settings
    has_key = {
        "clik": bool(s.clik_api_key),
        "lofin": bool(s.lofin_api_key),
        "g2b": bool(s.data_go_kr_service_key),
    }
    for entry in SOURCE_CATALOG:
        stmt = insert(Source).values(**entry, enabled=has_key[entry["adapter"]], config={})
        await session.execute(stmt.on_conflict_do_nothing(index_elements=["key"]))
    for entry in FIXTURE_CATALOG:
        config = {"anchor": anchor.isoformat(), "seed": seed, "scale": scale}
        stmt = insert(Source).values(**entry, enabled=True, config=config)
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=["key"],
                set_={
                    "config": config,
                    "enabled": True,
                    "adapter": entry["adapter"],
                    "name": entry["name"],
                },
            )
        )


@dataclass(slots=True)
class DemoTenant:
    org_name: str
    email: str
    name: str
    plan: str
    profile: dict[str, Any]
    staff: bool = False
    extra_channels: list[tuple[str, str]] = field(default_factory=list)


DEMO_TENANTS = (
    DemoTenant(
        "데모 스마트시티솔루션(주)",
        "demo@example.com",
        "김데모",
        "pro",
        {
            "description": "스마트쉘터·스마트폴 등 도시 IoT 인프라와 지능형 CCTV 관제 솔루션을 "
            "공급하는 중소기업. 지자체 납품 실적 30건.",
            "keywords": [
                "스마트쉘터",
                "스마트 버스정류장",
                "스마트폴",
                "선별관제",
                "CCTV",
                "디지털트윈",
            ],
            "exclude_keywords": ["청소용역"],
            "categories": ["smart_city", "safety_cctv"],
            "region_codes": [],
            "budget_min": 100_000_000,
            "budget_max": 2_000_000_000,
        },
    ),
    DemoTenant(
        "케어온AI 주식회사",
        "care@example.com",
        "박돌봄",
        "free",
        {
            "description": "독거 어르신 AI 돌봄 스피커와 IoT 안부확인 서비스를 운영하는 스타트업.",
            "keywords": ["돌봄", "AI 스피커", "고독사", "안부확인"],
            "exclude_keywords": [],
            "categories": ["welfare_care"],
            "region_codes": ["41"],
            "budget_min": 50_000_000,
            "budget_max": 800_000_000,
        },
    ),
    DemoTenant(
        "발주 예측 운영팀", "admin@example.com", "운영자", "team", {"keywords": []}, staff=True
    ),
)


async def seed_tenants(session: AsyncSession, runtime: Runtime) -> list[int]:
    org_ids: list[int] = []
    provider = build_payment_provider(runtime.settings)
    for t in DEMO_TENANTS:
        user = await session.scalar(select(User).where(User.email == t.email))
        if user is not None:
            org_ids.append(user.org_id)
            continue
        org = Organization(name=t.org_name, plan="free", credit_balance=0)
        session.add(org)
        await session.flush()
        session.add(
            User(
                org_id=org.id,
                email=t.email,
                name=t.name,
                role="owner",
                is_staff=t.staff,
                password_hash=hash_password(ADMIN_PASSWORD if t.staff else DEMO_PASSWORD),
            )
        )
        profile = CompanyProfile(org_id=org.id, **t.profile)
        text = " ".join([t.profile.get("description", ""), *t.profile.get("keywords", []) * 2])
        [profile.embedding] = await runtime.embedder.embed([text], input_type="query")
        session.add(profile)
        session.add(AlertRule(org_id=org.id, mode="daily", min_score=0.5, stages=[]))
        session.add(AlertChannel(org_id=org.id, kind="email", target=t.email, label="대표 메일"))
        await session.flush()
        sub = await ensure_subscription(session, org)
        if t.plan != "free":
            await register_card(
                session,
                runtime.settings,
                provider,
                org,
                auth_key=f"demo-{org.id}",
                customer_key=sub.customer_key,
            )
            await change_plan(
                session, runtime.settings, provider, org, t.plan, request_id=f"seed-{org.id}"
            )
        else:
            from app.billing.service import start_period

            await start_period(session, org, sub, datetime.now(UTC))
        org_ids.append(org.id)
    return org_ids


@dataclass(slots=True)
class DemoReport:
    documents: int = 0
    signals: int = 0
    opportunities: int = 0
    needs_review: int = 0
    degraded: int = 0
    backtest: dict[str, Any] = field(default_factory=dict)


async def run_demo_pipeline(session: AsyncSession, runtime: Runtime, *, anchor: date) -> DemoReport:
    report = DemoReport()
    sources = (await session.scalars(select(Source).where(Source.key.like("fixture_%")))).all()
    window = FetchWindow(anchor - timedelta(days=365 * 4), anchor)
    doc_ids: list[int] = []
    for src in sources:
        stats = await run_ingest(session, src, build_adapter(src, runtime), runtime, window)
        doc_ids += stats.changed_ids
    await session.commit()
    report.documents = len(doc_ids)

    docs = (await session.scalars(select(Document).where(Document.id.in_(doc_ids)))).all()
    signal_ids: list[int] = []
    for i, doc in enumerate(sorted(docs, key=lambda d: d.published_at)):
        result = await process_document(session, runtime, doc.id)
        signal_ids += result.signal_ids
        report.needs_review += result.needs_review
        report.degraded += result.degraded
        if i % 25 == 0:
            await session.commit()
            log.info("demo.progress", processed=i + 1, total=len(docs))
    await session.commit()
    report.signals = len(signal_ids)

    touched = await link_signals(session, runtime, signal_ids, today=anchor)
    await session.commit()
    report.opportunities = len(touched)
    metrics = await run_backtest(session, today=anchor)
    session.add(
        EvalRun(
            kind="backtest",
            label=f"demo@{anchor}",
            metrics=metrics,
            params={"anchor": anchor.isoformat(), "synthetic": True},
        )
    )
    report.backtest = metrics
    # Re-link with calibrated conversion rates now that the backtest has measured them.
    calibration = metrics.get("calibration") or None
    if calibration:
        from app.db.models import Opportunity
        from app.pipeline.link import refresh_opportunity

        for opp in (await session.scalars(select(Opportunity))).all():
            await refresh_opportunity(session, opp, today=anchor, calibration=calibration)
    for org_id in (await session.scalars(select(Organization.id))).all():
        await refresh_recommendations(session, org_id, today=anchor)
    await session.commit()
    return report


def fixture_world(runtime: Runtime, session_source: Source) -> Any:
    return FixtureAdapter(session_source.key, session_source.config).world()


async def count_signals(session: AsyncSession) -> int:
    return len((await session.scalars(select(Signal.id))).all())
