"""Token-based auth for the API router.

_ACTIVE_TOKEN == None  → open (WebUI / existing tests pass unchanged).
_ACTIVE_TOKEN != None  → ``Authorization: Bearer <token>`` required.
"""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException

# Module-level mutable state; monkeypatched in tests.
_ACTIVE_TOKEN: str | None = None


def new_token() -> str:
    """Generate a new token, store it, and return it."""
    global _ACTIVE_TOKEN
    _ACTIVE_TOKEN = secrets.token_urlsafe(32)
    return _ACTIVE_TOKEN


async def require_token(authorization: str | None = Header(None)) -> None:
    """FastAPI dependency: no-op when token is None, else validate Bearer."""
    if _ACTIVE_TOKEN is None:
        return
    if authorization is None or not secrets.compare_digest(
        authorization, f"Bearer {_ACTIVE_TOKEN}"
    ):
        raise HTTPException(status_code=401, detail="Not authenticated")
