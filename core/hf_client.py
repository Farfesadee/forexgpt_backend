from functools import lru_cache

from huggingface_hub import AsyncInferenceClient
from mistralai import Mistral

from core.config import settings

def _is_configured(value: str | None) -> bool:
    return bool(value and value.strip() and not value.lower().startswith("your-"))


def _missing_config_error(var_name: str, purpose: str) -> RuntimeError:
    return RuntimeError(f"{var_name} is not configured. Set it in .env before using {purpose}.")


@lru_cache
def get_mistral_client() -> Mistral:
    if not _is_configured(settings.MISTRAL_API_KEY):
        raise _missing_config_error(
            "MISTRAL_API_KEY",
            "mentor, code generation, or signal extraction endpoints",
        )
    return Mistral(api_key=settings.MISTRAL_API_KEY)


@lru_cache
def get_hf_client() -> AsyncInferenceClient:
    if not _is_configured(settings.HUGGING_FACE_TOKEN):
        raise _missing_config_error(
            "HUGGING_FACE_TOKEN",
            "Hugging Face-backed signal extraction endpoints",
        )
    return AsyncInferenceClient(token=settings.HUGGING_FACE_TOKEN, provider="hf-inference")
