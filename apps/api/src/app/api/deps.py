"""FastAPI dependencies."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

import jwt
from arq import ArqRedis
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import COOKIE_NAME, decode_token
from app.db.models import Organization, User
from app.db.session import get_sessionmaker
from app.runtime import Runtime
from app.settings import Settings, get_settings


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


def get_runtime(request: Request) -> Runtime:
    runtime: Runtime = request.app.state.runtime
    return runtime


def get_queue(request: Request) -> ArqRedis:
    queue: ArqRedis = request.app.state.queue
    return queue


SessionDep = Annotated[AsyncSession, Depends(get_session)]
RuntimeDep = Annotated[Runtime, Depends(get_runtime)]
QueueDep = Annotated[ArqRedis, Depends(get_queue)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@dataclass(slots=True)
class Principal:
    user: User
    org: Organization


async def current_principal(
    request: Request, session: SessionDep, settings: SettingsDep
) -> Principal:
    token = request.cookies.get(COOKIE_NAME)
    auth = request.headers.get("Authorization", "")
    if not token and auth.lower().startswith("bearer "):
        token = auth[7:]
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "로그인이 필요해요")
    try:
        claims = decode_token(settings, token)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "로그인이 만료됐어요. 다시 로그인해 주세요"
        ) from exc
    user = await session.get(User, int(claims["sub"]))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "계정을 찾을 수 없어요")
    org = await session.get(Organization, user.org_id)
    assert org is not None
    return Principal(user, org)


PrincipalDep = Annotated[Principal, Depends(current_principal)]


async def staff_principal(principal: PrincipalDep) -> Principal:
    if not principal.user.is_staff:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "운영자만 볼 수 있는 화면이에요")
    return principal


StaffDep = Annotated[Principal, Depends(staff_principal)]
