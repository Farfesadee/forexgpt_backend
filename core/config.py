from pydantic_settings import BaseSettings
from pydantic import Field, AliasChoices

class Settings(BaseSettings):
    # Mistral (for mentor and codegen services)
    MISTRAL_API_KEY: str
    
    # HuggingFace (for signal service - fine-tuned model)
    HUGGING_FACE_TOKEN: str = Field(validation_alias=AliasChoices("HUGGING_FACE_TOKEN", "HF_API_KEY"))
    
    # Supabase
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_JWT_SECRET: str = Field(validation_alias=AliasChoices("SUPABASE_JWT_SECRET", "JWT_SECRET"))
    
    SITE_URL: str = "http://localhost:3000"
    # Model IDs
    MISTRAL_MODEL_ID: str = "mistral-small-latest"
    SIGNAL_MODEL_ID: str = "forexgpt/forexgpt-mistral-7b-forex-signals-v1.0"

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
