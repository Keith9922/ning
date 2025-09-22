from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional


class AsyncMemoryRedis:
    def __init__(self) -> None:
        self._kv: Dict[str, Any] = {}
        self._hash: Dict[str, Dict[str, Any]] = {}
        self._sets: Dict[str, set] = {}
        self._ttl: Dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def _cleanup(self) -> None:
        now = time.time()
        expired = [k for k, t in self._ttl.items() if t <= now]
        for k in expired:
            self._kv.pop(k, None)
            self._ttl.pop(k, None)

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None

    async def get(self, key: str) -> Optional[str]:
        async with self._lock:
            await self._cleanup()
            return None if key not in self._kv else str(self._kv[key])

    async def set(self, key: str, value: Any, nx: bool | None = None) -> bool:
        async with self._lock:
            await self._cleanup()
            if nx:
                if key in self._kv:
                    return False
            self._kv[key] = value
            self._ttl.pop(key, None)
            return True

    async def setex(self, key: str, ttl_seconds: int, value: Any) -> bool:
        async with self._lock:
            await self._cleanup()
            self._kv[key] = value
            self._ttl[key] = time.time() + ttl_seconds
            return True

    async def incr(self, key: str) -> int:
        async with self._lock:
            await self._cleanup()
            cur = int(self._kv.get(key, 0)) + 1
            self._kv[key] = cur
            return cur

    async def hset(self, key: str, mapping: Dict[str, Any]) -> int:
        async with self._lock:
            await self._cleanup()
            h = self._hash.setdefault(key, {})
            h.update(mapping)
            return len(mapping)

    async def hgetall(self, key: str) -> Dict[str, Any]:
        async with self._lock:
            await self._cleanup()
            return dict(self._hash.get(key, {}))

    async def sadd(self, key: str, *members: Any) -> int:
        async with self._lock:
            await self._cleanup()
            s = self._sets.setdefault(key, set())
            before = len(s)
            for m in members:
                s.add(m)
            return len(s) - before

    async def srem(self, key: str, *members: Any) -> int:
        async with self._lock:
            await self._cleanup()
            s = self._sets.setdefault(key, set())
            before = len(s)
            for m in members:
                s.discard(m)
            return before - len(s)

    async def smembers(self, key: str) -> set:
        async with self._lock:
            await self._cleanup()
            return set(self._sets.get(key, set()))

    async def sismember(self, key: str, member: Any) -> bool:
        async with self._lock:
            await self._cleanup()
            return member in self._sets.get(key, set())

    async def scard(self, key: str) -> int:
        async with self._lock:
            await self._cleanup()
            return len(self._sets.get(key, set()))

    async def delete(self, key: str) -> int:
        async with self._lock:
            await self._cleanup()
            existed = 1 if key in self._kv else 0
            self._kv.pop(key, None)
            self._ttl.pop(key, None)
            return existed


