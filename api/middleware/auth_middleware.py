
"""
api/middleware/auth_middleware.py — JWT verification for all protected routes.

How it works:
  1. Every request to a protected route passes through get_current_user()
  2. It extracts the Bearer token from the Authorization header
  3. The token is verified against Supabase's JWT secret (locally — no network call)
  4. The decoded payload is returned as a JWTPayload for use in route handlers

Usage in routes:
    from api.middleware.auth_middleware import get_current_user
    from models.user import JWTPayload

    @router.get("/protected")
    async def protected_route(user: JWTPayload = Depends(get_current_user)):
        ...  # user.user_id is available here

Two verification modes:
  - Local JWT verification (default, fast, offline-capable):
      Uses python-jose to verify with SUPABASE_JWT_SECRET
  - Supabase introspection (optional, for revocation checks):
      Calls Supabase /auth/v1/user with the token
"""

import logging
import time
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt, ExpiredSignatureError
from supabase import create_client
from core.config import settings
from models.user import JWTPayload

logger = logging.getLogger(__name__)

# FastAPI dependency that extracts Bearer token from Authorization header
_bearer_scheme = HTTPBearer(auto_error=False)

def _verify_with_supabase(token: str) -> JWTPayload:
    """
    Verify token server-side with Supabase Auth.
    Works for both HS256 and asymmetric (e.g. RS256) projects.
    """
    try:
        supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
        res = supabase.auth.get_user(token)
        if res is None or res.user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token.",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Supabase token introspection failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        claims = jwt.get_unverified_claims(token)
    except JWTError:
        claims = {}

    now = int(time.time())
    exp = claims.get("exp")
    if isinstance(exp, (int, float)) and exp < now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return JWTPayload(
        sub=claims.get("sub", res.user.id),
        email=claims.get("email") or getattr(res.user, "email", "") or "",
        role=claims.get("role", "authenticated"),
        exp=int(claims.get("exp", now + 3600)),
        iat=int(claims.get("iat", now)),
        aud=claims.get("aud", "authenticated"),
    )

# Core Verification 
def _verify_jwt(token: str) -> JWTPayload:
    """
    Verify a Supabase JWT locally using the project's JWT secret.

    Supabase signs all tokens with HS256 and the JWT secret found at:
    Project Settings → API → JWT Settings → JWT Secret

    Raises HTTPException on any verification failure.
    """
    try:
        try:
            header = jwt.get_unverified_header(token)
            alg = (header or {}).get("alg", "")
        except Exception:
            alg = ""

        # Supabase may issue asymmetric JWTs (e.g. RS256) depending on project config.
        # For any non-HS256 token, verify with Supabase directly.
        if alg and alg.upper() != "HS256":
            logger.info(f"JWT alg={alg}; using Supabase introspection.")
            return _verify_with_supabase(token)

        payload = jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
            options={"verify_aud": True},
        )

        # Check expiry explicitly (jose verifies this but we log it clearly)
        if payload.get("exp", 0) < time.time():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired. Please log in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return JWTPayload(**payload)

    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError as e:
        err = str(e).lower()
        if "alg value is not allowed" in err:
            logger.info("JWT uses non-HS256 algorithm; falling back to Supabase introspection.")
            return _verify_with_supabase(token)

        logger.warning(f"JWT verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        err = str(e).lower()
        if "alg value is not allowed" in err:
            logger.info("JWT uses non-HS256 algorithm; falling back to Supabase introspection.")
            return _verify_with_supabase(token)
        logger.warning(f"JWT verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

# FastAPI Dependencies 

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> JWTPayload:
    """
    FastAPI dependency — extracts and verifies the JWT from the Authorization header.

    Inject into any route that requires authentication:
        user: JWTPayload = Depends(get_current_user)

    Raises 401 if:
        - No Authorization header present
        - Token is malformed, expired, or has invalid signature
        - Token audience is not 'authenticated'
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required. Use: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return _verify_jwt(credentials.credentials)


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> Optional[JWTPayload]:
    """
    Like get_current_user but returns None instead of raising for unauthenticated requests.
    Use for routes that have different behaviour for logged-in vs anonymous users.
    """
    if credentials is None or not credentials.credentials:
        return None
    try:
        return _verify_jwt(credentials.credentials)
    except HTTPException:
        return None


async def require_pro_plan(user: JWTPayload = Depends(get_current_user)) -> JWTPayload:
    """
    Dependency that additionally checks the user has a pro or enterprise plan.
    Used for premium features (e.g. unlimited backtests, advanced signal extraction).

    Reads the plan from the profiles table — not from the JWT (which doesn't carry plan info).
    """
    from core.database import db

    try:
        profile = db.profiles.get(user.user_id)
        plan = profile.get("plan", "free")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not verify user plan.",
        )

    if plan not in ("pro", "enterprise"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This feature requires a Pro or Enterprise plan.",
            headers={"X-Upgrade-URL": "/pricing"},
        )

    return user
