from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

import app.core.runtime as runtime
from ....core.security import require_token
from ....schemas.study import MistakeCreate, MistakePublic, Recommendation, StatsResponse


router = APIRouter()


def _now_iso() -> str:
    return dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).isoformat()


async def _ensure_redis():
    if runtime.redis_client is None:
        raise HTTPException(status_code=500, detail="Redis not initialized")


@router.post("/mistakes", response_model=MistakePublic)
async def add_mistake(payload: MistakeCreate, token: str = Depends(require_token)) -> MistakePublic:
    await _ensure_redis()
    # derive user id from session
    uid = await runtime.redis_client.get(f"session:{token}")
    if not uid:
        raise HTTPException(status_code=401, detail="Unauthorized")
    # per-user auto id
    mid = await runtime.redis_client.incr(f"study:{uid}:mistakes_seq")
    created_at = _now_iso()
    await runtime.redis_client.hset(
        f"study:{uid}:mistake:{mid}",
        mapping={
            "id": str(mid),
            "titleSlug": payload.titleSlug,
            "title": payload.title,
            "difficulty": payload.difficulty or "",
            "tags": ",".join(payload.tags or []),
            "note": payload.note or "",
            "created_at": created_at,
        },
    )
    # update counters
    await runtime.redis_client.sadd(f"study:{uid}:mistakes", mid)
    if payload.difficulty:
        await runtime.redis_client.incr(f"study:{uid}:difficulty:{payload.difficulty}")
    for t in payload.tags or []:
        await runtime.redis_client.incr(f"study:{uid}:tag:{t}")
    # trend (per day count)
    day = created_at[:10]
    await runtime.redis_client.incr(f"study:{uid}:trend:{day}")
    return MistakePublic(id=str(mid), titleSlug=payload.titleSlug, title=payload.title, difficulty=payload.difficulty, tags=payload.tags or [], note=payload.note, createdAt=created_at)


@router.get("/mistakes")
async def list_mistakes(token: str = Depends(require_token)) -> dict[str, list[MistakePublic]]:
    await _ensure_redis()
    uid = await runtime.redis_client.get(f"session:{token}")
    if not uid:
        raise HTTPException(status_code=401, detail="Unauthorized")
    ids = sorted([int(x) for x in await runtime.redis_client.smembers(f"study:{uid}:mistakes")])
    items: list[MistakePublic] = []
    for mid in ids:
        data = await runtime.redis_client.hgetall(f"study:{uid}:mistake:{mid}")
        if not data:
            continue
        items.append(
            MistakePublic(
                id=str(mid),
                titleSlug=data.get("titleSlug", ""),
                title=data.get("title", ""),
                difficulty=(data.get("difficulty") or None) or None,
                tags=[t for t in (data.get("tags", "").split(",") if data.get("tags") else []) if t],
                note=(data.get("note") or None) or None,
                createdAt=data.get("created_at", _now_iso()),
            )
        )
    return {"items": items}


@router.delete("/mistakes/{mid}")
async def delete_mistake(mid: str, token: str = Depends(require_token)) -> dict[str, bool]:
    await _ensure_redis()
    uid = await runtime.redis_client.get(f"session:{token}")
    if not uid:
        raise HTTPException(status_code=401, detail="Unauthorized")
    data = await runtime.redis_client.hgetall(f"study:{uid}:mistake:{mid}")
    if data:
        await runtime.redis_client.delete(f"study:{uid}:mistake:{mid}")
        await runtime.redis_client.srem(f"study:{uid}:mistakes", mid)
        # best-effort decrement of counters skipped (to keep logic simple)
    return {"ok": True}


@router.get("/stats", response_model=StatsResponse)
async def stats(days: int = 7, token: str = Depends(require_token)) -> StatsResponse:  # type: ignore[override]
    await _ensure_redis()
    uid = await runtime.redis_client.get(f"session:{token}")
    if not uid:
        raise HTTPException(status_code=401, detail="Unauthorized")
    total = len(await runtime.redis_client.smembers(f"study:{uid}:mistakes"))
    # difficulties
    byDifficulty: dict[str, int] = {}
    for d in ["Easy", "Medium", "Hard"]:
        v = await runtime.redis_client.get(f"study:{uid}:difficulty:{d}")
        byDifficulty[d] = int(v) if v else 0
    # tags: sample top 20 by scanning known keys is omitted; compute from items
    byTag: dict[str, int] = {}
    ids = await runtime.redis_client.smembers(f"study:{uid}:mistakes")
    for mid in ids:
        data = await runtime.redis_client.hgetall(f"study:{uid}:mistake:{mid}")
        for t in [t for t in (data.get("tags", "").split(",") if data.get("tags") else []) if t]:
            byTag[t] = byTag.get(t, 0) + 1
    # trend (last N days)
    today = dt.datetime.utcnow().date()
    recentTrend: list[dict] = []
    for i in range(days):
        day = (today - dt.timedelta(days=i)).isoformat()
        v = await runtime.redis_client.get(f"study:{uid}:trend:{day}")
        recentTrend.append({"date": day, "count": int(v) if v else 0})
    recentTrend.reverse()
    return StatsResponse(total=total, byDifficulty=byDifficulty, byTag=byTag, recentTrend=recentTrend)


@router.get("/recommendations")
async def recommendations(limit: int = 10, token: str = Depends(require_token)) -> dict[str, list[Recommendation]]:
    await _ensure_redis()
    uid = await runtime.redis_client.get(f"session:{token}")
    if not uid:
        raise HTTPException(status_code=401, detail="Unauthorized")
    # naive heuristic: take user tags, suggest pseudo problems by tags
    ids = await runtime.redis_client.smembers(f"study:{uid}:mistakes")
    tag_count: dict[str, int] = {}
    for mid in ids:
        data = await runtime.redis_client.hgetall(f"study:{uid}:mistake:{mid}")
        for t in [t for t in (data.get("tags", "").split(",") if data.get("tags") else []) if t]:
            tag_count[t] = tag_count.get(t, 0) + 1
    ranked = sorted(tag_count.items(), key=lambda kv: (-kv[1], kv[0]))
    recs: list[Recommendation] = []
    for tag, _ in ranked[: max(1, limit // 2)]:
        # fabricate a few sample recommendations per tag
        recs.append(Recommendation(titleSlug=f"{tag}-practice-1", title=f"Practice {tag} I", reason=f"Based on frequent tag: {tag}"))
        if len(recs) >= limit:
            break
    return {"items": recs[:limit]}


