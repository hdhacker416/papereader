from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from services import auth_service


class AuthUserResponse(BaseModel):
    id: str
    email: str
    name: str


class AuthRequest(BaseModel):
    email: str
    password: str
    name: str | None = None


class AuthResponse(BaseModel):
    user: AuthUserResponse
    token: str | None = None
    expires_at: datetime | None = None


router = APIRouter(
    prefix="/api/auth",
    tags=["auth"],
)


def _serialize_user(user: auth_service.AuthUser) -> AuthUserResponse:
    return AuthUserResponse(id=user.id, email=user.email, name=user.name)


@router.get("/me", response_model=AuthResponse)
def me(request: Request) -> AuthResponse:
    user = auth_service.require_current_user(request)
    return AuthResponse(user=_serialize_user(user))


@router.post("/register", response_model=AuthResponse)
def register(payload: AuthRequest, request: Request, response: Response) -> AuthResponse:
    user = auth_service.register_user(payload.email, payload.password, payload.name)
    token, expires_at = auth_service.create_session(user.id)
    auth_service.set_session_cookie(response, request, token, expires_at)
    return AuthResponse(user=_serialize_user(user), token=token, expires_at=expires_at)


@router.post("/login", response_model=AuthResponse)
def login(payload: AuthRequest, request: Request, response: Response) -> AuthResponse:
    user = auth_service.authenticate_user(payload.email, payload.password)
    token, expires_at = auth_service.create_session(user.id)
    auth_service.set_session_cookie(response, request, token, expires_at)
    return AuthResponse(user=_serialize_user(user), token=token, expires_at=expires_at)


@router.post("/logout")
def logout(request: Request, response: Response):
    auth_service.delete_session(auth_service.get_request_session_token(request))
    auth_service.clear_session_cookie(response)
    return {"ok": True}
