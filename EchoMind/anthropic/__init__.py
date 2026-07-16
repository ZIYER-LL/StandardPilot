"""Anthropic-compatible client with provider-neutral telemetry."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import httpx

from core.llm_telemetry import record_call


@dataclass
class _TextBlock:
    text: str
    type: str = "text"


class _MessagesResource:
    def __init__(self, client: "AsyncAnthropic") -> None:
        self._client = client

    async def create(
        self,
        *,
        model: str,
        max_tokens: int,
        messages: List[Dict[str, Any]],
        temperature: float = 0.0,
        system: Optional[str] = None,
        **_: Any,
    ) -> Any:
        text = await self._client._create_message(
            model=model,
            max_tokens=max_tokens,
            messages=messages,
            temperature=temperature,
            system=system,
        )
        return SimpleNamespace(content=[_TextBlock(text=text)])


class AsyncAnthropic:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: Optional[str] = None,
        timeout: float = 180.0,
        **_: Any,
    ) -> None:
        self.provider = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()
        self.api_key = api_key
        self.base_url = (base_url or "").rstrip("/")
        self._http = httpx.AsyncClient(timeout=timeout)
        self.messages = _MessagesResource(self)

    async def _create_message(
        self,
        *,
        model: str,
        max_tokens: int,
        messages: List[Dict[str, Any]],
        temperature: float,
        system: Optional[str],
    ) -> str:
        if self.provider in {"zhipu", "glm", "bigmodel"}:
            return await self._create_openai_compatible(model, max_tokens, messages, temperature, system)
        if self.provider == "anthropic":
            return await self._create_anthropic(model, max_tokens, messages, temperature, system)
        raise RuntimeError(f"Unsupported LLM_PROVIDER: {self.provider}")

    async def _create_openai_compatible(
        self,
        model: str,
        max_tokens: int,
        messages: List[Dict[str, Any]],
        temperature: float,
        system: Optional[str],
    ) -> str:
        started = time.time()
        base_url = self.base_url or "https://open.bigmodel.cn/api/paas/v4"
        request_messages: List[Dict[str, Any]] = []
        if system:
            request_messages.append({"role": "system", "content": system})
        request_messages.extend(messages)
        thinking_enabled = os.getenv("ZHIPU_THINKING_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
        payload: Dict[str, Any] = {
            "model": model,
            "messages": request_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
            "thinking": {"type": "enabled" if thinking_enabled else "disabled"},
        }
        try:
            response = await self._http.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            content = self._extract_openai_content(data)
            if not content and thinking_enabled:
                payload["thinking"] = {"type": "disabled"}
                response = await self._http.post(
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                content = self._extract_openai_content(data)
            if not content:
                choices = data.get("choices") or []
                message = choices[0].get("message", {}) if choices else {}
                finish_reason = choices[0].get("finish_reason") if choices else None
                reasoning = message.get("reasoning_content") or ""
                raise RuntimeError(f"LLM returned empty content (finish_reason={finish_reason!r}, reasoning_chars={len(str(reasoning))})")
            usage = data.get("usage") or {}
            record_call(
                provider="zhipu",
                model=model,
                started_at_epoch=started,
                status="ok",
                provider_response_id=data.get("id"),
                provider_request_id=self._request_id(response),
                input_tokens=self._int_or_none(usage.get("prompt_tokens") or usage.get("input_tokens")),
                output_tokens=self._int_or_none(usage.get("completion_tokens") or usage.get("output_tokens")),
                total_tokens=self._int_or_none(usage.get("total_tokens")),
            )
            return content
        except Exception as exc:
            record_call(provider="zhipu", model=model, started_at_epoch=started, status="error", error=str(exc))
            raise

    async def _create_anthropic(
        self,
        model: str,
        max_tokens: int,
        messages: List[Dict[str, Any]],
        temperature: float,
        system: Optional[str],
    ) -> str:
        started = time.time()
        base_url = self.base_url or "https://api.anthropic.com"
        body: Dict[str, Any] = {"model": model, "max_tokens": max_tokens, "temperature": temperature, "messages": messages}
        if system:
            body["system"] = system
        try:
            response = await self._http.post(
                f"{base_url}/v1/messages",
                headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                json=body,
            )
            response.raise_for_status()
            payload = response.json()
            text = next((str(block["text"]) for block in payload.get("content") or [] if block.get("type") == "text" and block.get("text")), "")
            if not text:
                raise RuntimeError("Anthropic returned no text content")
            usage = payload.get("usage") or {}
            record_call(
                provider="anthropic",
                model=model,
                started_at_epoch=started,
                status="ok",
                provider_response_id=payload.get("id"),
                provider_request_id=self._request_id(response),
                input_tokens=self._int_or_none(usage.get("input_tokens")),
                output_tokens=self._int_or_none(usage.get("output_tokens")),
            )
            return text
        except Exception as exc:
            record_call(provider="anthropic", model=model, started_at_epoch=started, status="error", error=str(exc))
            raise

    @staticmethod
    def _extract_openai_content(payload: Dict[str, Any]) -> str:
        choices = payload.get("choices") or []
        if not choices:
            return ""
        content = (choices[0].get("message") or {}).get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            return "\n".join(str(item["text"]) for item in content if isinstance(item, dict) and item.get("text")).strip()
        return ""

    @staticmethod
    def _request_id(response: httpx.Response) -> Optional[str]:
        for name in ("x-request-id", "request-id", "x-zhipu-request-id", "cf-ray"):
            if response.headers.get(name):
                return response.headers[name]
        return None

    @staticmethod
    def _int_or_none(value: Any) -> Optional[int]:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    async def close(self) -> None:
        await self._http.aclose()
