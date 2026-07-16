"""Request-scoped telemetry for every LLM call."""
from __future__ import annotations

import time
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any, Dict, Iterator, List, Optional

_calls: ContextVar[Optional[List[Dict[str, Any]]]] = ContextVar("standardpilot_llm_calls", default=None)
_stage: ContextVar[str] = ContextVar("standardpilot_llm_stage", default="unspecified")


def begin_capture() -> Token:
    """Start a new request-local call collection and return the reset token."""
    return _calls.set([])


def finish_capture(token: Token) -> List[Dict[str, Any]]:
    """Return captured calls and restore the previous context."""
    calls = list(_calls.get() or [])
    _calls.reset(token)
    return calls


@contextmanager
def stage(name: str) -> Iterator[None]:
    token = _stage.set(name)
    try:
        yield
    finally:
        _stage.reset(token)


def record_call(
    *,
    provider: str,
    model: str,
    started_at_epoch: float,
    status: str,
    provider_response_id: Optional[str] = None,
    provider_request_id: Optional[str] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    total_tokens: Optional[int] = None,
    error: Optional[str] = None,
    streaming: bool = False,
) -> Dict[str, Any]:
    ended = time.time()
    item: Dict[str, Any] = {
        "sequence": len(_calls.get() or []) + 1,
        "stage": _stage.get(),
        "provider": provider,
        "model": model,
        "streaming": streaming,
        "status": status,
        "started_at_epoch": started_at_epoch,
        "ended_at_epoch": ended,
        "latency_ms": round((ended - started_at_epoch) * 1000, 1),
        "provider_response_id": provider_response_id,
        "provider_request_id": provider_request_id,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens if total_tokens is not None else (
            input_tokens + output_tokens if input_tokens is not None and output_tokens is not None else None
        ),
    }
    if error:
        item["error"] = error
    calls = _calls.get()
    if calls is not None:
        calls.append(item)
    return item


def summarize(calls: List[Dict[str, Any]]) -> Dict[str, Any]:
    successful = [item for item in calls if item.get("status") == "ok"]
    return {
        "llm_call_count": len(calls),
        "llm_success_count": len(successful),
        "input_tokens": sum(int(item.get("input_tokens") or 0) for item in calls),
        "output_tokens": sum(int(item.get("output_tokens") or 0) for item in calls),
        "total_tokens": sum(int(item.get("total_tokens") or 0) for item in calls),
        "provider_request_ids": [item["provider_request_id"] for item in calls if item.get("provider_request_id")],
        "provider_response_ids": [item["provider_response_id"] for item in calls if item.get("provider_response_id")],
    }
