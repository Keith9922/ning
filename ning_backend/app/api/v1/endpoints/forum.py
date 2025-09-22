from __future__ import annotations

import datetime as dt
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException

import app.core.runtime as runtime
from ....core.security import require_token
from ....schemas.auth import UserPublic
from ....schemas.forum import CommentCreate, CommentPublic, PostCreate, PostPublic, PostUpdate


router = APIRouter()


def _now_iso() -> str:
    return dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).isoformat()


async def _get_user_by_token(token: str) -> UserPublic:
    if runtime.redis_client is None:
        raise HTTPException(status_code=500, detail="Redis not initialized")
    uid = await runtime.redis_client.get(f"session:{token}")
    if not uid:
        raise HTTPException(status_code=401, detail="Unauthorized")
    user = await runtime.redis_client.hgetall(f"user:{uid}")
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return UserPublic(id=str(user["id"]), username=user["username"])


@router.get("/posts")
async def list_posts(offset: int = 0, limit: int = 20) -> dict[str, List[PostPublic]]:
    if runtime.redis_client is None:
        raise HTTPException(status_code=500, detail="Redis not initialized")
    # We store post ids in a list-like set ordered by time using incremental ids
    max_id = int((await runtime.redis_client.get("forum:post_seq")) or 0)
    items: List[PostPublic] = []
    # iterate from latest to oldest
    count = 0
    idx = 0
    i = max_id
    while i > 0 and count < limit:
        if idx >= offset:
            data = await runtime.redis_client.hgetall(f"forum:post:{i}")
            if data and data.get("deleted") != "1":
                likes = await runtime.redis_client.scard(f"forum:post:{i}:likes")
                comments = int((await runtime.redis_client.get(f"forum:post:{i}:comments_cnt")) or 0)
                items.append(
                    PostPublic(
                        id=str(i),
                        title=data.get("title", ""),
                        content=data.get("content", ""),
                        author=data.get("author", "匿名宁友"),
                        likes=likes,
                        comments=comments,
                        createdAt=data.get("created_at", _now_iso()),
                    )
                )
                count += 1
        idx += 1
        i -= 1
    return {"items": items}


@router.post("/posts", response_model=PostPublic)
async def create_post(payload: PostCreate, token: str = Depends(require_token)) -> PostPublic:
    if runtime.redis_client is None:
        raise HTTPException(status_code=500, detail="Redis not initialized")
    user = await _get_user_by_token(token)
    pid = await runtime.redis_client.incr("forum:post_seq")
    created_at = _now_iso()
    await runtime.redis_client.hset(
        f"forum:post:{pid}",
        mapping={
            "id": str(pid),
            "title": payload.title,
            "content": payload.content,
            "author": user.username,
            "author_id": user.id,
            "created_at": created_at,
            "deleted": "0",
        },
    )
    return PostPublic(id=str(pid), title=payload.title, content=payload.content, author=user.username, likes=0, comments=0, createdAt=created_at)


@router.get("/posts/{post_id}", response_model=PostPublic)
async def get_post(post_id: str) -> PostPublic:
    if runtime.redis_client is None:
        raise HTTPException(status_code=500, detail="Redis not initialized")
    data = await runtime.redis_client.hgetall(f"forum:post:{post_id}")
    if not data or data.get("deleted") == "1":
        raise HTTPException(status_code=404, detail="Post not found")
    likes = await runtime.redis_client.scard(f"forum:post:{post_id}:likes")
    comments = int((await runtime.redis_client.get(f"forum:post:{post_id}:comments_cnt")) or 0)
    return PostPublic(
        id=str(post_id), title=data.get("title", ""), content=data.get("content", ""), author=data.get("author", "匿名宁友"), likes=likes, comments=comments, createdAt=data.get("created_at", _now_iso())
    )


@router.put("/posts/{post_id}", response_model=PostPublic)
async def update_post(post_id: str, payload: PostUpdate, token: str = Depends(require_token)) -> PostPublic:
    if runtime.redis_client is None:
        raise HTTPException(status_code=500, detail="Redis not initialized")
    data = await runtime.redis_client.hgetall(f"forum:post:{post_id}")
    if not data or data.get("deleted") == "1":
        raise HTTPException(status_code=404, detail="Post not found")
    user = await _get_user_by_token(token)
    if data.get("author_id") != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    mapping: dict[str, Any] = {}
    if payload.title is not None:
        mapping["title"] = payload.title
    if payload.content is not None:
        mapping["content"] = payload.content
    if mapping:
        await runtime.redis_client.hset(f"forum:post:{post_id}", mapping=mapping)
    likes = await runtime.redis_client.scard(f"forum:post:{post_id}:likes")
    comments = int((await runtime.redis_client.get(f"forum:post:{post_id}:comments_cnt")) or 0)
    final = await runtime.redis_client.hgetall(f"forum:post:{post_id}")
    return PostPublic(
        id=str(post_id), title=final.get("title", ""), content=final.get("content", ""), author=final.get("author", "匿名宁友"), likes=likes, comments=comments, createdAt=final.get("created_at", _now_iso())
    )


