"""``mulmit`` command line.

mulmit db upgrade                 # alembic upgrade head
mulmit seed [--anchor 2026-09-25] # institutions, sources, demo tenants
mulmit demo run                   # full pipeline over the synthetic world, in-process
mulmit eval all --record          # extraction / linking / OCR / realistic-set evals
mulmit worker                     # arq worker + cron (+ /healthz on $PORT for Cloud Run)
mulmit openapi > openapi.json     # schema for the web app's generated types
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from collections.abc import Awaitable, Callable, Coroutine
from datetime import date
from pathlib import Path
from typing import Any, TypeVar

import typer

from mulmit.clock import today_kst
from mulmit.log import configure_logging
from mulmit.settings import get_settings

app = typer.Typer(help="발주 예측 operations CLI", no_args_is_help=True)
db_app = typer.Typer(help="Database")
demo_app = typer.Typer(help="Synthetic demo world")
eval_app = typer.Typer(help="Evaluations")
app.add_typer(db_app, name="db")
app.add_typer(demo_app, name="demo")
app.add_typer(eval_app, name="eval")

T = TypeVar("T")


def _run(fn: Callable[[], Coroutine[Any, Any, T]]) -> T:
    return asyncio.run(fn())


async def _with_session(fn: Callable[..., Awaitable[T]], **kwargs: Any) -> T:
    from redis.asyncio import Redis

    from mulmit.db.session import dispose_engine, session_scope
    from mulmit.runtime import build_runtime

    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    runtime = build_runtime(settings, redis=redis)
    try:
        async with session_scope() as session:
            return await fn(session, runtime, **kwargs)
    finally:
        await redis.aclose()
        await dispose_engine()


@db_app.command("upgrade")
def db_upgrade(revision: str = "head") -> None:
    """Apply migrations (Cloud Run Job runs this before each deploy)."""
    root = Path(__file__).resolve().parents[2]
    subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", "-c", str(root / "alembic.ini"), "upgrade", revision],
        check=True,
        cwd=root,
    )


@app.command()
def seed(
    anchor: str = typer.Option(None, help="Synthetic world 'today' (YYYY-MM-DD)"),
    seed_value: int = typer.Option(7, "--seed"),
    scale: float = 1.0,
) -> None:
    """Seed institutions, sources and demo tenants."""
    configure_logging(json=False)
    anchor_date = date.fromisoformat(anchor) if anchor else today_kst()

    async def go(session: Any, runtime: Any) -> None:
        from mulmit.demo.seed import seed_institutions, seed_sources, seed_tenants

        n = await seed_institutions(session, runtime)
        await seed_sources(session, runtime, anchor=anchor_date, seed=seed_value, scale=scale)
        await session.flush()
        orgs = await seed_tenants(session, runtime)
        typer.echo(f"institutions={n} demo_orgs={orgs} anchor={anchor_date}")

    _run(lambda: _with_session(go))


@demo_app.command("run")
def demo_run(anchor: str = typer.Option(None)) -> None:
    """Ingest the synthetic world and run every pipeline stage in-process."""
    configure_logging(json=False)

    async def go(session: Any, runtime: Any) -> None:
        from sqlalchemy import select

        from mulmit.db.models import Source
        from mulmit.demo.seed import run_demo_pipeline

        src = await session.scalar(select(Source).where(Source.key == "fixture_minutes"))
        if src is None:
            raise typer.BadParameter("run `mulmit seed` first")
        anchor_date = date.fromisoformat(anchor or src.config["anchor"])
        report = await run_demo_pipeline(session, runtime, anchor=anchor_date)
        typer.echo(
            json.dumps(
                {
                    "documents": report.documents,
                    "signals": report.signals,
                    "opportunities": report.opportunities,
                    "needs_review": report.needs_review,
                    "degraded": report.degraded,
                    "tender_early_coverage": report.backtest.get("tender_early_coverage"),
                    "lead_time_days": report.backtest.get("lead_time_days", {}).get("median"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    _run(lambda: _with_session(go))


@eval_app.command("all")
def eval_all(
    record: bool = typer.Option(False, help="Store results as eval_runs"),
    report: Path = typer.Option(None, help="Write a Markdown report here"),
) -> None:
    """Extraction, triage, linking and OCR metrics against the synthetic ground truth, plus the
    hand-written realistic set."""
    configure_logging(json=False, level="WARNING")

    async def go(session: Any, runtime: Any) -> dict[str, Any]:
        from mulmit.eval.runner import run_all_evals

        return await run_all_evals(session, runtime, record=record, report_path=report)

    results = _run(lambda: _with_session(go))
    typer.echo(json.dumps(results, ensure_ascii=False, indent=2, default=str))


@app.command()
def worker() -> None:
    """Run the arq worker (queue + cron). Serves GET /healthz on $PORT when set (Cloud Run)."""
    from mulmit.worker.runner import run

    run()


@app.command()
def openapi() -> None:
    """Print the OpenAPI schema (used to generate the web app's TypeScript types)."""
    from mulmit.api.app import create_app

    configure_logging(json=False, level="WARNING")
    typer.echo(json.dumps(create_app().openapi(), ensure_ascii=False, indent=2))


if __name__ == "__main__":  # pragma: no cover
    app()
