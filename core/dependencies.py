# from core.database import supabase
# from core.hf_client import mistral_client, hf_client
# from core.config import settings
# from services.mentor_service import MentorService
# from services.codegen_service import CodeGenService
# from services.signal_service import SignalService

# def get_mentor_service() -> MentorService:
#     return MentorService(
#         mistral_client, 
#         supabase, 
#         model_id=settings.MISTRAL_MODEL_ID
#     )

# def get_codegen_service() -> CodeGenService:
#     return CodeGenService(
#         mistral_client, 
#         supabase, 
#         model_id=settings.MISTRAL_MODEL_ID
#     )

# def get_signal_service() -> SignalService:
#     return SignalService(
#         hf_client,       # uses HuggingFace, not Mistral
#         supabase, 
#         model_id=settings.SIGNAL_MODEL_ID
#     )




#              ..
# """
# core/dependencies.py
# FastAPI dependency injection factory.
# Services import db directly from core.database.
# """

# from core.hf_client import mistral_client, hf_client
# from core.config import settings
# from services.mentor_service import MentorService
# from services.codegen_service import CodeGenService
# from services.signal_service import SignalService
# from services.backtest_service import BacktestService


# def get_mentor_service() -> MentorService:
#     return MentorService(
#         mistral_client=mistral_client,
#         model_id=settings.MISTRAL_MODEL_ID,
#     )


# def get_codegen_service() -> CodeGenService:
#     return CodeGenService(
#         mistral_client=mistral_client,
#         model_id=settings.MISTRAL_MODEL_ID,
#     )


# def get_signal_service() -> SignalService:
#     return SignalService(
#         hf_client=hf_client,
#         model_id=settings.SIGNAL_MODEL_ID,
#     )


                # ..
# def get_signal_service() -> SignalService:
#     return SignalService(
#         mistral_client=mistral_client,
#         model_id=settings.SIGNAL_MODEL_ID,
#     )


# def get_backtest_service() -> BacktestService:
#     return BacktestService()





















# """
# core/dependencies.py
# FastAPI dependency injection factory.
# Services import db directly from core.database.
# """

# import os
# from fastapi import Depends, HTTPException, status
# from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
# from jose import JWTError, jwt
# from dotenv import load_dotenv

# from core.hf_client import mistral_client, hf_client
# from core.config import settings
# from services.mentor_service import MentorService
# from services.codegen_service import CodeGenService
# from services.signal_service import SignalService
# from services.backtest_service import BacktestService







# load_dotenv()


# # ============================================================================
# # JWT AUTH
# # ============================================================================

# JWT_SECRET    = os.getenv("JWT_SECRET")
# JWT_ALGORITHM = "HS256"

# _bearer = HTTPBearer()


# def verify_token(
#     credentials: HTTPAuthorizationCredentials = Depends(_bearer),
# ) -> None:
#     """
#     FastAPI dependency — validates the Bearer JWT token.
#     Raises 401 if the token is missing, expired, or invalid.
#     Does NOT extract or require user_id — just checks the token is valid.

#     Usage:
#         @router.post("/some-endpoint", dependencies=[Depends(verify_token)])
#     """
#     token = credentials.credentials
#     try:
#         jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
#     except JWTError:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Invalid or expired token.",
#             headers={"WWW-Authenticate": "Bearer"},
#         )


# # ============================================================================
# # SERVICE FACTORIES
# # ============================================================================

# def get_mentor_service() -> MentorService:
#     return MentorService(
#         mistral_client=mistral_client,
#         model_id=settings.MISTRAL_MODEL_ID,
#     )


# def get_codegen_service() -> CodeGenService:
#     return CodeGenService(
#         mistral_client=mistral_client,
#         model_id=settings.MISTRAL_MODEL_ID,
#     )


# def get_signal_service() -> SignalService:
#     return SignalService(
#         mistral_client=mistral_client,
#         model_id=settings.SIGNAL_MODEL_ID,
#     )


# def get_backtest_service() -> BacktestService:
#     return BacktestService()















































# old dep

# """
# core/dependencies.py
# FastAPI dependency injection factory.
# """

# import os
# from fastapi import Depends, HTTPException, status
# from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
# from jose import JWTError, jwt
# from dotenv import load_dotenv

# from core.hf_client import mistral_client, hf_client
# # from core.database import supabase                      # ← add this import back
# from core.database import db
# from core.config import settings
# from services.mentor_service import MentorService
# from services.codegen_service import CodeGenService
# from services.signal_service import SignalService
# from services.backtest_service import BacktestService

# load_dotenv()

# # ============================================================================
# # DEV MODE — set DEV_MODE=true in your .env to skip auth entirely
# # ============================================================================
 
# DEV_MODE    = os.getenv("DEV_MODE", "false").lower() == "true"
# DEV_USER_ID = "00000000-0000-0000-0000-000000000001"   # fake user_id used in dev mode

# # ============================================================================
# # JWT AUTH
# # ============================================================================

# JWT_SECRET    = os.getenv("JWT_SECRET")
# JWT_ALGORITHM = "HS256"

# _bearer = HTTPBearer()


# def verify_token(
#     credentials: HTTPAuthorizationCredentials = Depends(_bearer),
# ) -> None:
#     token = credentials.credentials
#     try:
#         jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
#     except JWTError:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Invalid or expired token.",
#             headers={"WWW-Authenticate": "Bearer"},
#         )

# # core/dependencies.py

