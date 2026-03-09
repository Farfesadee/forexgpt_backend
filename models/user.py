"""
models/user.py — Pydantic schemas for auth and user profile.

Covers all request/response shapes for:
  - api/routes/auth.py  (register, login, logout, refresh, password reset)
  - api/routes/auth.py  (profile read/update, dashboard)
"""

from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum


class ExperienceLevel(str, Enum):
    BEGINNER     = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED     = "advanced"

# # Auth Request Schemas 
class RegisterRequest(BaseModel):
    email:        EmailStr
    password:     str = Field(..., min_length=8, max_length=128)
    display_name: Optional[str] = Field(None, min_length=2, max_length=80)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v

    model_config = {"json_schema_extra": {"example": {
        "email": "trader@gmail.com",
        "password": "SecurePass1",
        "display_name": "Alex Trader",
    }}}

class LoginRequest(BaseModel):
    email:    EmailStr
    password: str = Field(..., min_length=1)

    model_config = {"json_schema_extra": {"example": {
        "email": "trader@example.com",
        "password": "SecurePass1",
    }}}

class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=10)

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordUpdateRequest(BaseModel):
    """Used after clicking the reset link — Supabase sends the user back with a token."""
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v

class EmailConfirmRequest(BaseModel):
    """
    POST /auth/confirm

    The frontend extracts these two values from the URL query params that
    Supabase appends to the confirmation link:
      {SITE_URL}/auth/confirm?token_hash=<token_hash>&type=signup

    token_hash : the opaque token from the URL — pass it through verbatim
    type       : always "signup" for email confirmation links;
                 "recovery" for password-reset links (handled by /auth/password-update)
    """
    token_hash: str = Field(..., min_length=10, description="The token_hash param from the confirmation URL.")
    type:       str = Field("signup", pattern="^(signup|recovery|invite|email_change)$",
                            description="OTP type from the URL — almost always 'signup'.")

    model_config = {"json_schema_extra": {"example": {
        "token_hash": "pkce_6b4f2e1a9c3d8f7e2b5a4c1d9e8f3a2b...",
        "type":       "signup",
    }}}
    
class OAuthCallbackRequest(BaseModel):
    """For Google / GitHub OAuth — frontend sends the code from the OAuth redirect."""
    provider: Optional[str] = Field(default=None, pattern="^(google|github)$")
    code:     str

#  Auth Response Schemas 

class TokenPair(BaseModel):
    """Returned on successful login or token refresh."""
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"
    expires_in:    int  # seconds until access_token expires

class RegisterResponse(BaseModel):
    message:      str = "Registration successful. Please check your email to confirm your account."
    user_id:      str
    email:        str
    requires_confirmation: bool = True

class LoginResponse(BaseModel):
    tokens:  TokenPair
    user:    "UserProfile"  # forward ref — defined below

class LogoutResponse(BaseModel):
    message: str = "Logged out successfully."
    

# Profile Schemas 
class UserProfile(BaseModel):
    """
    Public-facing user profile.
    Returned on login, GET /me, and embedded in LoginResponse.
    """
    id:               str
    email:            str
    display_name:     Optional[str]
    avatar_url:       Optional[str]
    preferred_pairs:  List[str]
    timezone:         str
    
    mentor_questions_asked: int = Field(default=0)
    signals_extracted: int = Field(default=0)
    strategies_generated: int = Field(default=0)
    backtests_run: int = Field(default=0)
    
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

class ProfileUpdateRequest(BaseModel):
    """Fields the user can self-update. All optional."""
    display_name:     Optional[str] = Field(None, min_length=2, max_length=80)
    avatar_url:       Optional[str] = Field(None, max_length=500)
    preferred_pairs:  Optional[List[str]] = None
    timezone:         Optional[str] = Field(None, max_length=60)

    model_config = {"json_schema_extra": {"example": {
        "display_name": "Alex Trader",
        "experience_level": "intermediate",
        "preferred_pairs": ["EUR/USD", "USD/JPY", "GBP/USD"],
        "timezone": "America/New_York",
    }}}

class ProfileUpdateResponse(BaseModel):
    message: str = "Profile updated successfully."
    profile: UserProfile

# Dashboard Schema

class UserDashboard(BaseModel):
    """
    Aggregated user statistics returned by GET /me/dashboard.
    Populated from the user_dashboard VIEW in Supabase.
    """
    id:               str
    display_name:     Optional[str]
    email:            str
    preferred_pairs:  List[str]

    # Live aggregates
    active_mentor_conversations: int
    active_quant_sessions:       int
    total_signals:               int
    saved_signals:               int
    total_strategies:            int
    validated_strategies:        int
    completed_backtests:         int

    # Best performance
    best_sharpe:      Optional[float]
    avg_return_pct:   Optional[float]

    # Timestamps
    last_mentor_activity:   Optional[datetime]
    last_quant_activity:    Optional[datetime]
    last_signal_extracted:  Optional[datetime]
    member_since:           datetime

# JWT Payload Schema 

class JWTPayload(BaseModel):
    """
    Decoded Supabase JWT payload.
    Supabase signs JWTs with the project's JWT secret — we verify locally.
    """
    sub:   str            # user UUID
    email: str
    role:  str            # 'authenticated' | 'anon' | 'service_role'
    exp:   int            # Unix timestamp
    iat:   int
    aud:   str = "authenticated"

    @property
    def user_id(self) -> str:
        return self.sub

# Rebuild model with forward ref 
LoginResponse.model_rebuild()
