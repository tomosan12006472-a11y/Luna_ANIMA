from __future__ import annotations

import secrets

from fastapi import HTTPException, Response

from .config import APP_PIN

SESSION_COOKIE_NAME = "anima_claude_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30
SESSIONS: set[str] = set()


def require_auth(session: str | None) -> None:
    if session not in SESSIONS:
        raise HTTPException(status_code=401, detail="login required")


def validate_login_pin(pin: str) -> None:
    if pin != APP_PIN:
        raise HTTPException(status_code=403, detail="PINが違います")


def create_session_token() -> str:
    token = secrets.token_urlsafe(24)
    SESSIONS.add(token)
    return token


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        max_age=SESSION_MAX_AGE_SECONDS,
    )
