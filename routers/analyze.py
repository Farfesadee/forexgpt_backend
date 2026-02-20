from fastapi import APIRouter, Depends
from services.ai_service import generate_signal
from services.auth_service import verify_token
from models.request_models import SignalRequest
from models.response_models import SignalResponse

router = APIRouter()

@router.post("/extract-signal", response_model=SignalResponse)
def extract_signal(
    request: SignalRequest,
    user=Depends(verify_token)
):
    return generate_signal(request)