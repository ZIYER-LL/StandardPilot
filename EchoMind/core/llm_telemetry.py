"""Request-scoped telemetry for every LLM call."""
from __future__ import annotations

import time
from contextvars import ContextVar, Token
from typing import Any, Dict, List, Optional

_calls: ContextVar[Optional[List[Dict[str, Any]]]] = ContextVar("standardpilot_llm_calls", default=None)
_stage: ContextVar[str] = ContextVar("standardpilot_llm_stage", default="unspecified")


def begin_capture() -> Token:
    return