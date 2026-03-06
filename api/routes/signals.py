# import logging
# from fastapi import APIRouter, Depends
# from models.signal import SignalExtractRequest, SignalExtractResponse, SignalResult
# from services.signal_service import extract_signal
# from services.auth_service import verify_token

# logger = logging.getLogger(__name__)
# router = APIRouter(prefix="/signals", tags=["Signals"])


# @router.post("/extract", response_model=SignalExtractResponse)
# async def extract_signal_endpoint(
#     body: SignalExtractRequest,
#     user: dict = Depends(verify_token),
# ):
#     logger.info(f"Signal extraction requested by user: {user['user_id']}")
#     result = await extract_signal(
#         transcript=body.transcript,
#         user_id=user["user_id"],
#     )
#     return SignalExtractResponse(
#         signal=SignalResult(**{k: result[k] for k in SignalResult.model_fields}),
#         signal_id=result.get("signal_id"),
#     )

from fastapi import APIRouter, Depends, HTTPException, status
from models.signal import (
    ExtractSignalRequest,
    BatchExtractRequest,
    SignalResponse,
    BatchSignalResponse,
    SavedSignalResponse,
    SignalStatisticsResponse,
    DeleteSignalResponse
)
from core.dependencies import get_signal_service
from api.middleware.auth_middleware import get_current_user
from models.user import JWTPayload
from typing import Optional

router = APIRouter(prefix="/signals", tags=["signals"])
service = get_signal_service()

def _assert_user_access(requested_user_id: str, user: JWTPayload) -> None:
    if requested_user_id != user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own resources.",
        )


@router.post("/extract", response_model=SignalResponse)
async def extract_signal(
    request: ExtractSignalRequest,
    user: JWTPayload = Depends(get_current_user),
):
    try:
        if request.user_id and request.user_id != user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only extract signals for your own account.",
            )
        result = await service.extract_signal(
            user_id=user.user_id,
            transcript=request.transcript,
            company_name=request.company_name,
            save_to_db=request.save_to_db
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        # raise HTTPException(
        #     status_code=503,
        #     detail="Our AI service is temporarily unavailable. Please try again in a moment."
        # )


@router.post("/batch", response_model=BatchSignalResponse)
async def batch_extract(
    request: BatchExtractRequest,
    user: JWTPayload = Depends(get_current_user),
):
    try:
        if request.user_id and request.user_id != user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only extract signals for your own account.",
            )
        signals = await service.batch_extract_signals(
            user_id=user.user_id,
            transcripts=request.transcripts,
            save_to_db=request.save_to_db
        )
        return {
            "signals": signals,
            "total": len(signals),
            "signals_found": sum(1 for s in signals if s.get("signal"))
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/user/{user_id}", response_model=list[SavedSignalResponse])
async def get_user_signals(
    user_id: str,
    limit: int = 50,
    currency_pair: Optional[str] = None,
    direction: Optional[str] = None,
    user: JWTPayload = Depends(get_current_user),
):
    try:
        _assert_user_access(user_id, user)
        signals = await service.get_user_signals(
            user_id=user_id,
            limit=limit,
            currency_pair=currency_pair,
            direction=direction
        )
        return signals
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/user/{user_id}/{signal_id}", response_model=SavedSignalResponse)
async def get_signal(
    signal_id: str,
    user_id: str,
    user: JWTPayload = Depends(get_current_user),
):
    try:
        _assert_user_access(user_id, user)
        signal = await service.get_signal_by_id(signal_id, user_id)
        if signal is None:
            raise HTTPException(status_code=404, detail="Signal not found")
        return signal
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics/{user_id}", response_model=SignalStatisticsResponse)
async def get_statistics(
    user_id: str,
    user: JWTPayload = Depends(get_current_user),
):
    try:
        _assert_user_access(user_id, user)
        stats = await service.get_signal_statistics(user_id)
        return stats
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{user_id}/{signal_id}", response_model=DeleteSignalResponse)
async def delete_signal(
    signal_id: str,
    user_id: str,
    user: JWTPayload = Depends(get_current_user),
):
    try:
        _assert_user_access(user_id, user)
        deleted = await service.delete_signal(signal_id, user_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Signal not found")
        return {"message": "Signal deleted successfully", "signal_id": signal_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
