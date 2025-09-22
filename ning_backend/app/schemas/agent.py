from __future__ import annotations

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    role: str | None = Field(default=None)
    focus: str | None = Field(default=None)


class SessionPublic(BaseModel):
    session_id: str


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(min_length=1)


class ChatResponse(BaseModel):
    reply: str
    tips: str | None = None
    score: int | None = None


class SessionDetail(BaseModel):
    session_id: str
    messages: list[dict]


