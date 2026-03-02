from mistralai import Mistral
from huggingface_hub import AsyncInferenceClient
from core.config import settings

# Mistral client - for mentor and codegen
def get_mistral_client() -> Mistral:
    return Mistral(api_key=settings.MISTRAL_API_KEY)

# HuggingFace client - for fine-tuned signal model
def get_hf_client() -> AsyncInferenceClient:
    return AsyncInferenceClient(token=settings.HUGGING_FACE_TOKEN)

mistral_client = get_mistral_client()
hf_client = get_hf_client()