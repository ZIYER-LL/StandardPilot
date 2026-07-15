"""Small Anthropic-compatible async client for StandardPilot.

StandardPilot historically calls ``AsyncAnthropic.messages.create`` from its
agents, intent recognizer, memory manager, RAG reranker, and evaluator.  This
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

        response = await self._http.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": request_messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": False,
            },
        )
        response.raise_for_status()
        payload = response.json()
        choices = payload.get("choices") or []
        if not choices:
            raise RuntimeError(f"LLM returned no choices: {payload}")
        content = choices[0].get("message", {}).get("content")
        if not content:
            raise RuntimeError("LLM returned empty content")
        return str(content)

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
