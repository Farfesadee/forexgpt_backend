
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
import jwt as pyjwt
from jwt import PyJWKClient
from supabase import create_client
from core.config import settings
from models.user import JWTPayload

logger = logging.getLogger(__name__)

# FastAPI dependency that extracts Bearer token from Authorization header
_bearer_scheme = HTTPBearer(auto_error=False)
_jwks_client: Optional[PyJWKClient] = None


def _to_jwt_payload(claims: dict, fallback_sub: str = "", fallback_email: str = "") -> JWTPayload:
    now = int(time.time())
    aud = claims.get("aud", "authenticated")
    if isinstance(aud, list):
        aud = aud[0] if aud else "authenticated"

    return JWTPayload(
        sub=claims.get("sub", fallback_sub),
        email=claims.get("email") or fallback_email or "",
        role=claims.get("role", "authenticated"),
        exp=int(claims.get("exp", now + 3600)),
        iat=int(claims.get("iat", now)),
        aud=aud,
    )


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        jwks_url = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"
        _jwks_client = PyJWKClient(
            jwks_url,
            cache_keys=True,
            cache_jwk_set=True,
            lifespan=300,
            timeout=5,
        )
    return _jwks_client


def _verify_with_jwks(token: str, alg: str) -> JWTPayload:
    """
    Verify asymmetric Supabase access tokens against the project's JWKS.
    This keeps authentication local after the first key fetch.
    """
    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        claims = pyjwt.decode(
            token,
            signing_key.key,
            algorithms=[alg],
            audience="authenticated",
            options={"verify_aud": True},
        )
        return _to_jwt_payload(claims)
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"JWKS token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

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

    return _to_jwt_payload(
        claims,
        fallback_sub=res.user.id,
        fallback_email=getattr(res.user, "email", "") or "",
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
        if not settings.SUPABASE_JWT_SECRET:
            logger.info("SUPABASE_JWT_SECRET not configured; using Supabase introspection.")
            return _verify_with_supabase(token)

        try:
            header = jwt.get_unverified_header(token)
            alg = (header or {}).get("alg", "")
        except Exception:
            alg = ""

        # Supabase may issue asymmetric JWTs (e.g. RS256).
        # Verify those against the project's JWKS instead of calling get_user().
        if alg and alg.upper() != "HS256":
            logger.info(f"JWT alg={alg}; verifying with Supabase JWKS.")
            try:
                return _verify_with_jwks(token, alg)
            except HTTPException as jwks_error:
                logger.info(
                    f"JWKS verification failed for alg={alg}; "
                    "falling back to Supabase introspection."
                )
                try:
                    return _verify_with_supabase(token)
                except HTTPException:
                    raise jwks_error

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
            logger.info("JWT uses non-HS256 algorithm; verifying with Supabase JWKS.")
            try:
                header = jwt.get_unverified_header(token)
                alg = (header or {}).get("alg", "RS256")
            except Exception:
                alg = "RS256"
            try:
                return _verify_with_jwks(token, alg)
            except HTTPException as jwks_error:
                logger.info("JWKS verification failed; falling back to Supabase introspection.")
                try:
                    return _verify_with_supabase(token)
                except HTTPException:
                    raise jwks_error

        logger.warning(f"JWT verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        err = str(e).lower()
        if "alg value is not allowed" in err:
            logger.info("JWT uses non-HS256 algorithm; verifying with Supabase JWKS.")
            try:
                header = jwt.get_unverified_header(token)
                alg = (header or {}).get("alg", "RS256")
            except Exception:
                alg = "RS256"
            try:
                return _verify_with_jwks(token, alg)
            except HTTPException as jwks_error:
                logger.info("JWKS verification failed; falling back to Supabase introspection.")
                try:
                    return _verify_with_supabase(token)
                except HTTPException:
                    raise jwks_error
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
