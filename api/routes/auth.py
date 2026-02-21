import logging
from fastapi import APIRouter, HTTPException
from models.user import RegisterRequest, LoginRequest, AuthResponse
from core.database import get_supabase_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=AuthResponse)
async def register(body: RegisterRequest):
    client = get_supabase_auth()
    try:
        res = client.auth.sign_up({
            "email": body.email,
            "password": body.password,
            "options": {"data": {"full_name": body.full_name}},
        })
        if res.user is None:
            raise HTTPException(status_code=400, detail="Registration failed.")
        logger.info(f"New user registered: {body.email}")
        return AuthResponse(
            access_token=res.session.access_token,
            user_id=str(res.user.id),
            email=res.user.email,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest):
    client = get_supabase_auth()
    try:
        res = client.auth.sign_in_with_password({
            "email": body.email,
            "password": body.password,
        })
        if res.user is None:
            raise HTTPException(status_code=401, detail="Invalid credentials.")
        logger.info(f"User logged in: {body.email}")
        return AuthResponse(
            access_token=res.session.access_token,
            user_id=str(res.user.id),
            email=res.user.email,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=401, detail=str(e))