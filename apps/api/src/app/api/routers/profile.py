from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import PrincipalDep, QueueDep, RuntimeDep, SessionDep
from app.api.schemas import CategoryOut, InstitutionOut, ProfileIO
from app.billing.plans import PLANS
from app.db.models import CompanyProfile, InstitutionRow
from app.domain.institutions import PROVIDER_CODE_PREFIX
from app.domain.taxonomy import CATEGORIES, Category
from app.worker.queue import enqueue

router = APIRouter(prefix="/api", tags=["profile"])


def _profile_text(p: ProfileIO) -> str:
    labels = [
        CATEGORIES[Category(c)].label for c in p.categories if c in Category._value2member_map_
    ]
    return " ".join([p.description, *p.keywords, *p.keywords, *labels])


@router.get("/profile", response_model=ProfileIO)
async def get_profile(principal: PrincipalDep, session: SessionDep) -> ProfileIO:
    profile = await session.get(CompanyProfile, principal.org.id)
    return ProfileIO.model_validate(profile) if profile else ProfileIO()


@router.put("/profile", response_model=ProfileIO)
async def put_profile(
    body: ProfileIO,
    principal: PrincipalDep,
    session: SessionDep,
    runtime: RuntimeDep,
    queue: QueueDep,
) -> ProfileIO:
    plan = PLANS[principal.org.plan]
    if plan.max_regions is not None and len(body.region_codes) > plan.max_regions:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            f"{plan.name} 플랜에서는 관심 지역을 {plan.max_regions}곳까지 고를 수 있어요",
        )
    if body.budget_min and body.budget_max and body.budget_min > body.budget_max:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "최소 사업 규모가 최대 규모보다 커요"
        )
    unknown = [c for c in body.categories if c not in Category._value2member_map_]
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"없는 분야예요: {', '.join(unknown)}"
        )
    profile = await session.get(CompanyProfile, principal.org.id)
    if profile is None:
        profile = CompanyProfile(org_id=principal.org.id)
        session.add(profile)
    keywords = list(dict.fromkeys(k.strip() for k in body.keywords if k.strip()))
    excludes = list(dict.fromkeys(k.strip() for k in body.exclude_keywords if k.strip()))
    profile.description = body.description.strip()
    profile.keywords = keywords
    profile.exclude_keywords = excludes
    profile.categories = body.categories
    profile.region_codes = body.region_codes
    profile.budget_min = body.budget_min
    profile.budget_max = body.budget_max
    [vector] = await runtime.embedder.embed([_profile_text(body)], input_type="query")
    profile.embedding = vector
    await session.flush()
    await session.commit()
    await enqueue(queue, "refresh_recommendations", principal.org.id)
    return ProfileIO.model_validate(profile)


@router.get("/institutions", response_model=list[InstitutionOut])
async def institutions(principal: PrincipalDep, session: SessionDep) -> list[InstitutionOut]:
    # The table's own institutions: the ones a reviewer may need to pick. Those known by a
    # provider code (thousands of schools and hospitals) never wait for an institution.
    rows = await session.scalars(
        select(InstitutionRow)
        .where(
            InstitutionRow.kind != "council",
            InstitutionRow.code.not_like(f"{PROVIDER_CODE_PREFIX}%"),
        )
        .order_by(InstitutionRow.region_code)
    )
    return [InstitutionOut.model_validate(r) for r in rows]


@router.get("/categories", response_model=list[CategoryOut])
async def categories() -> list[CategoryOut]:
    return [
        CategoryOut(key=c.value, label=i.label)
        for c, i in CATEGORIES.items()
        if c is not Category.OTHER
    ]
