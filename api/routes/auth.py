
"""
api/routes/auth.py — Authentication & user profile endpoints.

All auth operations delegate to Supabase Auth (GoTrue).
The backend never stores passwords — Supabase handles that entirely.

Endpoints:
  POST   /auth/register           Register with email + password
  POST   /auth/confirm                 Exchange token_hash from confirmation email → session
  POST   /auth/resend-confirmation     Resend confirmation email (expired or lost)
  POST   /auth/login              Login → returns JWT access + refresh tokens
  POST   /auth/logout             Invalidate the current session
  POST   /auth/refresh            Exchange refresh token for a new access token
  POST   /auth/password-reset     Send password reset email
  POST   /auth/password-update    Set new password (after reset flow)
  POST   /auth/oauth/{provider}   OAuth login (Google, GitHub)

  GET    /auth/me                 Get current user's profile
  PATCH  /auth/me                 Update profile (display_name, level, pairs, etc.)
  GET    /auth/me/dashboard       Aggregated stats across all 5 modules

  GET    /auth/session            Check if current token is valid (health check)
  
  Email confirmation flow:
  1. POST /auth/register  →  Supabase sends email with link to {SITE_URL}/auth/confirm?token_hash=...&type=signup
  2. User clicks link     →  Browser navigates to your frontend at that URL
  3. Frontend extracts token_hash + type from URL query params
  4. Frontend calls POST /auth/confirm with those values
  5. /auth/confirm calls Supabase verifyOtp → account activated → returns LoginResponse
  6. Frontend stores tokens and redirects into the app

  If the link expires (24h default): POST /auth/resend-confirmation

Supabase dashboard requirements (fix before testing):
  Authentication → URL Configuration → Redirect URLs:
    Add: {SITE_URL}/auth/confirm
    Add: {SITE_URL}/auth/reset-password
"""

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from supabase import create_client, Client

from core.config import settings
from core.database import db
from api.middleware.auth_middleware import get_current_user
from models.user import (
    RegisterRequest, RegisterResponse,
    LoginRequest, LoginResponse,
    RefreshRequest, TokenPair,
    LogoutResponse,
    PasswordResetRequest, PasswordUpdateRequest,
    OAuthCallbackRequest, EmailConfirmRequest,
    ProfileUpdateRequest, ProfileUpdateResponse,
    UserProfile, UserDashboard, ActivityLogItem,
    JWTPayload,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Supabase Auth client (uses anon key for auth operations)
# Note: auth operations use the anon key, not the service_role key.
# The service_role key is used only for DB reads/writes in core/database.py.
# _ was used to indicate "private" (meant to be used only within this module), but it's needed in multiple endpoints so it's defined as a helper function instead of a global variable.

def _auth_client() -> Client:
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)

def _build_token_pair(session) -> TokenPair:
    """Convert a Supabase session object into our TokenPair schema."""
    return TokenPair(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        expires_in=session.expires_in or 3600,
    )

def _build_user_profile(raw: dict) -> UserProfile:
    """Convert a profiles table row into the UserProfile schema."""
    return UserProfile(
        id=raw["id"],
        email=raw["email"],
        display_name=raw.get("display_name"),
        avatar_url=raw.get("avatar_url"),
        preferred_pairs=raw.get("preferred_pairs", ["EUR/USD", "GBP/USD"]),
        timezone=raw.get("timezone", "UTC"),
        created_at=raw["created_at"],
        updated_at=raw["updated_at"],
    )


def _frontend_url(path: str, **query_params) -> str:
    base = settings.SITE_URL.rstrip("/")
    query = urlencode({k: v for k, v in query_params.items() if v is not None})
    return f"{base}{path}" + (f"?{query}" if query else "")

