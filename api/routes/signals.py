import logging
from fastapi import APIRouter, Depends
from models.signal import SignalExtractRequest, SignalExtractResponse, SignalResult
from services.signal_service import extract_signal
from services.auth_service import verify_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/signals", tags=["Signals"])


@router.post("/extract", response_model=SignalExtractResponse)
async def extract_signal_endpoint(
    body: SignalExtractRequest,
    user: dict = Depends(verify_token),
):
    logger.info(f"Signal extraction requested by user: {user['user_id']}")
    result = await extract_signal(
        transcript=body.transcript,
        user_id=user["user_id"],
    )
    return SignalExtractResponse(
        signal=SignalResult(**{k: result[k] for k in SignalResult.model_fields}),
        signal_id=result.get("signal_id"),
    )