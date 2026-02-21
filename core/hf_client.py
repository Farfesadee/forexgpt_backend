import logging
import httpx
from config import get_settings

logger = logging.getLogger(__name__)


class HuggingFaceClient:
    def __init__(self):
        settings = get_settings()
        self.hf_api_key = settings.hf_api_key
        self.signal_endpoint = settings.hf_signal_endpoint
        self.base_endpoint = settings.hf_base_endpoint
        self.headers = {
            "Authorization": f"Bearer {self.hf_api_key}",
            "Content-Type": "application/json",
        }

    async def call_signal_model(self, prompt: str) -> str:
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": 512,
                "temperature": 0.1,
                "return_full_text": False,
            },
        }
        logger.info("Calling fine-tuned signal model on Hugging Face.")
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                self.signal_endpoint, headers=self.headers, json=payload
            )
            response.raise_for_status()
            result = response.json()
            return result[0]["generated_text"]

    async def call_base_model(self, system_prompt: str, user_message: str) -> str:
        prompt = f"<s>[INST] {system_prompt}\n\n{user_message} [/INST]"
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": 1024,
                "temperature": 0.7,
                "return_full_text": False,
            },
        }
        logger.info("Calling base Mistral model on Hugging Face.")
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                self.base_endpoint, headers=self.headers, json=payload
            )
            response.raise_for_status()
            result = response.json()
            return result[0]["generated_text"]


hf_client = HuggingFaceClient()