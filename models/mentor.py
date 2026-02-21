from pydantic import BaseModel


class MentorRequest(BaseModel):
    question: str
    context: str | None = None
    user_id: str | None = None


class MentorResponse(BaseModel):
    answer: str
    conversation_id: str | None = None


class CodeGenRequest(BaseModel):
    strategy_description: str
    user_id: str | None = None


class CodeGenResponse(BaseModel):
    code: str
    language: str = "python"