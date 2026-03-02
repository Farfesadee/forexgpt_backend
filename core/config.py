"""
core/config.py — Environment variables and application settings.
All secrets loaded from .env — never hardcoded.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List


class Settings(BaseSettings):

    # ── Anthropic ─────────────────────────────────────────────────────────────
    ANTHROPIC_API_KEY: str = Field(..., env="ANTHROPIC_API_KEY")
    CLAUDE_MODEL: str = "claude-sonnet-4-6"

    # ── Supabase ──────────────────────────────────────────────────────────────
    SUPABASE_URL:              str = Field(..., env="SUPABASE_URL")
    SUPABASE_ANON_KEY:         str = Field(..., env="SUPABASE_ANON_KEY")
    SUPABASE_SERVICE_ROLE_KEY: str = Field(..., env="SUPABASE_SERVICE_ROLE_KEY")

    # JWT secret — found at: Supabase Dashboard → Project Settings → API → JWT Secret
    # Used by auth_middleware.py to verify tokens locally (no network call)
    SUPABASE_JWT_SECRET: str = Field(..., env="SUPABASE_JWT_SECRET")

    # Frontend URL — used to build password-reset redirect links
    SITE_URL: str = Field("http://localhost:3000", env="SITE_URL")

    # ── Mistral (fine-tuned) — Signal Extraction ──────────────────────────────
    MISTRAL_MODEL_PATH:    str   = Field("models/mistral-7b-forex-finetuned", env="MISTRAL_MODEL_PATH")
    MISTRAL_DEVICE:        str   = Field("cuda", env="MISTRAL_DEVICE")
    MISTRAL_MAX_NEW_TOKENS: int  = 512
    MISTRAL_TEMPERATURE:   float = 0.1

    # ── Mistral (base) — Mentor draft + CodeGen draft ─────────────────────────
    MISTRAL_API_KEY:         str = Field("", env="MISTRAL_API_KEY")
    MISTRAL_BASE_MODEL_NAME: str = Field("mistral-small-latest", env="MISTRAL_BASE_MODEL_NAME")
    MISTRAL_BASE_MODEL_PATH: str = Field("", env="MISTRAL_BASE_MODEL_PATH")

    # ── E2B Code Sandbox ──────────────────────────────────────────────────────
    E2B_API_KEY:              str = Field("", env="E2B_API_KEY")
    SANDBOX_TIMEOUT_SECONDS:  int = 30

    # ── Backtesting defaults ──────────────────────────────────────────────────
    DEFAULT_INITIAL_CAPITAL:   float = 10_000.0
    DEFAULT_SPREAD_PIPS:       float = 1.0
    DEFAULT_COMMISSION_PER_LOT: float = 3.5

    # ── OANDA (optional — for live market data) ───────────────────────────────
    OANDA_API_KEY:    str = Field("", env="OANDA_API_KEY")
    OANDA_ACCOUNT_ID: str = Field("", env="OANDA_ACCOUNT_ID")

    # ── Security ──────────────────────────────────────────────────────────────
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "https://forexmentor.ai"]
    SECRET_KEY:      str = Field("change-me-in-prod", env="SECRET_KEY")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()