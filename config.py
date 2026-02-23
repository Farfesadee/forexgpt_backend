import logging
from pydantic_settings import BaseSettings
from functools import lru_cache


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


class Settings(BaseSettings):
    
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str

    # Hugging Face — from AI engineers
    hf_api_key: str
    hf_signal_endpoint: str
    hf_base_endpoint: str

    # App
    app_env: str = "development"
    app_secret_key: str

    # Quant Finance Module
    quant_adapter_id: str = "user/mistral-quant-finance"
    quant_adapter_available: bool = False
    quant_quality_mode: str = "prompt_engineering"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()