# Registration section
@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
@router.post(
    "/auth/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def register(body: RegisterRequest):
    """
    Create a new user account via Supabase Auth.

    Supabase sends a confirmation email by default (configurable in project settings).
    The profile row is auto-created by the `handle_new_user` DB trigger.

    After registration:
    - User receives a confirmation email
    - Profile row is auto-created in public.profiles
    - User must confirm email before logging in (if confirmations are enabled)
    """
    supabase = _auth_client()

    existing_profile = db.profiles.get_by_email(body.email)
    if existing_profile is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    try:
        res = supabase.auth.sign_up({
            "email": body.email,
            "password": body.password,
            "options": {
                "data": {
                    "full_name": body.display_name or body.email.split("@")[0],
                },
                "emailRedirectTo": f"{settings.SITE_URL}/auth/confirm",
            },
        })
    except Exception as e:
        _handle_supabase_auth_error(e, "registration")

    if res.user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration failed. The email may already be in use.",
        )

    # Log the signup activity (profile may not exist yet if email confirmation pending)
    try:
        db.activity.log(
            user_id=res.user.id,
            action="signed_up",
            metadata={"email": body.email},
        )
    except Exception:
        pass  # non-fatal — profile trigger may not have fired yet

    logger.info(f"New user registered: {body.email} (id={res.user.id})")

    return RegisterResponse(
        user_id=res.user.id,
        email=res.user.email,
        requires_confirmation=res.session is None,  # True if email confirmation required
    )
# Email Confirmation Section
@router.post(
    "/confirm",
    response_model=LoginResponse,
    summary="Confirm email address and complete registration",
)
@router.post(
    "/auth/confirm",
    response_model=LoginResponse,
    include_in_schema=False,
)
async def confirm_email(body: "EmailConfirmRequest"):
    """
    Exchanges the `token_hash` from the confirmation email link for a full session.

    **Full confirmation flow:**
    1. User registers → receives confirmation email
    2. User clicks link → browser navigates to `{SITE_URL}/auth/confirm?token_hash=...&type=signup`
    3. Frontend extracts `token_hash` and `type` from the URL query params
    4. Frontend POSTs them to this endpoint: `POST /auth/confirm`
    5. Supabase verifies the token → activates the account → returns a session
    6. This endpoint returns the same `LoginResponse` (tokens + profile) as `/login`
    7. Frontend stores the tokens and redirects the user into the app — they are logged in

    **Request body:**
    ```json
    {
      "token_hash": "pkce_...",
      "type": "signup"
    }
    ```

    The `token_hash` and `type` come directly from the URL params Supabase appends
    to the confirmation link. Do not modify them.

    Errors:
    - 400: Token is malformed or was already used
    - 410: Token has expired (Supabase default expiry: 24 hours — resend via POST /auth/resend-confirmation)
    """
    supabase = _auth_client()

    try:
        res = supabase.auth.verify_otp({
            "token_hash": body.token_hash,
            "type":       body.type,
        })
    except Exception as e:
        err = str(e).lower()
        logger.warning(f"Email confirmation failed: {e}")
        if "expired" in err or "otp" in err:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail=(
                    "This confirmation link has expired or has already been used. "
                    "Request a new one via POST /auth/resend-confirmation."
                ),
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid confirmation link. Please request a new one.",
        )

    if res.session is None or res.user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email confirmation failed. The link may be invalid or already used.",
        )

    # Profile was created by the DB trigger on sign_up.
    # If confirmation was very fast the trigger may not have run yet — retry once.
    raw_profile = None
    for attempt in range(2):
        try:
            raw_profile = db.profiles.get(res.user.id)
            break
        except Exception:
            if attempt == 0:
                import asyncio
                await asyncio.sleep(0.5)  # give the trigger a moment
            else:
                logger.error(f"Profile missing after email confirmation for {res.user.id}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Account confirmed but profile could not be loaded. Please contact support.",
                )

    profile = _build_user_profile(raw_profile)

    db.activity.log(
        user_id=res.user.id,
        action="email_confirmed",
        metadata={"email": res.user.email},
    )
    logger.info(f"Email confirmed: {res.user.email} (id={res.user.id})")

    return LoginResponse(
        tokens=_build_token_pair(res.session),
        user=profile,
    )


