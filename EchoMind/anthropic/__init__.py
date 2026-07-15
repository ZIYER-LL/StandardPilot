"""Small Anthropic-compatible async client for StandardPilot.

StandardPilot historically calls ``AsyncAnthropic.messages.create`` from its
agents, intent recognizer, memory manager, RAG reranker, and evaluator. This
module keeps that internal interface stable while routing requests to either
Anthropic Messages API or an OpenAI-compatible provider such as Zhipu GLM.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import httpx


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
    """Compatibility client exposing the subset used by StandardPilot."""

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
            return await self._create_openai_compatible(
                model=model,
                max_tokens=max_tokens,
                messages=messages,
                temperature=temperature,
                system=system,
            )
        if self.provider == "anthropic":
            return await self._create_anthropic(
                model=model,
                max_tokens=max_tokens,
                messages=messages,
                temperature=temperature,
                system=system,
            )
        raise RuntimeError(f"Unsupported LLM_PROVIDER: {self.provider}")

    async def _create_openai_compatible(
        self,
        *,
        model: str,
        max_tokens: int,
        messages: List[Dict[str, Any]],
        temperature: float,
        system: Optional[str],
    ) -> str:
        base_url = self.base_url or "https://open.bigmodel.cn/api/paas/v4"
        request_messages: List[Dict[str, Any]] = []
        if system:
            request_messages.append({"role": "system", "content": system})
        request_messages.extend(messages)

        payload: Dict[str, Any] = {
            "model": model,
            "messages": request_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }

        # GLM-4.7 defaults to thinking mode. Short internal tasks such as intent
        # recognition, query rewriting and reranking can consume the entire
        # output budget in reasoning_content and leave message.content empty.
        # Disable thinking by default for this application. It can be enabled
        # explicitly with ZHIPU_THINKING_ENABLED=true.
        thinking_enabled = os.getenv("ZHIPU_THINKING_ENABLED", "false").strip().lower() in {
            "1", "true", "yes", "on"
        }
        payload["thinking"] = {"type": "enabled" if thinking_enabled else "disabled"}

        response = await self._http.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        content = self._extract_openai_content(data)

        # Defensive retry: some compatible endpoints may still return only
        # reasoning_content. Retry once with thinking explicitly disabled.
        if not content and thinking_enabled:
            payload["thinking"] = {"type": "disabled"}
            retry = await self._http.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            retry.raise_for_status()
            data = retry.json()
            content = self._extract_openai_content(data)

        if not content:
            choices = data.get("choices") or []
            message = choices[0].get("message", {}) if choices else {}
            finish_reason = choices[0].get("finish_reason") if choices else None
            reasoning = message.get("reasoning_content") or ""
            raise RuntimeError(
                "LLM returned empty content "
                f"(finish_reason={finish_reason!r}, reasoning_chars={len(str(reasoning))})"
            )
        return content

    @staticmethod
    def _extract_openai_content(payload: Dict[str, Any]) -> str:
        choices = payload.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("text"):
                    parts.append(str(item["text"]))
            return "\n".join(parts).strip()
        return ""

    async def _create_anthropic(
        self,
        *,
        model: str,
        max_tokens: int,
        messages: List[Dict[str, Any]],
        temperature: float,
        system: Optional[str],
    ) -> str:
        base_url = self.base_url or "https://api.anthropic.com"
        body: Dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
        if system:
            body["system"] = system

        response = await self._http.post(
            f"{base_url}/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json=body,
        )
        response.raise_for_status()
        payload = response.json()
        blocks = payload.get("content") or []
        for block in blocks:
            if block.get("type") == "text" and block.get("text"):
                return str(block["text"])
        raise RuntimeError("Anthropic returned no text content")

    async def close(self) -> None:
        await self._http.aclose()
