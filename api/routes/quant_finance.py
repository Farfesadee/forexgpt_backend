import logging
from fastapi import APIRouter, Depends, Query
from models.quant_finance import (
    QuantAskRequest, QuantAskResponse,
    QuantSearchResponse, QuantTopic,
    QuantInteractiveRequest,
)
from services.quant_finance_service import (
    ask_quant, search_topics, get_topic,
    get_related_topics, QUANT_TOPICS,
)
from services.auth_service import verify_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/quant-finance", tags=["Quantitative Finance"])


@router.post("/ask", response_model=QuantAskResponse)
async def ask_quant_endpoint(
    body: QuantAskRequest,
    user: dict = Depends(verify_token),
):
    """Ask any quantitative finance question."""
    logger.info(f"Quant finance question from user: {user['user_id']}")
    result = await ask_quant(
        question=body.question,
        topic_id=body.topic_id,
        conversation_history=body.conversation_history,
        user_id=user["user_id"],
    )
    return QuantAskResponse(**result)


@router.get("/search", response_model=QuantSearchResponse)
async def search_quant_topics(
    query: str = Query(..., min_length=1),
    user: dict = Depends(verify_token),
):
    """Search across all 50 quant finance topics."""
    results = search_topics(query)
    return QuantSearchResponse(
        results=[QuantTopic(**t) for t in results],
        total=len(results),
    )


@router.get("/all", response_model=QuantSearchResponse)
async def get_all_topics(user: dict = Depends(verify_token)):
    """Returns all 50 quantitative finance topics."""
    return QuantSearchResponse(
        results=[QuantTopic(**t) for t in QUANT_TOPICS],
        total=len(QUANT_TOPICS),
    )


@router.get("/topics/{topic_id}")
async def get_topic_detail(
    topic_id: str,
    user: dict = Depends(verify_token),
):
    """Get full details for a specific topic."""
    topic = get_topic(topic_id)
    if not topic:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Topic not found.")
    return QuantTopic(**topic)


@router.get("/related/{topic_id}")
async def get_related(
    topic_id: str,
    user: dict = Depends(verify_token),
):
    """Get related topics in the same category."""
    related = get_related_topics(topic_id)
    return {"related": [QuantTopic(**t) for t in related]}


@router.post("/interactive")
async def interactive_qa(
    body: QuantInteractiveRequest,
    user: dict = Depends(verify_token),
):
    """Interactive Q&A within a specific topic context."""
    logger.info(f"Interactive quant Q&A from user: {user['user_id']}")
    result = await ask_quant(
        question=body.message,
        topic_id=body.topic_id,
        conversation_history=body.history,
        user_id=user["user_id"],
    )
    return QuantAskResponse(**result)