# def get_current_user_id(
#     credentials: HTTPAuthorizationCredentials = Depends(_bearer),
# ) -> str:
#     """
#     Validates the Bearer JWT and returns the user_id from the token payload.
#     Raises 401 if invalid or expired.
#     """
#     token = credentials.credentials
#     try:
#         payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
#         user_id = payload.get("sub")
#         if not user_id:
#             raise HTTPException(
#                 status_code=status.HTTP_401_UNAUTHORIZED,
#                 detail="Token missing user ID.",
#             )
#         return user_id
#     except JWTError:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Invalid or expired token.",
#             headers={"WWW-Authenticate": "Bearer"},
#         )
    
# # ============================================================================
# # SERVICE FACTORIES
# # ============================================================================

# def get_mentor_service() -> MentorService:
#     return MentorService(
#         mistral_client = mistral_client,
#         db             = db,              # ← pass db
#         model_id       = settings.MISTRAL_MODEL_ID,
#     )


# def get_codegen_service() -> CodeGenService:
#     return CodeGenService(
#         mistral_client=mistral_client,
#         model_id=settings.MISTRAL_MODEL_ID,
#     )


# def get_signal_service() -> SignalService:
#     return SignalService(
#         mistral_client=mistral_client,
#         model_id=settings.SIGNAL_MODEL_ID,
#     )


# def get_backtest_service() -> BacktestService:
#     return BacktestService()

































































# """
# core/dependencies.py
# FastAPI dependency injection factory.
# """

# import os
# from fastapi import Depends, HTTPException, status
# from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
# from jose import JWTError, jwt
# from dotenv import load_dotenv

# from core.hf_client import mistral_client, hf_client
# from core.database import db
# from core.config import settings
# from services.mentor_service import MentorService
# from services.codegen_service import CodeGenService
# from services.signal_service import SignalService
# from services.backtest_service import BacktestService

# load_dotenv()

# # ============================================================================
# # DEV MODE — set DEV_MODE=true in your .env to skip auth entirely
# # ============================================================================

# DEV_MODE    = os.getenv("DEV_MODE", "false").lower() == "true"
# DEV_USER_ID = "00000000-0000-0000-0000-000000000001"   # fake user_id used in dev mode

# # ============================================================================
# # JWT AUTH
# # ============================================================================

# JWT_SECRET    = os.getenv("JWT_SECRET")
# JWT_ALGORITHM = "HS256"

# # auto_error=False so missing token doesn't crash in dev mode
# _bearer = HTTPBearer(auto_error=False)


# def get_current_user_id(
#     credentials: HTTPAuthorizationCredentials = Depends(_bearer),
# ) -> str:
#     """
#     Extracts and validates the user_id from the Bearer JWT token.

#     DEV_MODE=true in .env  → skips auth, returns DEV_USER_ID
#     Production             → validates token, returns user_id from 'sub' claim
#     """
#     if DEV_MODE:
#         return DEV_USER_ID

#     if not credentials:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Authorization token required.",
#             headers={"WWW-Authenticate": "Bearer"},
#         )

#     try:
#         payload = jwt.decode(
#             credentials.credentials,
#             JWT_SECRET,
#             algorithms=[JWT_ALGORITHM],
#         )
#         user_id = payload.get("sub")
#         if not user_id:
#             raise HTTPException(
#                 status_code=status.HTTP_401_UNAUTHORIZED,
#                 detail="Token missing user ID.",
#             )
#         return user_id
#     except JWTError:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Invalid or expired token.",
#             headers={"WWW-Authenticate": "Bearer"},
#         )


# def verify_token(
#     credentials: HTTPAuthorizationCredentials = Depends(_bearer),
# ) -> None:
#     """Simple token check — use get_current_user_id when you need the user_id."""
#     if DEV_MODE:
#         return
#     get_current_user_id(credentials)


# # ============================================================================
# # SERVICE FACTORIES
# # ============================================================================

# def get_mentor_service() -> MentorService:
#     return MentorService(
#         mistral_client = mistral_client,
#         db             = db,
#         model_id       = settings.MISTRAL_MODEL_ID,
#     )


# def get_codegen_service() -> CodeGenService:
#     return CodeGenService(
#         mistral_client=mistral_client,
#         model_id=settings.MISTRAL_MODEL_ID,
#     )


# def get_signal_service() -> SignalService:
#     return SignalService(
#         mistral_client=mistral_client,
#         model_id=settings.SIGNAL_MODEL_ID,
#     )


# def get_backtest_service() -> BacktestService:
#     return BacktestService()

























"""
core/dependencies.py
FastAPI dependency injection factory.
"""

from core.hf_client import mistral_client, hf_client
from core.database import db
from core.config import settings
from services.mentor_service import MentorService
from services.codegen_service import CodeGenService
from services.signal_service import SignalService
from services.backtest_service import BacktestService


def get_mentor_service() -> MentorService:
    return MentorService(
        mistral_client = mistral_client,
        db             = db,
        model_id       = settings.MISTRAL_MODEL_ID,
    )


def get_codegen_service() -> CodeGenService:
    return CodeGenService(
        mistral_client=mistral_client,
        model_id=settings.MISTRAL_MODEL_ID,
    )


def get_signal_service() -> SignalService:
    return SignalService(
        mistral_client=mistral_client,
        model_id=settings.SIGNAL_MODEL_ID,
    )


def get_backtest_service() -> BacktestService:
    return BacktestService()