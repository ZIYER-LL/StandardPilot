"""Provider-neutral token streaming used by the observable chat endpoint."""
from __future__ import annotations

import json
import os
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx


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
    timeout = httpx.Timeout(connect=20.0, read=180.0, write=30.0, pool=20.0)
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
                "thinking": {"type": "disabled"},
            }
            async with client.stream(
                "POST",
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    chunk = json.loads(data)
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    content = (choices[0].get("delta") or {}).get("content")
                    if isinstance(content, str) and content:
                        yield content
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
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                event = json.loads(data)
                if event.get("type") == "content_block_delta":
                    delta = event.get("delta") or {}
                    text = delta.get("text")
                    if isinstance(text, str) and text:
                        yield text
