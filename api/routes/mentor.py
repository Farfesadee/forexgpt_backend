import logging
from fastapi import APIRouter, Depends
from models.mentor import MentorRequest, MentorResponse
from services.ai_service import ask_mentor
from services.auth_service import verify_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/mentor", tags=["Mentor"])


@router.post("/ask", response_model=MentorResponse)
async def ask_mentor_endpoint(
    body: MentorRequest,
    user: dict = Depends(verify_token),
):
    logger.info(f"Mentor question from user: {user['user_id']}")
    result = await ask_mentor(
        question=body.question,
        context=body.context,
        user_id=user["user_id"],
    )
    return MentorResponse(**result)