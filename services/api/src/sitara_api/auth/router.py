"""Auth endpoints (§34.5 handshake, §22.5 sessions, §32.12 choose-flow).

Cookie surface: `sitara_access` (path=/) + `sitara_refresh` (path=/auth,
rotating). Both httpOnly — the Firebase token is exchanged exactly once and
never persisted client-side.
"""

from datetime import date
from typing import Annotated, Any

from bson import ObjectId
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sitara_schemas import ErrorCode

from sitara_api.auth.firebase import FirebaseVerifier, get_verifier
from sitara_api.auth.service import AuthService
from sitara_api.auth.sessions import ACCESS_COOKIE, REFRESH_COOKIE, MintedSession, SessionService
from sitara_api.auth.throttle import OtpThrottle
from sitara_api.config import Settings
from sitara_api.errors import ApiError

router = APIRouter(prefix="/auth", tags=["auth"])


class ExchangeRequest(BaseModel):
    id_token: str
    date_of_birth: date | None = None
    locale: str | None = None
    device_name: str | None = None


class LinkRequest(BaseModel):
    id_token: str
    step_up_token: str | None = None


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _session_service(request: Request) -> SessionService:
    return SessionService(request.app.state.db, request.app.state.redis, _settings(request))


def _auth_service(request: Request, verifier: FirebaseVerifier) -> AuthService:
    settings = _settings(request)
    throttle = OtpThrottle(request.app.state.redis, settings)
    return AuthService(request.app.state.db, verifier, throttle, settings)


def _throttle_key(request: Request) -> str:
    client = request.client
    return client.host if client else "unknown"


def _set_cookies(response: Response, minted: MintedSession, settings: Settings) -> None:
    response.set_cookie(
        ACCESS_COOKIE,
        minted.access_token,
        max_age=settings.access_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        minted.refresh_token,
        max_age=settings.refresh_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/auth",
    )


def _clear_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/auth")


async def current_session(request: Request) -> tuple[ObjectId, str]:
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise ApiError(ErrorCode.AUTH_INVALID_TOKEN)
    resolved = await _session_service(request).resolve_access(token)
    if resolved is None:
        raise ApiError(ErrorCode.AUTH_INVALID_TOKEN)
    return resolved


CurrentSession = Annotated[tuple[ObjectId, str], Depends(current_session)]
Verifier = Annotated[FirebaseVerifier, Depends(get_verifier)]


@router.post("/session")
async def exchange_session(
    body: ExchangeRequest, request: Request, response: Response, verifier: Verifier
) -> dict[str, Any]:
    service = _auth_service(request, verifier)
    user, is_new = await service.exchange(
        body.id_token, _throttle_key(request), body.date_of_birth, body.locale
    )
    minted = await _session_service(request).create(user["_id"], body.device_name)
    _set_cookies(response, minted, _settings(request))
    return {"user_id": str(user["_id"]), "locale": user["locale"], "is_new_user": is_new}


@router.post("/session/refresh")
async def refresh_session(
    request: Request, response: Response
) -> dict[str, Any]:
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise ApiError(ErrorCode.AUTH_SESSION_EXPIRED)
    user_id, minted = await _session_service(request).rotate(token)
    _set_cookies(response, minted, _settings(request))
    return {"user_id": str(user_id)}


@router.delete("/session", status_code=204)
async def sign_out(request: Request, response: Response, session: CurrentSession) -> None:
    _, session_id = session
    await _session_service(request).revoke(session_id)
    _clear_cookies(response)


@router.get("/sessions")
async def list_sessions(request: Request, session: CurrentSession) -> dict[str, Any]:
    user_id, session_id = session
    sessions = await _session_service(request).list_for_user(user_id, session_id)
    return {"sessions": sessions}


@router.delete("/sessions/{session_id}", status_code=204)
async def revoke_session(
    session_id: str, request: Request, session: CurrentSession
) -> None:
    user_id, _ = session
    service = _session_service(request)
    target = await request.app.state.db.sessions.find_one({"_id": ObjectId(session_id)})
    if target is None or target["user_id"] != user_id:
        raise ApiError(ErrorCode.AUTH_FORBIDDEN)
    await service.revoke(session_id)


@router.post("/link")
async def link_provider(
    body: LinkRequest, request: Request, session: CurrentSession, verifier: Verifier
) -> dict[str, Any]:
    user_id, _ = session
    service = _auth_service(request, verifier)
    provider = await service.link(
        user_id, body.id_token, _throttle_key(request), body.step_up_token
    )
    return {"linked": True, "provider": provider}


@router.get("/link/conflict")
async def link_conflict(
    request: Request, session: CurrentSession, verifier: Verifier
) -> dict[str, Any]:
    user_id, _ = session
    return await _auth_service(request, verifier).pending_conflict(user_id)
