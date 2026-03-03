from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Mistral (for mentor and codegen services)
    MISTRAL_API_KEY: str
    
    # HuggingFace (for signal service - fine-tuned model)
    HUGGING_FACE_TOKEN: str
    
    # Supabase
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str
    

    
    # Model IDs
    MISTRAL_MODEL_ID: str = "mistral-small-latest"
    SIGNAL_MODEL_ID: str = "forexgpt/mistral-7b-forex-signals"

    class Config:
        env_file = ".env"

settings = Settings()