from typing import Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Mistral (for mentor and codegen services)
    MISTRAL_API_KEY: Optional[str] = None
    
    # HuggingFace (for signal service - fine-tuned model)
    HUGGING_FACE_TOKEN: str = Field(validation_alias=AliasChoices("HUGGING_FACE_TOKEN", "HF_API_KEY"))
    
    # Supabase
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_JWT_SECRET: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("SUPABASE_JWT_SECRET", "JWT_SECRET", "APP_SECRET_KEY"),
    )
    
    SITE_URL: str = "http://localhost:3000"
    # Model IDs
    MISTRAL_MODEL_ID: str = "mistral-small-latest"
    SIGNAL_MODEL_ID: str = "forexgpt/forexgpt-mistral-7b-forex-signals-v1.0"

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
