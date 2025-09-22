from __future__ import annotations

from pydantic import BaseModel, Field


class MistakeCreate(BaseModel):
    titleSlug: str = Field(min_length=1)
    title: str = Field(min_length=1)
    difficulty: str | None = Field(default=None)
    tags: list[str] = Field(default_factory=list)
    note: str | None = Field(default=None)


class MistakePublic(BaseModel):
    id: str
    titleSlug: str
    title: str
    difficulty: str | None
    tags: list[str]
    note: str | None
    createdAt: str


class StatsResponse(BaseModel):
    total: int
    byDifficulty: dict[str, int]
    byTag: dict[str, int]
    recentTrend: list[dict]


class Recommendation(BaseModel):
    titleSlug: str
    title: str
    reason: str


