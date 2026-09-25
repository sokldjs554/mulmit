"""``manage`` command line.

manage db upgrade                 # alembic upgrade head
manage seed [--anchor 2026-09-25] # institutions, sources, demo tenants
manage demo run                   # full pipeline over the synthetic world, in-process
manage eval all --record          # extraction / linking / OCR / realistic-set evals
manage eval llm --dry-run         # Claude model × effort comparison on the hand-written set
manage bench --report ../../docs/performance.md   # hot-query plans at volume
manage worker                     # arq worker + cron (+ /healthz on $PORT for Cloud Run)
manage openapi > openapi.json     # schema for the web app's generated types
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

from app.clock import today_kst
from app.log import configure_logging
from app.settings import get_settings

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

    from app.db.session import dispose_engine, session_scope
    from app.runtime import build_runtime

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
        from app.demo.seed import seed_institutions, seed_sources, seed_tenants

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

        from app.db.models import Source
        from app.demo.seed import run_demo_pipeline

        src = await session.scalar(select(Source).where(Source.key == "fixture_minutes"))
        if src is None:
            raise typer.BadParameter("run `manage seed` first")
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
        from app.eval.runner import run_all_evals

        return await run_all_evals(session, runtime, record=record, report_path=report)

    results = _run(lambda: _with_session(go))
    typer.echo(json.dumps(results, ensure_ascii=False, indent=2, default=str))


@eval_app.command("llm")
def eval_llm(
    model: list[str] = typer.Option(
        None,
        "--model",
        "-m",
        help="Repeatable: heuristic | <model> | <model>:<effort>. Default: "
        "heuristic, claude-opus-5:low, claude-opus-5:medium, claude-sonnet-5:low, "
        "claude-haiku-4-5",
    ),
    max_usd: float = typer.Option(10.0, help="Stop calling the API once this much is spent"),
    concurrency: int = typer.Option(4, help="Calls in flight per model"),
    dry_run: bool = typer.Option(False, help="Print the estimated cost and exit"),
    report: Path = typer.Option(None, help="Write a Markdown report here"),
    record: bool = typer.Option(False, help="Also store each model as an eval_runs row"),
) -> None:
    """Run the hand-written set through each extractor: quality after the grounding verifier,
    cost, latency. Reads the key from APP_ANTHROPIC_API_KEY or ANTHROPIC_API_KEY."""
    from app.eval.llm_compare import DEFAULT_CANDIDATES, Candidate, compare, estimate, render
    from app.eval.realistic import load_realistic

    configure_logging(json=False, level="WARNING")
    try:
        candidates = [Candidate.parse(m) for m in (model or DEFAULT_CANDIDATES)]
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    cases = load_realistic()
    total = 0.0
    for c in candidates:
        est = float(estimate(cases, c))
        total += est
        typer.echo(f"{c.label:<28} {len(cases)} cases  ~${est:.2f}", err=True)
    typer.echo(f"{'estimated total':<28} ~${total:.2f} (cap ${max_usd:.2f})", err=True)
    if total > max_usd:
        typer.echo(
            "warning: estimate exceeds --max-usd; calls stop once the cap is spent", err=True
        )
    if dry_run:
        return

    settings = get_settings()
    key = settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
    results = _run(
        lambda: compare(
            candidates,
            api_key=key,
            max_usd=max_usd,
            concurrency=concurrency,
            min_score=settings.grounding_min_score,
            cases=cases,
        )
    )
    if report is not None:
        report.write_text(render(results), encoding="utf-8")
    if record:

        async def store(session: Any, _runtime: Any) -> None:
            from app.db.models import EvalRun

            for x in results["candidates"]:
                session.add(
                    EvalRun(
                        kind="extraction",
                        label=f"llm-compare:{x['candidate']}"[:100],
                        metrics=x,
                        params=results["conditions"],
                    )
                )

        _run(lambda: _with_session(store))
    typer.echo(json.dumps(results, ensure_ascii=False, indent=2, default=str))


@app.command()
def bench(
    scale: float = typer.Option(1.0, help="Multiply the default row counts"),
    report: Path = typer.Option(Path("performance.md"), help="Markdown report to write"),
) -> None:
    """Load a throwaway <db>_bench at production-like volume and compare hot query plans
    between the initial schema and head (see docs/performance.md)."""
    from app.bench import SIZES, run_bench

    configure_logging(json=False, level="WARNING")
    sizes = {k: max(1, int(v * scale)) for k, v in SIZES.items()}
    results = _run(lambda: run_bench(sizes, report, log=typer.echo))
    typer.echo(json.dumps(results, ensure_ascii=False, indent=2, default=str))


@app.command()
def worker() -> None:
    """Run the arq worker (queue + cron). Serves GET /healthz on $PORT when set (Cloud Run)."""
    from app.worker.runner import run

    run()


@app.command()
def openapi() -> None:
    """Print the OpenAPI schema (used to generate the web app's TypeScript types)."""
    from app.api.app import create_app

    configure_logging(json=False, level="WARNING")
    typer.echo(json.dumps(create_app().openapi(), ensure_ascii=False, indent=2))


if __name__ == "__main__":  # pragma: no cover
    app()
