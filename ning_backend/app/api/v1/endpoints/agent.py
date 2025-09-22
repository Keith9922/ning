from __future__ import annotations

import datetime as dt
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

import app.core.runtime as runtime
from ....core.security import require_token
from ....schemas.agent import ChatRequest, ChatResponse, SessionCreate, SessionDetail, SessionPublic


router = APIRouter()


def _now_iso() -> str:
    return dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).isoformat()


async def _ensure_user(token: str) -> str:
    if runtime.redis_client is None:
        raise HTTPException(status_code=500, detail="Redis not initialized")
    uid = await runtime.redis_client.get(f"session:{token}")
    if not uid:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return uid


@router.post("/session", response_model=SessionPublic)
async def create_session(payload: SessionCreate | None = None, token: str = Depends(require_token)) -> SessionPublic:
    uid = await _ensure_user(token)
    sid = await runtime.redis_client.incr(f"agent:{uid}:session_seq")
    await runtime.redis_client.hset(
        f"agent:{uid}:session:{sid}",
        mapping={
            "session_id": str(sid),
            "created_at": _now_iso(),
            "role": (payload.role if payload else "") or "",
            "focus": (payload.focus if payload else "") or "",
        },
    )
    await runtime.redis_client.sadd(f"agent:{uid}:sessions", sid)
    return SessionPublic(session_id=str(sid))


def _rule_based_reply(message: str, role: str, focus: str) -> ChatResponse:
    text = message.lower()
    # Simple intents
    if any(k in text for k in ["hello", "hi", "你好"]):
        return ChatResponse(reply="你好，我是你的模拟面试官。请先简要介绍一下自己和擅长方向。", tips="条理清晰，突出关键成绩。")
    if any(k in text for k in ["二分", "binary search"]):
        return ChatResponse(reply="二分查找的时间复杂度是多少？在旋转数组中如何应用？", tips="先给出 O(log n)；再讲不变式与边界处理。", score=7)
    if any(k in text for k in ["hash", "哈希"]):
        return ChatResponse(reply="说说哈希冲突的常见解决方案，以及适用场景。", tips="拉链法、开放寻址、再哈希。")
    if any(k in text for k in ["dp", "动态规划"]):
        return ChatResponse(reply="给出一道背包或最长子序列类 DP 的状态定义与转移。", tips="状态压缩可作为加分项。", score=8)
    if any(k in text for k in ["tcp", "三次握手", "四次挥手"]):
        return ChatResponse(reply="请简述 TCP 三次握手与四次挥手的过程与原因。", tips="半关闭、TIME_WAIT、RST 情况。")
    # Fallback
    return ChatResponse(reply=f"针对{role or '通用岗位'}（方向：{focus or '综合'}），请阐述你最熟悉的项目难点与优化。", tips="结构化表达：背景-问题-方案-效果-复盘。")


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, token: str = Depends(require_token)) -> ChatResponse:
    uid = await _ensure_user(token)
    sess = await runtime.redis_client.hgetall(f"agent:{uid}:session:{payload.session_id}")
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    role = sess.get("role", "")
    focus = sess.get("focus", "")

    # append user message
    idx = (int((await runtime.redis_client.get(f"agent:{uid}:session:{payload.session_id}:msg_seq")) or 0) + 1)
    await runtime.redis_client.hset(
        f"agent:{uid}:session:{payload.session_id}:msg:{idx}",
        mapping={"role": "user", "content": payload.message, "time": _now_iso()},
    )
    await runtime.redis_client.set(f"agent:{uid}:session:{payload.session_id}:msg_seq", idx)

    # rule reply
    reply = _rule_based_reply(payload.message, role, focus)
    idx2 = idx + 1
    await runtime.redis_client.hset(
        f"agent:{uid}:session:{payload.session_id}:msg:{idx2}",
        mapping={"role": "assistant", "content": reply.reply, "time": _now_iso()},
    )
    await runtime.redis_client.set(f"agent:{uid}:session:{payload.session_id}:msg_seq", idx2)
    return reply


@router.get("/session/{session_id}", response_model=SessionDetail)
async def session_detail(session_id: str, token: str = Depends(require_token)) -> SessionDetail:
    uid = await _ensure_user(token)
    if not await runtime.redis_client.hgetall(f"agent:{uid}:session:{session_id}"):
        raise HTTPException(status_code=404, detail="Session not found")
    seq = int((await runtime.redis_client.get(f"agent:{uid}:session:{session_id}:msg_seq")) or 0)
    msgs: list[dict] = []
    for i in range(1, seq + 1):
        m = await runtime.redis_client.hgetall(f"agent:{uid}:session:{session_id}:msg:{i}")
        if m:
            msgs.append(m)
    return SessionDetail(session_id=str(session_id), messages=msgs)



