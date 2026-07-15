"""Normalize provider-specific environment variables before app imports.

Python imports ``sitecustomize`` automatically during interpreter startup when
it is available on ``sys.path``.  The backend runs from ``/app``, so this file
lets the existing configuration entry point keep working while new provider
variables are introduced.
"""

from __future__ import annotations

import os


provider = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()

if provider in {"zhipu", "glm", "bigmodel"}:
    api_key = os.getenv("ZHIPU_API_KEY", "").strip()
    if api_key:
        os.environ["ANTHROPIC_API_KEY"] = api_key
    os.environ["ANTHROPIC_MODEL"] = os.getenv(
        "ZHIPU_MODEL", "glm-4.7-flash"
    ).strip()
    os.environ["ANTHROPIC_BASE_URL"] = os.getenv(
        "ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"
    ).strip().rstrip("/")
