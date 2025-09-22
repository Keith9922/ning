from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any, Iterable

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .core import runtime


# Lazy import redis to avoid hard dependency during initial scaffold
redis_client: Any | None = None


def get_cors_origins() -> list[str]:
    origins_env = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000")
    parts: Iterable[str] = (o.strip() for o in origins_env.split(","))
    return [o for o in parts if o]


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[override]
    global redis_client
    try:
        import redis.asyncio as redis  # type: ignore

        use_fake = os.getenv("USE_FAKE_REDIS", "0") == "1"
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        redis_client_local = None
        if use_fake or redis_url.startswith("memory://") or redis_url.startswith("redis+fake://"):
            try:
                from .core.memory_redis import AsyncMemoryRedis  # type: ignore
                redis_client_local = AsyncMemoryRedis()
            except Exception:
                redis_client_local = None
        if redis_client_local is None:
            redis_client_local = redis.from_url(redis_url, decode_responses=True)
            # Opportunistic ping; ignore failures to keep app booting
            try:
                await redis_client_local.ping()
            except Exception:
                pass
        globals()["redis_client"] = redis_client_local
        runtime.redis_client = redis_client_local
    except Exception:
        # redis package not installed or other error; proceed without hard fail
        globals()["redis_client"] = None
        runtime.redis_client = None
    yield
    try:
        if globals().get("redis_client") is not None:
            try:
                await globals()["redis_client"].close()
            except Exception:
                pass
        runtime.redis_client = None
    except Exception:
        pass


app = FastAPI(title="Ning Backend", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    status: dict[str, Any] = {"ok": True}
    # report redis status
    if redis_client is None:
        status["redis"] = {"connected": False, "message": "redis not initialized"}
        return status
    try:
        pong = await redis_client.ping()
        status["redis"] = {"connected": bool(pong)}
    except Exception as e:  # pragma: no cover - diagnostic only
        status["redis"] = {"connected": False, "error": str(e)}
    return status


# Routers v1 (placeholders; will be implemented in subsequent steps)
try:
    from .api.v1.endpoints import auth, forum, study, agent  # type: ignore

    app.include_router(auth.router, prefix="/auth", tags=["auth"])  # e.g., /auth/login
    app.include_router(forum.router, prefix="/forum", tags=["forum"])  # e.g., /forum/posts
    app.include_router(study.router, prefix="/study", tags=["study"])  # e.g., /study/mistakes
    app.include_router(agent.router, prefix="/agent", tags=["agent"])  # e.g., /agent/chat
except Exception:
    # During scaffold, missing modules should not break health
    pass


