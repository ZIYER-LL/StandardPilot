"""Multi-provider model gateway with role pools, bounded concurrency and fallback."""
from __future__ import annotations

import asyncio
import json
import os
import random
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from core.llm_telemetry import record_call

_OPENAI_COMPAT = {"zhipu", "glm", "bigmodel", "openai", "openai_compatible", "deepseek", "qwen", "dashscope"}


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    provider: str
    api_key: str
    base_url: str
    model: str
    max_concurrency: int = 2


class ModelGateway:
    def __init__(self) -> None:
        self.primary = self._spec("PRIMARY", legacy=True)
        self.fallback = self._spec("FALLBACK", legacy=False)
        self.router = self._spec("ROUTER", legacy=False)
        self._limits: Dict[str, asyncio.Semaphore] = {}
        for spec in (self.primary, self.fallback, self.router):
            if spec and spec.name not in self._limits:
                self._limits[spec.name] = asyncio.Semaphore(max(1, spec.max_concurrency))

    def _spec(self, prefix: str, legacy: bool) -> Optional[ProviderSpec]:
        provider = os.getenv(f"{prefix}_LLM_PROVIDER", "").strip().lower()
        if not provider and legacy:
            provider = os.getenv("LLM_PROVIDER", "zhipu").strip().lower()
        if not provider:
            return None
        legacy_key = os.getenv("ZHIPU_API_KEY") or os.getenv("ANTHROPIC_API_KEY", "")
        key = os.getenv(f"{prefix}_LLM_API_KEY", legacy_key if legacy else "")
        if not key:
            return None
        if provider in _OPENAI_COMPAT:
            default_base = os.getenv("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
            default_model = os.getenv("ZHIPU_MODEL", "glm-4.7-flash")
        else:
            default_base = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
            default_model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
        return ProviderSpec(
            name=f"{prefix.lower()}:{provider}:{os.getenv(f'{prefix}_LLM_MODEL', default_model)}",
            provider=provider,
            api_key=key,
            base_url=os.getenv(f"{prefix}_LLM_BASE_URL", default_base).rstrip("/"),
            model=os.getenv(f"{prefix}_LLM_MODEL", default_model),
            max_concurrency=int(os.getenv(f"{prefix}_LLM_MAX_CONCURRENCY", "1" if prefix == "ROUTER" else "2")),
        )

    def _chain(self, role: str) -> List[ProviderSpec]:
        ordered = (self.router, self.primary, self.fallback) if role == "router" else (self.primary, self.fallback)
        result: List[ProviderSpec] = []
        for spec in ordered:
            if spec and spec.name not in {item.name for item in result}:
                result.append(spec)
        return result

    async def complete(self, *, messages: List[Dict[str, Any]], system: str = "", max_tokens: int = 512, temperature: float = 0.0, role: str = "generation") -> str:
        parts: List[str] = []
        async for token in self.stream(messages=messages, system=system, max_tokens=max_tokens, temperature=temperature, role=role):
            parts.append(token)
        return "".join(parts)

    async def stream(self, *, messages: List[Dict[str, Any]], system: str = "", max_tokens: int = 1024, temperature: float = 0.2, role: str = "generation") -> AsyncIterator[str]:
        errors: List[str] = []
        for spec in self._chain(role):
            for attempt in range(2):
                try:
                    async with self._limits[spec.name]:
                        async for token in self._stream_once(spec, messages, system, max_tokens, temperature):
                            yield token
                    return
                except httpx.HTTPStatusError as exc:
                    errors.append(f"{spec.name}:{exc.response.status_code}")
                    if exc.response.status_code != 429 or attempt >= 1:
                        break
                    retry_after = float(exc.response.headers.get("retry-after", "0") or 0)
                    await asyncio.sleep(max(retry_after, 0.5 * (2 ** attempt)) + random.random() * 0.2)
                except Exception as exc:
                    errors.append(f"{spec.name}:{type(exc).__name__}")
                    break
        raise RuntimeError("所有模型供应商均不可用: " + ", ".join(errors))

    async def _stream_once(self, spec: ProviderSpec, messages: List[Dict[str, Any]], system: str, max_tokens: int, temperature: float) -> AsyncIterator[str]:
        started = time.time()
        if spec.provider in _OPENAI_COMPAT:
            request_messages = ([{"role": "system", "content": system}] if system else []) + messages
            body = {"model": spec.model, "messages": request_messages, "max_tokens": max_tokens, "temperature": temperature, "stream": True, "stream_options": {"include_usage": True}}
            if spec.provider in {"zhipu", "glm", "bigmodel"}:
                body["thinking"] = {"type": "disabled"}
            url = f"{spec.base_url}/chat/completions"
            headers = {"Authorization": f"Bearer {spec.api_key}", "Content-Type": "application/json"}
        else:
            body = {"model": spec.model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature, "stream": True}
            if system:
                body["system"] = system
            url = f"{spec.base_url}/v1/messages"
            headers = {"x-api-key": spec.api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
        response_id = request_id = None
        usage: Dict[str, Any] = {}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=20.0)) as client:
                async with client.stream("POST", url, headers=headers, json=body) as response:
                    response.raise_for_status()
                    request_id = response.headers.get("x-request-id") or response.headers.get("request-id")
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if not raw or raw == "[DONE]":
                            continue
                        event = json.loads(raw)
                        response_id = response_id or event.get("id")
                        usage = event.get("usage") or usage
                        if spec.provider in _OPENAI_COMPAT:
                            choices = event.get("choices") or []
                            text = (choices[0].get("delta") or {}).get("content") if choices else None
                        else:
                            delta = event.get("delta") or {}
                            text = delta.get("text") if event.get("type") == "content_block_delta" else None
                            if event.get("type") == "message_start":
                                usage = (event.get("message") or {}).get("usage") or usage
                            if event.get("type") == "message_delta":
                                usage.update(event.get("usage") or {})
                        if isinstance(text, str) and text:
                            yield text
            input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens")
            output_tokens = usage.get("completion_tokens") or usage.get("output_tokens")
            record_call(provider=spec.provider, model=spec.model, started_at_epoch=started, status="ok", provider_response_id=response_id, provider_request_id=request_id, input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=usage.get("total_tokens"), streaming=True)
        except Exception as exc:
            record_call(provider=spec.provider, model=spec.model, started_at_epoch=started, status="error", error=str(exc), streaming=True)
            raise
