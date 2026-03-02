from core.database import supabase
from core.hf_client import mistral_client, hf_client
from core.config import settings
from services.mentor_service import MentorService
from services.codegen_service import CodeGenService
from services.signal_service import SignalService

def get_mentor_service() -> MentorService:
    return MentorService(
        mistral_client, 
        supabase, 
        model_id=settings.MISTRAL_MODEL_ID
    )

def get_codegen_service() -> CodeGenService:
    return CodeGenService(
        mistral_client, 
        supabase, 
        model_id=settings.MISTRAL_MODEL_ID
    )

def get_signal_service() -> SignalService:
    return SignalService(
        hf_client,       # uses HuggingFace, not Mistral
        supabase, 
        model_id=settings.SIGNAL_MODEL_ID
    )