from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

import httpx
import pytest

from app.api.app import create_app
from app.clock import today_kst
from app.settings import get_settings


@pytest.fixture
async def client(demo_world) -> AsyncIterator[httpx.AsyncClient]:  # type: ignore[no-untyped-def]
    app = create_app(get_settings())
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def _login(client: httpx.AsyncClient, email: str, password: str) -> None:
    resp = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text


async def test_signup_profile_feed_detail_brief(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/auth/signup",
        json={
            "email": "new@vendor.kr",
            "password": "secret-pass-1",
            "name": "홍길동",
            "company_name": "벤더",
        },
    )
    assert resp.status_code == 201, resp.text
    me = resp.json()
    assert me["org"]["plan"] == "free" and me["org"]["credit_balance"] == 3

    dup = await client.post(
        "/api/auth/signup",
        json={
            "email": "new@vendor.kr",
            "password": "secret-pass-1",
            "name": "x",
            "company_name": "y",
        },
    )
    assert dup.status_code == 409

    profile = {
        "description": "지능형 CCTV 전문",
        "keywords": ["CCTV", "선별관제"],
        "exclude_keywords": [],
        "categories": ["safety_cctv"],
        "region_codes": [],
        "budget_min": None,
        "budget_max": None,
    }
    assert (await client.put("/api/profile", json=profile)).status_code == 200

    # The worker would refresh recommendations; do it inline for the test.
    from sqlalchemy import select

    from app.db.models import User
    from app.db.session import session_scope
    from app.pipeline.recommend import refresh_recommendations

    async with session_scope() as s:
        user = await s.scalar(select(User).where(User.email == "new@vendor.kr"))
        assert user is not None
        await refresh_recommendations(s, user.org_id)

    feed = (await client.get("/api/opportunities", params={"limit": 5})).json()
    assert feed["total"] > 0
    card = feed["items"][0]
    assert card["reasons"], "recommendations must say why"

    detail = (await client.get(f"/api/opportunities/{card['id']}")).json()
    assert detail["signals"] and detail["signals"][0]["evidence"]

    headers = {"Idempotency-Key": "brief-key-0001"}
    first = await client.post(f"/api/opportunities/{card['id']}/briefs", headers=headers)
    again = await client.post(f"/api/opportunities/{card['id']}/briefs", headers=headers)
    assert first.status_code == again.status_code == 201
    assert first.json()["id"] == again.json()["id"], "same idempotency key must not charge twice"
    billing = (await client.get("/api/billing")).json()
    assert billing["credit_balance"] == 0

    broke = await client.post(
        f"/api/opportunities/{card['id']}/briefs", headers={"Idempotency-Key": "brief-key-0002"}
    )
    assert broke.status_code == 402

    # Paging is stable with the keyset cursor.
    page1 = (await client.get("/api/opportunities", params={"limit": 2})).json()
    if page1["next_cursor"]:
        page2 = (
            await client.get(
                "/api/opportunities", params={"limit": 2, "cursor": page1["next_cursor"]}
            )
        ).json()
        assert {i["id"] for i in page1["items"]}.isdisjoint({i["id"] for i in page2["items"]})


async def test_billing_card_plan_and_credit_pack(client: httpx.AsyncClient) -> None:
    await client.post(
        "/api/auth/signup",
        json={
            "email": "pay@vendor.kr",
            "password": "secret-pass-1",
            "name": "결제",
            "company_name": "페이",
        },
    )
    billing = (await client.get("/api/billing")).json()
    no_card = await client.post(
        "/api/billing/plan", json={"plan": "pro"}, headers={"Idempotency-Key": "plan-0000001"}
    )
    assert no_card.status_code == 400

    card = await client.post(
        "/api/billing/card", json={"auth_key": "auth-ok", "customer_key": billing["customer_key"]}
    )
    assert card.status_code == 200 and card.json()["card_summary"]
    upgraded = await client.post(
        "/api/billing/plan", json={"plan": "pro"}, headers={"Idempotency-Key": "plan-0000002"}
    )
    assert upgraded.status_code == 200 and upgraded.json()["plan"] == "pro"
    pack = await client.post(
        "/api/billing/credits",
        json={"pack": "pack_30"},
        headers={"Idempotency-Key": "pack-0000001"},
    )
    assert pack.status_code == 200 and pack.json()["status"] == "paid"
    after = (await client.get("/api/billing")).json()
    # free grant (3) expired on upgrade, pro grant (40) + pack (30)
    assert after["credit_balance"] == 70
    reasons = [e["reason"] for e in after["ledger"]]
    assert {"plan_grant", "purchase", "expiry"} <= set(reasons)


