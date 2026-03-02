# import logging
# from fastapi import APIRouter, Depends
# from models.mentor import CodeGenRequest, CodeGenResponse
# from services.ai_service import generate_code
# from services.auth_service import verify_token

# logger = logging.getLogger(__name__)
# router = APIRouter(prefix="/codegen", tags=["Code Generation"])


# @router.post("/translate", response_model=CodeGenResponse)
# async def translate_strategy(
#     body: CodeGenRequest,
#     user: dict = Depends(verify_token),
# ):
#     logger.info(f"Code generation requested by user: {user['user_id']}")
#     result = await generate_code(
#         strategy_description=body.strategy_description,
#         user_id=user["user_id"],
#     )
#     return CodeGenResponse(**result)

from fastapi import APIRouter, HTTPException
from models.codegen import (
    GenerateCodeRequest,
    GenerateCodeResponse,
    GeneratedCodeSummaryResponse,
    GeneratedCodeDetailResponse,
    CodeConversationHistoryResponse
)
from core.dependencies import get_codegen_service

router = APIRouter(prefix="/codegen", tags=["codegen"])
service = get_codegen_service()


@router.post("/generate", response_model=GenerateCodeResponse)
async def generate_code(request: GenerateCodeRequest):
    try:
        result = await service.generate_code(
            user_id=request.user_id,
            strategy_description=request.strategy_description,
            conversation_id=request.conversation_id,
            previous_code=request.previous_code,
            error_message=request.error_message
        )
        return result
    except Exception as e:
        # raise HTTPException(status_code=500, detail=str(e))
        raise HTTPException(
            status_code=503,
            detail="Our AI service is temporarily unavailable. Please try again in a moment."
        )


@router.get("/codes/{user_id}", response_model=list[GeneratedCodeSummaryResponse])
async def list_generated_codes(user_id: str, limit: int = 20):
    try:
        codes = await service.list_generated_codes(user_id, limit)
        return codes
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/codes/{user_id}/{code_id}", response_model=GeneratedCodeDetailResponse)
async def get_generated_code(code_id: str, user_id: str):
    try:
        code = await service.get_generated_code(code_id, user_id)
        if code is None:
            raise HTTPException(status_code=404, detail="Code not found")
        return code
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations/{user_id}/{conversation_id}", response_model=CodeConversationHistoryResponse)
async def get_conversation(conversation_id: str, user_id: str):
    try:
        history = await service.get_conversation_history(conversation_id, user_id)
        if history is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {
            "conversation_id": conversation_id,
            "history": history
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))