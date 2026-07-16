"""Adaptive triage router: deterministic confidence first, model fallback for ambiguity."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from core.adaptive_contracts import ExecutionMode, ResponseProfile, RouteDecision
from core.llm_telemetry import stage
from core.model_gateway import ModelGateway


class AdaptiveRouter:
    def __init__(self, gateway: ModelGateway) -> None:
        self.gateway = gateway

    async def decide(self, message: str, history: Optional[List[Dict[str, str]]] = None) -> RouteDecision:
        heuristic = self._heuristic(message)
        if heuristic.confidence >= 0.86:
            return heuristic
        try:
            return await self._model_decision(message, history, heuristic)
        except Exception:
            return heuristic

    def _heuristic(self, message: str) -> RouteDecision:
        text = (message or "").strip().lower()
        detailed = any(key in text for key in ("详细", "深入", "全面", "逐条", "报告"))
        report = any(key in text for key in ("proposal", "提案", "草稿", "正式报告"))
        compound = sum(1 for key in ("总结", "比较", "分析", "判断", "生成", "评审", "提案") if key in text) >= 3
        gap = any(key in text for key in ("gap", "标准化空白", "标准化价值", "是否覆盖", "实现问题"))
        tdoc = any(key in text for key in ("tdoc", "t-doc", "文稿摘要", "总结这篇", "总结这几篇"))
        review = any(key in text for key in ("challenge", "质疑", "攻防", "review defense"))
        unclear = len(text) < 4 or text in {"这个呢", "继续", "分析一下", "怎么看"}
        if unclear:
            return RouteDecision(ExecutionMode.CLARIFY, "unclear", 0.92, ResponseProfile.BRIEF, reason_codes=["missing_task_context"], source="heuristic", clarification_question="请补充需要分析的文稿、议题或具体问题。")
        if compound:
            return RouteDecision(ExecutionMode.MANAGER_AGENT, "compound_analysis", 0.90, ResponseProfile.REPORT if report else ResponseProfile.DETAILED, retrieval_required=True, reason_codes=["multiple_distinct_subtasks"], source="heuristic")
        if report:
            return RouteDecision(ExecutionMode.SPECIALIST_AGENT, "proposal_draft", 0.93, ResponseProfile.REPORT, specialist="proposal_writer", retrieval_required=True, reason_codes=["formal_artifact_requested"], source="heuristic")
        if review:
            return RouteDecision(ExecutionMode.SPECIALIST_AGENT, "review_defense", 0.90, ResponseProfile.DETAILED, specialist="review_defense", retrieval_required=True, reason_codes=["specialist_review_task"], source="heuristic")
        if gap:
            return RouteDecision(ExecutionMode.SPECIALIST_AGENT, "gap_analysis", 0.90, ResponseProfile.DETAILED, specialist="standard_analyst", retrieval_required=True, reason_codes=["specialist_gap_task"], source="heuristic")
        if tdoc:
            return RouteDecision(ExecutionMode.SPECIALIST_AGENT, "tdoc_summary", 0.88, ResponseProfile.DETAILED if detailed else ResponseProfile.STANDARD, specialist="tdoc_analyst", retrieval_required=True, reason_codes=["document_analysis_task"], source="heuristic")
        if any(key in text for key in ("3gpp", "标准", "nwdaf", "5gc", "amf", "smf", "pcf", "qos", "release", "agenda")):
            return RouteDecision(ExecutionMode.RAG_GENERATION, "standard_qa", 0.84, ResponseProfile.DETAILED if detailed else ResponseProfile.STANDARD, retrieval_required=True, reason_codes=["domain_knowledge_required"], source="heuristic")
        return RouteDecision(ExecutionMode.DIRECT_GENERATION, "general_chat", 0.72, ResponseProfile.DETAILED if detailed else ResponseProfile.BRIEF, reason_codes=["no_external_evidence_required"], source="heuristic")

    async def _model_decision(self, message: str, history: Optional[List[Dict[str, str]]], fallback: RouteDecision) -> RouteDecision:
        prompt = {"message": message, "recent_history": history[-3:] if history else [], "allowed_modes": [item.value for item in ExecutionMode], "allowed_profiles": [item.value for item in ResponseProfile], "fallback": fallback.to_dict()}
        system = "你是受约束的任务路由器。只输出JSON，不回答用户问题。选择最短且足够的执行模式；复杂多任务才用manager_agent。"
        with stage("adaptive_router"):
            raw = await self.gateway.complete(messages=[{"role": "user", "content": json.dumps(prompt, ensure_ascii=False)}], system=system, max_tokens=280, temperature=0.0, role="router")
        start, end = raw.find("{"), raw.rfind("}") + 1
        data: Dict[str, Any] = json.loads(raw[start:end])
        return RouteDecision(
            mode=ExecutionMode(data.get("mode", fallback.mode.value)),
            task_type=str(data.get("task_type", fallback.task_type)),
            confidence=float(data.get("confidence", 0.7)),
            response_profile=ResponseProfile(data.get("response_profile", fallback.response_profile.value)),
            specialist=data.get("specialist"),
            retrieval_required=bool(data.get("retrieval_required", fallback.retrieval_required)),
            reason_codes=[str(item) for item in data.get("reason_codes", ["model_triage"])][:5],
            source="model",
            clarification_question=data.get("clarification_question"),
        )