async def test_admin_requires_staff(client: httpx.AsyncClient) -> None:
    await _login(client, "demo@example.com", "demo-pass-1234")
    assert (await client.get("/api/admin/overview")).status_code == 403
    await _login(client, "admin@example.com", "admin-pass-1234")
    overview = await client.get("/api/admin/overview")
    assert overview.status_code == 200
    body = overview.json()
    assert body["funnel"]["chunks"] >= body["funnel"]["chunks_triaged"] > 0
    sources = (await client.get("/api/admin/sources")).json()
    assert any(s["key"] == "fixture_minutes" and s["documents"] > 0 for s in sources)
    assert (await client.get("/api/admin/llm/usage")).status_code == 200


async def test_login_is_throttled(client: httpx.AsyncClient) -> None:
    codes = [
        (
            await client.post(
                # not the demo account: the lock-out lasts a minute and later tests log in as demo
                "/api/auth/login",
                json={"email": "someone@example.com", "password": "wrong"},
            )
        ).status_code
        for _ in range(7)
    ]
    assert codes[:5] == [401] * 5
    assert codes[-1] == 429


@pytest.mark.parametrize("sort", ["score", "soon", "recent"])
async def test_every_sort_pages_through_the_whole_feed_once(
    client: httpx.AsyncClient, sort: str
) -> None:
    await _login(client, "demo@example.com", "demo-pass-1234")
    params: dict[str, str | int] = {"limit": 7, "sort": sort, "status": "open"}
    first = (await client.get("/api/opportunities", params=params)).json()
    seen, pages, cursor = list(first["items"]), 1, first["next_cursor"]
    while cursor:
        page = (await client.get("/api/opportunities", params={**params, "cursor": cursor})).json()
        seen += page["items"]
        cursor, pages = page["next_cursor"], pages + 1
    ids = [c["id"] for c in seen]
    assert pages > 1 and len(ids) == len(set(ids)) == first["total"]
    if sort == "recent":
        keys = [c["last_signal_at"] for c in seen]
        assert keys == sorted(keys, reverse=True)
    if sort == "soon":
        # the key is when the tender is due: an open window shows from today, a missed one
        # counts as today too; within the same day the better fit comes first
        today = today_kst().isoformat()

        def due(c: dict[str, Any]) -> str:
            return today if c["window_passed"] else (c["bid_window_start"] or "9999-12-31")

        pairs = [(due(c), -c["score"]) for c in seen]
        assert pairs == sorted(pairs)
    wrong = await client.get(
        "/api/opportunities", params={**params, "sort": "score", "cursor": first["next_cursor"]}
    )
    assert sort == "score" or wrong.status_code == 400  # a cursor only continues its own order


async def test_stage_counts_ignore_the_stage_filter(client: httpx.AsyncClient) -> None:
    await _login(client, "demo@example.com", "demo-pass-1234")
    everything = (await client.get("/api/opportunities", params={"limit": 1})).json()
    counts = everything["stage_counts"]
    assert sum(counts.values()) == everything["total"] and len(counts) >= 2
    one = (
        await client.get("/api/opportunities", params={"limit": 1, "stage": "council_mention"})
    ).json()
    assert one["stage_counts"] == counts
    assert one["total"] == counts["council_mention"]


async def test_a_soon_cursor_survives_midnight(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api.routers import opportunities

    await _login(client, "demo@example.com", "demo-pass-1234")
    params: dict[str, str | int] = {"limit": 5, "sort": "soon", "status": "open"}
    first = (await client.get("/api/opportunities", params=params)).json()
    tomorrow = today_kst() + timedelta(days=1)
    monkeypatch.setattr(opportunities, "today_kst", lambda: tomorrow)
    second = (
        await client.get("/api/opportunities", params={**params, "cursor": first["next_cursor"]})
    ).json()
    assert second["items"]
    assert not {c["id"] for c in first["items"]} & {c["id"] for c in second["items"]}


async def test_a_cursor_from_before_sort_options_still_pages(client: httpx.AsyncClient) -> None:
    import base64
    import json

    await _login(client, "demo@example.com", "demo-pass-1234")
    first = (await client.get("/api/opportunities", params={"limit": 3})).json()
    last = first["items"][-1]
    old = base64.urlsafe_b64encode(json.dumps([last["score"], last["id"]]).encode()).decode()
    resp = await client.get("/api/opportunities", params={"limit": 3, "cursor": old})
    assert resp.status_code == 200 and resp.json()["items"]
    assert not {c["id"] for c in first["items"]} & {c["id"] for c in resp.json()["items"]}
