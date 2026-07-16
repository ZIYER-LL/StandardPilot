"""Provider-neutral token streaming with exact call telemetry."""
from __future__ import annotations

import json
import os
import time
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from core.llm_telemetry import record_call


def _request_id(response: httpx.Response) -> Optional[str]:
    for name in ("x-request-id", "request-id", "x-zhipu-request-id", "cf-ray"):
        if response.headers.get(name):
            return response.headers[name]
    return None


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


async def stream_text(
    *,
    api_key: str,
    base_url: str,
    model: str,
    messages: List[Dict[str, Any]],
    system: Optional[str] = None,
    max_tokens: int = 1024,
    temperature: float = 0.2,
) -> AsyncIterator[str]:
    provider = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()
    started = time.time()
    timeout = httpx.Timeout(connect=20.0, read=180.0, write=30.0, pool=20.0)
    response_id: Optional[str] = None
    request_id: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    recorded = False
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            if provider in {"zhipu", "glm", "bigmodel"}:
                request_messages: List[Dict[str, Any]] = []
                if system:
                    request_messages.append({"role": "system", "content": system})
                request_messages.extend(messages)
                payload = {
                    "model": model,
                    "messages": request_messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "stream": True,
                    "stream_options": {"include_usage": True},
                    "thinking": {"type": "disabled"},
                }
                async with client.stream(
                    "POST",
                    f"{base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    request_id = _request_id(response)
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data or data == "[DONE]":
                            continue
                        chunk = json.loads(data)
                        response_id = response_id or chunk.get("id")
                        usage = chunk.get("usage") or {}
                        if usage:
                            input_tokens = _to_int(usage.get("prompt_tokens") or usage.get("input_tokens"))
                            output_tokens = _to_int(usage.get("completion_tokens") or usage.get("output_tokens"))
                            total_tokens = _to_int(usage.get("total_tokens"))
                        choices = chunk.get("choices") or []
                        if choices:
                            content = (choices[0].get("delta") or {}).get("content")
                            if isinstance(content, str) and content:
                                yield content
                record_call(
                    provider="zhipu",
                    model=model,
                    started_at_epoch=started,
                    status="ok",
                    provider_response_id=response_id,
                    provider_request_id=request_id,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    streaming=True,
                )
                recorded = True
                return

            body: Dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": messages,
                "stream": True,
            }
            if system:
                body["system"] = system
            async with client.stream(
                "POST",
                f"{base_url.rstrip('/')}/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json=body,
            ) as response:
                response.raise_for_status()
                request_id = _request_id(response)
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    event = json.loads(data)
                    if event.get("type") == "message_start":
                        message = event.get("message") or {}
                        response_id = message.get("id")
                        usage = message.get("usage") or {}
                        input_tokens = _to_int(usage.get("input_tokens"))
                    elif event.get("type") == "message_delta":
                        usage = event.get("usage") or {}
                        output_tokens = _to_int(usage.get("output_tokens"))
                    elif event.get("type") == "content_block_delta":
                        text = (event.get("delta") or {}).get("text")
                        if isinstance(text, str) and text:
                            yield text
            record_call(
                provider="anthropic",
                model=model,
                started_at_epoch=started,
                status="ok",
                provider_response_id=response_id,
                provider_request_id=request_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                streaming=True,
            )
            recorded = True
    except Exception as exc:
        if not recorded:
            record_call(
                provider="zhipu" if provider in {"zhipu", "glm", "bigmodel"} else provider,
                model=model,
                started_at_epoch=started,
                status="error",
                provider_response_id=response_id,
                provider_request_id=request_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                error=str(exc),
                streaming=True,
            )
        raise
