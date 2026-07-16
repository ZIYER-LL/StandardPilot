"""Redis-backed conversation and trace persistence with an in-memory fallback."""
from __future__ import annotations

import json
import time
from collections import defaultdict, deque
from typing import Any, Deque, Dict, List, Optional

import redis.asyncio as redis


class TraceStore:
    """Persist request traces and conversation summaries.

    Redis is the primary store. A bounded in-memory fallback keeps local development
    usable when Redis is temporarily unavailable.
    """

    def __init__(self, redis_url: str, trace_limit: int = 500, conversation_limit: int = 100):
        self.redis_url = redis_url
        self.trace_limit = trace_limit
        self.conversation_limit = conversation_limit
        self._redis = redis.from_url(redis_url, decode_responses=True)
        self._memory_traces: Dict[str, Dict[str, Any]] = {}
        self._memory_trace_order: Deque[str] = deque(maxlen=trace_limit)
        self._memory_conversations: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)

    async def close(self) -> None:
        await self._redis.aclose()

    async def ping(self) -> bool:
        try:
            return bool(await self._redis.ping())
        except Exception:
            return False

    async def save_trace(self, trace: Dict[str, Any]) -> None:
        trace_id = str(trace["trace_id"])
        user_id = str(trace.get("user_id", "anonymous"))
        conv_id = str(trace.get("conv_id", ""))
        payload = json.dumps(trace, ensure_ascii=False)
        score = float(trace.get("started_at_epoch", time.time()))
        try:
            pipe = self._redis.pipeline()
            pipe.set(f"standardpilot:trace:{trace_id}", payload, ex=7 * 24 * 3600)
            pipe.zadd("standardpilot:traces", {trace_id: score})
            pipe.zremrangebyrank("standardpilot:traces", 0, -(self.trace_limit + 1))
            if conv_id:
                pipe.zadd(f"standardpilot:conversation_traces:{user_id}:{conv_id}", {trace_id: score})
                pipe.expire(f"standardpilot:conversation_traces:{user_id}:{conv_id}", 30 * 24 * 3600)
            await pipe.execute()
        except Exception:
            if trace_id not in self._memory_traces:
                self._memory_trace_order.append(trace_id)
            self._memory_traces[trace_id] = trace
            while len(self._memory_traces) > self.trace_limit and self._memory_trace_order:
                self._memory_traces.pop(self._memory_trace_order.popleft(), None)

    async def get_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        try:
            raw = await self._redis.get(f"standardpilot:trace:{trace_id}")
            if raw:
                return json.loads(raw)
        except Exception:
            pass
        return self._memory_traces.get(trace_id)

    async def list_traces(self, limit: int = 50, user_id: Optional[str] = None, conv_id: Optional[str] = None) -> List[Dict[str, Any]]:
        limit = max(1, min(limit, 200))
        try:
            if user_id and conv_id:
                key = f"standardpilot:conversation_traces:{user_id}:{conv_id}"
            else:
                key = "standardpilot:traces"
            ids = await self._redis.zrevrange(key, 0, limit - 1)
            if ids:
                values = await self._redis.mget([f"standardpilot:trace:{trace_id}" for trace_id in ids])
                return [json.loads(raw) for raw in values if raw]
        except Exception:
            pass
        traces = [self._memory_traces[trace_id] for trace_id in reversed(self._memory_trace_order) if trace_id in self._memory_traces]
        if user_id:
            traces = [item for item in traces if item.get("user_id") == user_id]
        if conv_id:
            traces = [item for item in traces if item.get("conv_id") == conv_id]
        return traces[:limit]

    async def upsert_conversation(self, user_id: str, conv_id: str, **updates: Any) -> Dict[str, Any]:
        key = f"standardpilot:conversation:{user_id}:{conv_id}"
        now = time.time()
        current = await self.get_conversation(user_id, conv_id) or {
            "user_id": user_id,
            "conv_id": conv_id,
            "title": "新会话",
            "created_at_epoch": now,
            "message_count": 0,
        }
        current.update(updates)
        current["updated_at_epoch"] = now
        payload = json.dumps(current, ensure_ascii=False)
        try:
            pipe = self._redis.pipeline()
            pipe.set(key, payload, ex=30 * 24 * 3600)
            pipe.zadd(f"standardpilot:conversations:{user_id}", {conv_id: now})
            pipe.zremrangebyrank(f"standardpilot:conversations:{user_id}", 0, -(self.conversation_limit + 1))
            await pipe.execute()
        except Exception:
            self._memory_conversations[user_id][conv_id] = current
        return current

    async def get_conversation(self, user_id: str, conv_id: str) -> Optional[Dict[str, Any]]:
        try:
            raw = await self._redis.get(f"standardpilot:conversation:{user_id}:{conv_id}")
            if raw:
                return json.loads(raw)
        except Exception:
            pass
        return self._memory_conversations.get(user_id, {}).get(conv_id)

    async def list_conversations(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        limit = max(1, min(limit, self.conversation_limit))
        try:
            ids = await self._redis.zrevrange(f"standardpilot:conversations:{user_id}", 0, limit - 1)
            if ids:
                values = await self._redis.mget([f"standardpilot:conversation:{user_id}:{conv_id}" for conv_id in ids])
                return [json.loads(raw) for raw in values if raw]
        except Exception:
            pass
        values = list(self._memory_conversations.get(user_id, {}).values())
        return sorted(values, key=lambda item: item.get("updated_at_epoch", 0), reverse=True)[:limit]

    async def delete_conversation(self, user_id: str, conv_id: str) -> bool:
        deleted = False
        try:
            pipe = self._redis.pipeline()
            pipe.delete(f"standardpilot:conversation:{user_id}:{conv_id}")
            pipe.zrem(f"standardpilot:conversations:{user_id}", conv_id)
            pipe.delete(f"standardpilot:conversation_traces:{user_id}:{conv_id}")
            results = await pipe.execute()
            deleted = bool(results[0])
        except Exception:
            pass
        deleted = self._memory_conversations.get(user_id, {}).pop(conv_id, None) is not None or deleted
        return deleted
