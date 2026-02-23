from pydantic import BaseModel
from typing import Literal


class QuantAskRequest(BaseModel):
    question: str
    topic_id: str | None = None
    conversation_history: list[dict] | None = None
    user_id: str | None = None


class QuantAskResponse(BaseModel):
    answer: str
    topic_id: str | None = None
    related_topics: list[str] = []
    conversation_id: str | None = None


class QuantTopic(BaseModel):
    id: str
    title: str
    difficulty: Literal["beginner", "intermediate", "advanced"]
    category: str
    description: str


class QuantSearchResponse(BaseModel):
    results: list[QuantTopic]
    total: int


class QuantInteractiveRequest(BaseModel):
    topic_id: str
    message: str
    history: list[dict] | None = None
    user_id: str | None = None