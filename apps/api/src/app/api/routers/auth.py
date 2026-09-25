from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from app.api.deps import PrincipalDep, RuntimeDep, SessionDep, SettingsDep
from app.api.schemas import LoginIn, MeOut, OrgOut, SignupIn, UserOut
from app.auth.security import COOKIE_NAME, create_token, hash_password, verify_password
from app.billing.service import ensure_subscription, start_period
from app.db.models import AlertChannel, AlertRule, CompanyProfile, Organization, User
from app.settings import Settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.jwt_ttl_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def _me(user: User, org: Organization, mode: str) -> MeOut:
    return MeOut(
        user=UserOut.model_validate(user), org=OrgOut.model_validate(org), extractor_mode=mode
    )


def _throttle_key(request: Request, email: str) -> str:
    ip = request.client.host if request.client else "unknown"
    return f"app:login:{ip}:{email}"


async def _check_throttle(request: Request, runtime: RuntimeDep, email: str) -> None:
    """At most 5 *failed* attempts per minute per (IP, email), shared across replicas."""
    if runtime.redis is None:
        return
    failures = await runtime.redis.get(_throttle_key(request, email))
    if failures is not None and int(failures) >= 5:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "로그인 시도가 너무 많았어요. 1분 뒤에 다시 해 주세요",
        )


async def _record_failure(request: Request, runtime: RuntimeDep, email: str) -> None:
    if runtime.redis is None:
        return
    key = _throttle_key(request, email)
    if int(await runtime.redis.incr(key)) == 1:
        await runtime.redis.expire(key, 60)


@router.post("/signup", response_model=MeOut, status_code=status.HTTP_201_CREATED)
async def signup(
    body: SignupIn,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    runtime: RuntimeDep,
) -> MeOut:
    if await session.scalar(select(User.id).where(User.email == body.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 가입한 이메일이에요. 로그인해 주세요")
    org = Organization(name=body.company_name, plan="free", credit_balance=0)
    session.add(org)
    await session.flush()
    user = User(
        org_id=org.id,
        email=body.email,
        name=body.name,
        password_hash=hash_password(body.password),
        role="owner",
    )
    session.add(user)
    session.add(CompanyProfile(org_id=org.id))
    session.add(AlertRule(org_id=org.id, mode="daily", min_score=0.55, stages=[]))
    session.add(AlertChannel(org_id=org.id, kind="email", target=body.email, label="가입 이메일"))
    await session.flush()
    sub = await ensure_subscription(session, org)
    await start_period(session, org, sub, datetime.now(UTC))  # free plan: 3 welcome credits
    _set_cookie(
        response, settings, create_token(settings, user_id=user.id, org_id=org.id, staff=False)
    )
    return _me(user, org, runtime.extractor_mode)


@router.post("/login", response_model=MeOut)
async def login(
    body: LoginIn,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    runtime: RuntimeDep,
) -> MeOut:
    email = body.email.strip().lower()
    await _check_throttle(request, runtime, email)
    user = await session.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(user.password_hash, body.password):
        await _record_failure(request, runtime, email)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "이메일이나 비밀번호가 맞지 않아요")
    if runtime.redis is not None:
        await runtime.redis.delete(_throttle_key(request, email))
    user.last_login_at = datetime.now(UTC)
    org = await session.get(Organization, user.org_id)
    assert org is not None
    _set_cookie(
        response,
        settings,
        create_token(settings, user_id=user.id, org_id=org.id, staff=user.is_staff),
    )
    return _me(user, org, runtime.extractor_mode)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> Response:
    response.delete_cookie(COOKIE_NAME, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


me_router = APIRouter(prefix="/api", tags=["auth"])


@me_router.get("/me", response_model=MeOut)
async def me(principal: PrincipalDep, runtime: RuntimeDep) -> MeOut:
    return _me(principal.user, principal.org, runtime.extractor_mode)
