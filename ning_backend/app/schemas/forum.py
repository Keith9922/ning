from __future__ import annotations

from pydantic import BaseModel, Field


class PostCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)


class PostUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, min_length=1)


class PostPublic(BaseModel):
    id: str
    title: str
    content: str
    author: str
    likes: int
    comments: int
    createdAt: str


class CommentCreate(BaseModel):
    content: str = Field(min_length=1)


class CommentPublic(BaseModel):
    id: str
    content: str
    author: str
    createdAt: str


