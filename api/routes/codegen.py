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


from fastapi import APIRouter, Depends, HTTPException, status
from models.codegen import (
    GenerateCodeRequest,
    GenerateCodeResponse,
    GeneratedCodeSummaryResponse,
    GeneratedCodeDetailResponse,
    CodeConversationHistoryResponse,
    ImproveStrategyRequest,
    ImproveStrategyResponse
)
from core.dependencies import get_codegen_service
from api.middleware.auth_middleware import get_current_user
from models.user import JWTPayload
from services.ai_errors import AIServiceUnavailableError

router = APIRouter(prefix="/codegen", tags=["codegen"])

def _assert_user_access(requested_user_id: str, user: JWTPayload) -> None:
    if requested_user_id != user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own resources.",
        )


@router.post("/generate", response_model=GenerateCodeResponse)
async def generate_code(
    request: GenerateCodeRequest,
    user: JWTPayload = Depends(get_current_user),
    service = Depends(get_codegen_service),
):
    try:
        if request.user_id and request.user_id != user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only generate code for your own account.",
            )
        result = await service.generate_code(
            user_id=user.user_id,
            strategy_description=request.strategy_description,
            conversation_id=request.conversation_id,
            previous_code=request.previous_code,
            error_message=request.error_message
        )
        return result
    except AIServiceUnavailableError:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        # raise HTTPException(
        #     status_code=503,
        #     detail="Our AI service is temporarily unavailable. Please try again in a moment."
        # )


@router.get("/codes/{user_id}", response_model=list[GeneratedCodeSummaryResponse])
async def list_generated_codes(
    user_id: str,
    limit: int = 20,
    user: JWTPayload = Depends(get_current_user),
    service = Depends(get_codegen_service),
):
    try:
        _assert_user_access(user_id, user)
        codes = await service.list_generated_codes(user_id, limit)
        return codes
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/codes/{user_id}/{code_id}", response_model=GeneratedCodeDetailResponse)
async def get_generated_code(
    code_id: str,
    user_id: str,
    user: JWTPayload = Depends(get_current_user),
    service = Depends(get_codegen_service),
):
    try:
        _assert_user_access(user_id, user)
        code = await service.get_generated_code(code_id, user_id)
        if code is None:
            raise HTTPException(status_code=404, detail="Code not found")
        return code
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations/{user_id}/{conversation_id}", response_model=CodeConversationHistoryResponse)
async def get_conversation(
    conversation_id: str,
    user_id: str,
    user: JWTPayload = Depends(get_current_user),
    service = Depends(get_codegen_service),
):
    try:
        _assert_user_access(user_id, user)
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
    
@router.post("/improve", response_model=ImproveStrategyResponse)
async def improve_strategy(
    request: ImproveStrategyRequest,
    user: JWTPayload = Depends(get_current_user),
    service = Depends(get_codegen_service),
):
    try:
        if request.user_id and request.user_id != user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only improve code for your own account.",
            )
        result = await service.generate_improvement(
            user_id=user.user_id,
            original_code=request.original_code,
            backtest_results=request.backtest_results,
            mentor_analysis=request.mentor_analysis,
            additional_requirements=request.additional_requirements,
            conversation_id=request.conversation_id
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.delete("/conversations/{user_id}/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    user_id: str,
    user: JWTPayload = Depends(get_current_user),
    service = Depends(get_codegen_service),
):
    try:
        _assert_user_access(user_id, user)
        deleted = service.delete_conversation(conversation_id, user_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {"message": "Conversation deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