@router.get("/auth/confirm", include_in_schema=False)
async def confirm_email_redirect(request: Request):
    return RedirectResponse(
        url=_frontend_url("/auth/confirm", **dict(request.query_params)),
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )


# Resend Confirmation Email 
@router.post(
    "/resend-confirmation",
    status_code=status.HTTP_200_OK,
    summary="Resend the email confirmation link",
)
@router.post(
    "/auth/resend-confirmation",
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def resend_confirmation(body: PasswordResetRequest):
    """
    Resends a confirmation email to the given address if the account exists
    and is not yet confirmed.

    Use this when:
    - The original email never arrived (check spam)
    - The 24-hour link has expired

    Always returns 200 regardless of whether the email exists (prevents enumeration).

    The new link follows the same flow as the original:
    browser → `{SITE_URL}/auth/confirm?token_hash=...&type=signup` → POST /auth/confirm
    """
    supabase = _auth_client()

    try:
        supabase.auth.resend({
            "type":  "signup",
            "email": body.email,
            "options": {
                "emailRedirectTo": f"{settings.SITE_URL}/auth/confirm",
            },
        })
    except Exception as e:
        logger.warning(f"Resend confirmation error for {body.email}: {e}")
        # Always return 200 — never reveal whether the email exists

    return {
        "message": (
            "If an unconfirmed account exists with that email, "
            "a new confirmation link has been sent."
        )
    }


# Login Section
@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Login with email and password",
)
@router.post(
    "/auth/login",
    response_model=LoginResponse,
    include_in_schema=False,
)
async def login(body: LoginRequest):
    """
    Authenticate with email + password.

    Returns:
    - `tokens.access_token`: JWT for API calls (put in Authorization: Bearer header)
    - `tokens.refresh_token`: Long-lived token to get new access tokens
    - `user`: Full user profile

    The access token expires in 1 hour by default (configurable in Supabase dashboard).
    Use POST /auth/refresh before expiry to get a new one without re-logging in.
    """
    supabase = _auth_client()

    try:
        res = supabase.auth.sign_in_with_password({
            "email": body.email,
            "password": body.password,
        })
    except Exception as e:
        _handle_supabase_auth_error(e, "login")

    if res.session is None or res.user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    # Fetch the full profile from our DB
    try:
        raw_profile = db.profiles.get(res.user.id)
        profile = _build_user_profile(raw_profile)
    except Exception as e:
        logger.error(f"Profile fetch failed after login for {res.user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login succeeded but profile could not be loaded.",
        )

    db.activity.log(
        user_id=res.user.id,
        action="signed_in",
        metadata={"email": body.email},
    )

    logger.info(f"User logged in: {body.email} (id={res.user.id})")

    return LoginResponse(
        tokens=_build_token_pair(res.session),
        user=profile,
    )

# Logout Section

@router.post(
    "/logout",
    response_model=LogoutResponse,
    summary="Log out and invalidate the current session",
)
@router.post(
    "/auth/logout",
    response_model=LogoutResponse,
    include_in_schema=False,
)
async def logout(user: JWTPayload = Depends(get_current_user)):
    """
    Signs the user out of the current session.

    Invalidates the refresh token server-side in Supabase.
    The access token remains technically valid until its `exp` timestamp,
    but the refresh token can no longer be used to generate new ones.

    Best practice: the frontend should discard both tokens immediately on logout.
    """
    supabase = _auth_client()

    try:
        supabase.auth.sign_out()
    except Exception as e:
        # Non-fatal — log but don't fail the request
        logger.warning(f"Supabase sign_out error for {user.user_id}: {e}")

    db.activity.log(user_id=user.user_id, action="signed_out")
    logger.info(f"User logged out: {user.user_id}")

    return LogoutResponse()

# Token Refresh Section

