# Ning Backend (FastAPI + Redis)

Ning Platform backend providing: authentication, forum, study assistant, and interview agent.

## Quick Start

1. Requirements
   - Python 3.10+
   - FastAPI, Uvicorn, redis-py (async)
   - Redis server (local or remote)

2. Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install fastapi uvicorn[standard] redis passlib[bcrypt] pydantic-settings fakeredis
```

3. Run

```bash
export REDIS_URL="redis://localhost:6379/0"
export CORS_ALLOW_ORIGINS="http://localhost:3000"
# optional for future Agent integration
export DEEPSEEK_API_KEY="sk-..."
# use in-memory redis for local/dev if you don't have Redis running
# export USE_FAKE_REDIS=1

uvicorn app.main:app --reload --port 8000
```

4. Health Check

- GET http://localhost:8000/healthz

## Environment Variables

- `REDIS_URL` (default: `redis://localhost:6379/0`)
- `CORS_ALLOW_ORIGINS` (default: `http://localhost:3000`)
- `DEEPSEEK_API_KEY` (optional, for LangGraph + DeepSeek later)
- `USE_FAKE_REDIS` (optional: `1` to enable in-memory Redis for local/dev)

## Modules (scaffolded)

- Auth: opaque token sessions (7 days)
- Forum: posts/comments CRUD, like toggle, soft delete
- Study: mistakes CRUD by titleSlug, stats, recommendations
- Agent: session + chat (rule-based now); future LangGraph + DeepSeek

## API Overview

All responses are JSON. Authorization via `Authorization: Bearer <token>`.

### Auth

- POST `/auth/register` { username, password } -> { id, username }
- POST `/auth/login` { username, password } -> { token }
- GET `/auth/me` (Bearer) -> { id, username }
- POST `/auth/logout` (Bearer) -> { ok: true }

### Forum

- GET `/forum/posts?offset=0&limit=20` -> { items: [ { id, title, content, author, likes, comments, createdAt } ] }
- POST `/forum/posts` (Bearer) { title, content } -> PostPublic
- GET `/forum/posts/{id}` -> PostPublic
- PUT `/forum/posts/{id}` (Bearer, owner) { title?, content? } -> PostPublic
- DELETE `/forum/posts/{id}` (Bearer, owner) -> { ok: true }
- POST `/forum/posts/{id}/like` (Bearer) -> { liked, likes }
- GET `/forum/posts/{id}/comments` -> { items: CommentPublic[] }
- POST `/forum/posts/{id}/comment` (Bearer) { content } -> CommentPublic
- DELETE `/forum/comments/{comment_id}` (Bearer, owner) with query `post_id` -> { ok: true }

### Study (titleSlug-centric)

- POST `/study/mistakes` (Bearer) { titleSlug, title, difficulty?, tags[], note? } -> MistakePublic
- GET `/study/mistakes` (Bearer) -> { items: MistakePublic[] }
- DELETE `/study/mistakes/{id}` (Bearer) -> { ok: true }
- GET `/study/stats?days=7` (Bearer) -> { total, byDifficulty, byTag, recentTrend }
- GET `/study/recommendations?limit=10` (Bearer) -> { items: Recommendation[] }

### Agent

- POST `/agent/session` (Bearer) { role?, focus? } -> { session_id }
- POST `/agent/chat` (Bearer) { session_id, message } -> { reply, tips?, score? }
- GET `/agent/session/{id}` (Bearer) -> { session_id, messages: Array<{ role, content, time }> }

## Frontend Proxy

Next.js proxies to this backend via app routes (already added):
- `/api/auth/*` -> `${BACKEND_URL}/auth/*`
- `/api/forum/posts` -> `${BACKEND_URL}/forum/posts`
- `/api/study/*` -> `${BACKEND_URL}/study/*`
- `/api/agent/*` -> `${BACKEND_URL}/agent/*`

Set `BACKEND_URL` in `.env.local` (default `http://127.0.0.1:8000`).

## Postman Collection

Import the collection and environment from `postman/`:
- `postman/ning-backend.postman_collection.json`
- `postman/ning-backend.postman_environment.json`

Usage:
1) Import both files into Postman
2) Select environment "Ning Backend Local" and set `auth_token` after login
3) Run requests in Auth / Forum / Study / Agent folders

## Notes

- Redis is the only datastore for now; plan migration to SQL later
- API mounted at root prefixes: `/auth`, `/forum`, `/study`, `/agent`