@router.delete("/posts/{post_id}")
async def delete_post(post_id: str, token: str = Depends(require_token)) -> dict[str, bool]:
    if runtime.redis_client is None:
        raise HTTPException(status_code=500, detail="Redis not initialized")
    data = await runtime.redis_client.hgetall(f"forum:post:{post_id}")
    if not data or data.get("deleted") == "1":
        raise HTTPException(status_code=404, detail="Post not found")
    user = await _get_user_by_token(token)
    if data.get("author_id") != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    await runtime.redis_client.hset(f"forum:post:{post_id}", mapping={"deleted": "1"})
    return {"ok": True}


@router.post("/posts/{post_id}/like")
async def toggle_like(post_id: str, token: str = Depends(require_token)) -> dict[str, Any]:
    if runtime.redis_client is None:
        raise HTTPException(status_code=500, detail="Redis not initialized")
    user = await _get_user_by_token(token)
    key = f"forum:post:{post_id}:likes"
    liked = await runtime.redis_client.sismember(key, user.id)
    if liked:
        await runtime.redis_client.srem(key, user.id)
        liked = False
    else:
        await runtime.redis_client.sadd(key, user.id)
        liked = True
    likes = await runtime.redis_client.scard(key)
    return {"liked": liked, "likes": likes}


@router.get("/posts/{post_id}/comments")
async def list_comments(post_id: str) -> dict[str, list[CommentPublic]]:
    if runtime.redis_client is None:
        raise HTTPException(status_code=500, detail="Redis not initialized")
    cnt = int((await runtime.redis_client.get(f"forum:post:{post_id}:comments_cnt")) or 0)
    items: list[CommentPublic] = []
    for i in range(1, cnt + 1):
        data = await runtime.redis_client.hgetall(f"forum:comment:{post_id}:{i}")
        if data and data.get("deleted") != "1":
            items.append(CommentPublic(id=str(i), content=data.get("content", ""), author=data.get("author", "匿名宁友"), createdAt=data.get("created_at", _now_iso())))
    return {"items": items}


@router.post("/posts/{post_id}/comment", response_model=CommentPublic)
async def create_comment(post_id: str, payload: CommentCreate, token: str = Depends(require_token)) -> CommentPublic:
    if runtime.redis_client is None:
        raise HTTPException(status_code=500, detail="Redis not initialized")
    user = await _get_user_by_token(token)
    data = await runtime.redis_client.hgetall(f"forum:post:{post_id}")
    if not data or data.get("deleted") == "1":
        raise HTTPException(status_code=404, detail="Post not found")
    idx = (int((await runtime.redis_client.get(f"forum:post:{post_id}:comments_cnt")) or 0) + 1)
    created_at = _now_iso()
    await runtime.redis_client.hset(
        f"forum:comment:{post_id}:{idx}",
        mapping={
            "id": str(idx),
            "post_id": str(post_id),
            "author": user.username,
            "author_id": user.id,
            "content": payload.content,
            "created_at": created_at,
            "deleted": "0",
        },
    )
    await runtime.redis_client.set(f"forum:post:{post_id}:comments_cnt", idx)
    return CommentPublic(id=str(idx), content=payload.content, author=user.username, createdAt=created_at)


@router.delete("/comments/{comment_id}")
async def delete_comment(comment_id: str, post_id: str, token: str = Depends(require_token)) -> dict[str, bool]:
    if runtime.redis_client is None:
        raise HTTPException(status_code=500, detail="Redis not initialized")
    user = await _get_user_by_token(token)
    data = await runtime.redis_client.hgetall(f"forum:comment:{post_id}:{comment_id}")
    if not data or data.get("deleted") == "1":
        raise HTTPException(status_code=404, detail="Comment not found")
    if data.get("author_id") != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    await runtime.redis_client.hset(f"forum:comment:{post_id}:{comment_id}", mapping={"deleted": "1"})
    return {"ok": True}


