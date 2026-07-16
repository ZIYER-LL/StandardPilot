"""Shared contracts for adaptive routing, execution modes, and response budgets."""
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