@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="Exchange a refresh token for a new access token",
)
@router.post(
    "/auth/refresh",
    response_model=TokenPair,
    include_in_schema=False,
)
async def refresh_token(body: RefreshRequest):
    """
    Get a new access token using a valid refresh token.

    Call this before the access token expires (default: 1 hour).
    Recommended pattern: refresh when < 5 minutes remain on the access token.

    Returns a new TokenPair (both access and refresh tokens are rotated).
    """
    supabase = _auth_client()

    try:
        res = supabase.auth.refresh_session(body.refresh_token)
    except Exception as e:
        _handle_supabase_auth_error(e, "token refresh")

    if res.session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is invalid or has expired. Please log in again.",
        )

    return _build_token_pair(res.session)


# Password Reset Flow Section

@router.post(
    "/password-reset",
    status_code=status.HTTP_200_OK,
    summary="Send a password reset email",
)
@router.post(
    "/auth/password-reset",
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
@router.post(
    "/forgot-password",
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
@router.post(
    "/auth/forgot-password",
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
@router.post(
    "/request-password-reset",
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
@router.post(
    "/password/forgot",
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def request_password_reset(body: PasswordResetRequest):
    """
    Sends a password reset link to the given email address.

    The link redirects to: `{SITE_URL}/auth/reset-password?token=...`
    Configure the redirect URL in Supabase → Authentication → URL Configuration.

    Always returns 200 regardless of whether the email exists (prevents enumeration).
    """
    supabase = _auth_client()

    try:
        supabase.auth.reset_password_email(
            email=body.email,
            options={"redirect_to": f"{settings.SITE_URL}/auth/reset-password"},
        )
    except Exception as e:
        logger.warning(f"Password reset error for {body.email}: {e}")
        if settings.APP_ENV.lower() != "production":
            _handle_supabase_auth_error(e, "password reset")

    return {"message": "If an account exists with that email, a reset link has been sent."}


@router.get("/auth/reset-password", include_in_schema=False)
async def password_reset_redirect(request: Request):
    return RedirectResponse(
        url=_frontend_url("/auth/reset-password", **dict(request.query_params)),
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )

# Password Update Section (after reset flow)
@router.post(
    "/password-update",
    status_code=status.HTTP_200_OK,
    summary="Set a new password (requires valid session from reset link)",
)
@router.post(
    "/auth/password-update",
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def update_password(
    body: PasswordUpdateRequest,
    request: Request,
    user: JWTPayload = Depends(get_current_user),
):
    """
    Updates the user's password.

    The user must be authenticated — Supabase's reset link logs the user in
    automatically with a short-lived session. The frontend captures that session
    and calls this endpoint.
    """
    supabase = _auth_client()
    auth_header = request.headers.get("authorization", "")
    access_token = auth_header.split(" ", 1)[1].strip() if auth_header.lower().startswith("bearer ") else ""
    refresh_token = body.refresh_token or request.headers.get("x-refresh-token")

    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required. Use: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Refresh token required to update password. "
                "Send it in the request body as `refresh_token` or header `X-Refresh-Token`."
            ),
        )

    try:
        supabase.auth.set_session(access_token, refresh_token)
        supabase.auth.update_user({"password": body.new_password})
    except Exception as e:
        _handle_supabase_auth_error(e, "password update")

    db.activity.log(user_id=user.user_id, action="password_updated")
    return {"message": "Password updated successfully. Please log in again."}


# OAuth Section

@router.post(
    "/oauth/{provider}",
    summary="Complete OAuth login (Google or GitHub)",
)
async def oauth_callback(provider: str, body: OAuthCallbackRequest):
    """
    Exchanges an OAuth code for a Supabase session.

    Flow:
    1. Frontend redirects user to Google/GitHub via Supabase OAuth URL
    2. Provider redirects back to frontend with ?code=...
    3. Frontend POSTs the code here → backend exchanges it for tokens
    4. Returns the same TokenPair + UserProfile as /login

    Provider must be 'google' or 'github' (configured in Supabase Auth settings).
    """
    if provider not in ("google", "github"):
        raise HTTPException(status_code=400, detail="Unsupported OAuth provider.")
    if body.provider and body.provider != provider:
        raise HTTPException(status_code=400, detail="OAuth provider mismatch between path and body.")

    supabase = _auth_client()

    try:
        res = supabase.auth.exchange_code_for_session(body.code)
    except Exception as e:
        _handle_supabase_auth_error(e, f"OAuth ({provider})")

    if res.session is None or res.user is None:
        raise HTTPException(status_code=401, detail="OAuth authentication failed.")

    # Fetch profile (auto-created by trigger on first OAuth login)
    try:
        raw_profile = db.profiles.get(res.user.id)
        profile = _build_user_profile(raw_profile)
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="OAuth succeeded but profile could not be loaded.",
        )

    db.activity.log(
        user_id=res.user.id,
        action="signed_in",
        metadata={"provider": provider},
    )

    return LoginResponse(tokens=_build_token_pair(res.session), user=profile)

# Profile Endpoints Section (protected by JWT auth)
# Get current user's profile
@router.get(
    "/me",
    response_model=UserProfile,
    summary="Get the current user's profile",
)
@router.get(
    "/auth/me",
    response_model=UserProfile,
    include_in_schema=False,
)
async def get_me(user: JWTPayload = Depends(get_current_user)):
    """
    Returns the authenticated user's profile from public.profiles.

    Requires: Authorization: Bearer <access_token>
    """
    try:
        raw = db.profiles.get(user.user_id)
        return _build_user_profile(raw)
    except Exception as e:
        logger.error(f"Profile fetch error for {user.user_id}: {e}")
        raise HTTPException(status_code=500, detail="Could not load profile.")

# Updating user's profile
@router.patch(
    "/me",
    response_model=ProfileUpdateResponse,
    summary="Update the current user's profile",
)
@router.patch(
    "/auth/me",
    response_model=ProfileUpdateResponse,
    include_in_schema=False,
)
async def update_me(
    body: ProfileUpdateRequest,
    user: JWTPayload = Depends(get_current_user),
):
    """
    Update mutable profile fields.
    All fields are optional — only supplied fields are updated.

    Updatable fields:
    - display_name
    - avatar_url
    - experience_level  → forwarded to system_prompts.py to tailor LLM responses
    - preferred_pairs   → shown in dashboard / used as defaults in signal extraction
    - timezone          → used for session timestamps
    """
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided to update.")

    try:
        updated_raw = db.profiles.update(user.user_id, updates)
        return ProfileUpdateResponse(profile=_build_user_profile(updated_raw))
    except Exception as e:
        err_text = str(e)
        # Backward-compatibility: some deployed schemas don't have preferred_pairs yet.
        # Retry without that field so other profile fields can still be updated.
        if "preferred_pairs" in updates and "PGRST204" in err_text and "preferred_pairs" in err_text:
            try:
                fallback_updates = {k: v for k, v in updates.items() if k != "preferred_pairs"}
                if not fallback_updates:
                    raise HTTPException(
                        status_code=400,
                        detail="Your profile schema does not support `preferred_pairs` yet.",
                    )
                updated_raw = db.profiles.update(user.user_id, fallback_updates)
                return ProfileUpdateResponse(profile=_build_user_profile(updated_raw))
            except HTTPException:
                raise
            except Exception as inner:
                logger.error(f"Profile update fallback error for {user.user_id}: {inner}")
                raise HTTPException(status_code=500, detail="Profile update failed.")

        logger.error(f"Profile update error for {user.user_id}: {e}")
        raise HTTPException(status_code=500, detail="Profile update failed.")

# Gets aggregated stats across all 5 modules for the dashboard page
@router.get(
    "/me/dashboard",
    response_model=UserDashboard,
    summary="Get aggregated usage stats across all 5 modules",
)
@router.get(
    "/auth/me/dashboard",
    response_model=UserDashboard,
    include_in_schema=False,
)
async def get_dashboard(user: JWTPayload = Depends(get_current_user)):
    """
    Returns the user's dashboard — aggregated statistics from the
    `user_dashboard` Supabase VIEW, which joins:
    - profiles (counters and user info)
    - mentor_conversations
    - quant_sessions
    - signals
    - strategies
    - backtests

    Used by the frontend home/dashboard page to show overall learning progress.
    """
    try:
        raw = db.profiles.get_dashboard(user.user_id)
        return UserDashboard(**raw)
    except Exception as e:
        logger.error(f"Dashboard fetch error for {user.user_id}: {e}")
        raise HTTPException(status_code=500, detail="Could not load dashboard.")

# Activity Log
@router.get(
    "/activity",
    response_model=list[ActivityLogItem],
    summary="Get recent activity log entries for the current user",
)
@router.get(
    "/auth/activity",
    response_model=list[ActivityLogItem],
    include_in_schema=False,
)
async def get_activity(
    limit: int = 20,
    user: JWTPayload = Depends(get_current_user),
):
    try:
        return db.activity.list(user.user_id, limit=limit)
    except Exception as e:
        logger.error(f"Activity log fetch error for {user.user_id}: {e}")
        raise HTTPException(status_code=500, detail="Could not load activity log.")

# Session Health Check Section

@router.get(
    "/session",
    summary="Verify the current token is valid",
)
@router.get(
    "/auth/session",
    include_in_schema=False,
)
async def check_session(user: JWTPayload = Depends(get_current_user)):
    """
    Lightweight endpoint to verify the access token is still valid.
    Returns the token's expiry time.

    Use this on app startup to decide whether to prompt the user to log in.
    """
    import datetime
    return {
        "valid": True,
        "user_id": user.user_id,
        "email": user.email,
        "expires_at": datetime.datetime.fromtimestamp(user.exp).isoformat(),
    }

# Error Helper Section

def _handle_supabase_auth_error(exc: Exception, context: str) -> None:
    """
    Translate Supabase auth exceptions into clean HTTP errors.
    Never leaks internal error details to the client.
    """
    err_str = str(exc).lower()
    logger.warning(f"Supabase auth error during {context}: {exc}")

    if "invalid login credentials" in err_str or "invalid credentials" in err_str:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    if "email not confirmed" in err_str:
        raise HTTPException(status_code=401, detail="Please confirm your email before logging in.")
    if "confirmation email" in err_str or "send" in err_str and "email" in err_str:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The authentication server failed to send a verification email. Please check your Supabase SMTP settings."
        )
    if "user already registered" in err_str or "already been registered" in err_str:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    if "password" in err_str and "weak" in err_str:
        raise HTTPException(status_code=400, detail="Password does not meet security requirements.")
    if "rate limit" in err_str or "too many" in err_str:
        raise HTTPException(status_code=429, detail="Too many attempts. Please wait and try again.")
    if "token" in err_str and ("invalid" in err_str or "expired" in err_str):
        raise HTTPException(status_code=401, detail="Session token is invalid or expired. Please log in again.")
    if "provider is not enabled" in err_str or "oauth provider not enabled" in err_str:
        raise HTTPException(
            status_code=400,
            detail="Google OAuth is not enabled in Supabase Auth settings.",
        )
    if "invalid grant" in err_str or "invalid authorization code" in err_str or "code_verifier" in err_str:
        raise HTTPException(
            status_code=401,
            detail="OAuth code is invalid or expired. Start Google login again.",
        )
    if "redirect" in err_str and "mismatch" in err_str:
        raise HTTPException(
            status_code=400,
            detail="OAuth redirect URL mismatch. Check Supabase Auth URL configuration.",
        )
    if "error sending confirmation email" in err_str or "smtp" in err_str:
        raise HTTPException(
            status_code=503,
            detail=(
                "Registration could not send the confirmation email. "
                "Check Supabase Auth email provider/SMTP settings and allowed redirect URLs."
            ),
        )

    # Fallback — don't expose raw Supabase errors
    raise HTTPException(status_code=500, detail=f"Authentication service error during {context}.")
