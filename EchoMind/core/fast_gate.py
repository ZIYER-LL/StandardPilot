"""Deterministic fast path for requests that have authoritative tool answers."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional


_TDOC_RE = re.compile(r"\b(?:S\d|R\d|C\d|RP|SP|CP|GP|TSG)[-_ ]?\d{5,8}\b", re.I)
_TASK_RE = re.compile(r"(?:任务|job|task)[-_ :#]*([a-zA-Z0-9-]{4,})", re.I)


@dataclass
class FastGateResult:
    matched: bool
    action: Optional[str] = None
    arguments: Optional[Dict[str, Any]] = None
    reason_code: str = "no_match"


class FastGate:
    """Only matches high precision operations; uncertain requests continue to the router."""

    def match(self, message: str) -> FastGateResult:
        text = (message or "").strip()
        lower = text.lower()
        if not text:
            return FastGateResult(True, "clarify", {"question": "请描述需要处理的标准研究任务。"}, "empty_request")
        if lower in {"你好", "您好", "hi", "hello", "你是谁", "你能做什么", "介绍一下standardpilot"}:
            return FastGateResult(True, "system_info", {}, "fixed_system_description")
        if any(key in lower for key in ("知识库统计", "多少篇文稿", "多少个文档", "多少文档", "知识库有多少")):
            return FastGateResult(True, "knowledge_stats", {}, "authoritative_store_query")
        tdoc = _TDOC_RE.search(text)
        if tdoc and any(key in lower for key in ("查询", "查找", "打开", "找到", "文稿", "tdoc")):
            return FastGateResult(True, "document_lookup", {"tdoc_id": tdoc.group(0)}, "exact_document_identifier")
        task = _TASK_RE.search(text)
        if task and any(key in lower for key in ("状态", "进度", "完成", "status", "progress")):
            return FastGateResult(True, "task_status", {"task_id": task.group(1)}, "exact_task_identifier")
        if any(key in lower for key in ("会议列表", "有哪些会议", "meeting list")):
            return FastGateResult(True, "meeting_list", {}, "authoritative_store_query")
        if any(key in lower for key in ("导入文稿", "上传文稿", "导出报告", "导出文稿")):
            return FastGateResult(True, "ui_action", {"request": text}, "deterministic_product_action")
        return FastGateResult(False)
