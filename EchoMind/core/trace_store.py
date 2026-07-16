"""Redis-backed conversation and trace persistence with an in-memory fallback."""
from __future__ import annotations

import json
import time
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional

import redis.asyncio as redis


class TraceStore:
    def __init__(self, redis_url: str, trace_limit: int = 500, conversation_limit: int = 100):
        self.redis_url = redis_url
        self.trace_limit = trace_limit
        self.con