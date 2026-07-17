"""Contracts for adaptive routing and response budgets."""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ExecutionMode(str, Enum):
    DIRECT_TOOL = "direct_tool"
    DIRECT_GENERATION = "direct_generation"
    RAG_GENERATION = "rag_generation"
    SPECIALIST_AGENT = "specialist_agent"
    MANAGER_AGENT = "manager_agent"
    CLARIFY = "clarify"


class ResponseProfile(str, Enum):
    BRIEF = "brief"
    STANDARD = "standard"
    DETAILED = "detailed"
    REPORT = "report"


@dataclass(frozen=True)
class ResponseBudget:
    profile: ResponseProfile
    max_tokens: int
    max_llm_calls: int
    deadline_ms: int
    max_retrieval_rounds: int = 1
    max_agent_handoffs: int = 0


@dataclass
class RouteDecision:
    mode: ExecutionMode
    task_type: str
    confidence: float
    response_profile: ResponseProfile
    specialist: Optional[str] = None
    retrieval_required: bool = False
    reason_codes: List[str] = field(default_factory=list)
    source: str = "router"
    clarification_question: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["mode"] = self.mode.value
        data["response_profile"] = self.response_profile.value
        return data


_DEFAULTS = {
    ResponseProfile.BRIEF: (384, 1, 8_000, 0, 0),
    ResponseProfile.STANDARD: (1024, 2, 18_000, 1, 0),
    ResponseProfile.DETAILED: (2048, 4, 35_000, 2, 1),
    ResponseProfile.REPORT: (3072, 6, 50_000, 2, 2),
}


def budget_for(profile: ResponseProfile) -> ResponseBudget:
    tokens, calls, deadline, retrieval_rounds, handoffs = _DEFAULTS[profile]
    prefix = f"BUDGET_{profile.value.upper()}"
    return ResponseBudget(
        profile=profile,
        max_tokens=int(os.getenv(f"{prefix}_MAX_TOKENS", str(tokens))),
        max_llm_calls=int(os.getenv(f"{prefix}_MAX_LLM_CALLS", str(calls))),
        deadline_ms=int(os.getenv(f"{prefix}_DEADLINE_MS", str(deadline))),
        max_retrieval_rounds=int(os.getenv(f"{prefix}_MAX_RETRIEVAL_ROUNDS", str(retrieval_rounds))),
        max_agent_handoffs=int(os.getenv(f"{prefix}_MAX_AGENT_HANDOFFS", str(handoffs))),
    )
