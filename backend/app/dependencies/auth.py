import logging

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.db.supabase import get_supabase

logger = logging.getLogger(__name__)
_bearer = HTTPBearer(auto_error=False)

_INVALID = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
_UPSTREAM = HTTPException(
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    detail="Auth service temporarily unavailable. Please retry.",
)


def _is_connection_error(e: Exception) -> bool:
    """True for transient transport/connection failures (not bad credentials).

    Covers httpx transport errors plus h2 GOAWAY/ConnectionTerminated, which
    surface as RemoteProtocolError or by class name string in wrapped errors.
    """
    if isinstance(e, (httpx.TransportError, httpx.RemoteProtocolError)):
        return True
    blob = f"{type(e).__name__}: {e}".lower()
    return any(
        s in blob
        for s in ("server disconnected", "connectionterminated", "connection reset", "goaway")
    )


def _user_from_claims(claims: dict) -> dict:
    sub = claims.get("sub")
    if not sub:
        raise _INVALID
    return {"user_id": sub, "email": claims.get("email") or ""}


def _verify_local(token: str) -> dict | None:
    """Verify the JWT signature locally (no network). Returns the user on
    success, or None if the token can't be locally verified — the caller then
    falls back to the authoritative remote check so a misconfigured secret or
    a non-HS256 signing key never locks out a valid session."""
    try:
        claims = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.PyJWTError as e:
        logger.info(f"Local JWT not accepted, falling back to remote: {type(e).__name__}: {e}")
        return None
    return _user_from_claims(claims)


def _verify_remote(token: str) -> dict:
    """Validate via Supabase auth, retrying once on transient connection drops.
    Connection failures -> 503 (not 401) so valid sessions aren't logged out."""
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            response = get_supabase().auth.get_user(token)
            user = response.user
            if not user:
                raise _INVALID
            return {"user_id": user.id, "email": user.email or ""}
        except HTTPException:
            raise
        except Exception as e:
            if _is_connection_error(e):
                last_err = e
                logger.warning(f"Auth upstream connection error (attempt {attempt + 1}/2): {e}")
                continue
            logger.warning(f"Auth failed: {e}")
            raise _INVALID
    logger.error(f"Auth upstream unavailable after retry: {last_err}")
    raise _UPSTREAM


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    token = credentials.credentials
    if settings.supabase_jwt_secret:
        user = _verify_local(token)
        if user is not None:
            return user
    return _verify_remote(token)
