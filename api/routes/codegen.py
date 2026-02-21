import logging
from fastapi import APIRouter, Depends
from models.mentor import CodeGenRequest, CodeGenResponse
from services.ai_service import generate_code
from services.auth_service import verify_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/codegen", tags=["Code Generation"])


@router.post("/translate", response_model=CodeGenResponse)
async def translate_strategy(
    body: CodeGenRequest,
    user: dict = Depends(verify_token),
):
    logger.info(f"Code generation requested by user: {user['user_id']}")
    result = await generate_code(
        strategy_description=body.strategy_description,
        user_id=user["user_id"],
    )
    return CodeGenResponse(**result)