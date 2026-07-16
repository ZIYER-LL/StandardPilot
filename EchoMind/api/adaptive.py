"""Adaptive chat API with fast gate, dynamic routing, budgets and provider fallback."""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request as HttpRequest
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import api.main as main_api
from core.adaptive_contracts import ExecutionMode, ResponseProfile, budget_for
from core.adaptive_router import AdaptiveRouter
from core.fast_gate import FastGate
from core.llm_telemetry import begin_capture, finish_capture, stage, summarize
from core.manager_runtime import ManagerRuntime
from core.model_gateway import ModelGateway

router = APIRouter(tags=["Adaptive Agent"])
_gateway: Optional[ModelGateway] = None
_router: Optional[AdaptiveRouter] = None
_manager: Optional[ManagerRuntime] = None
_gate = FastGate()


class AdaptiveChatRequest(BaseModel):
    message: str
    user_id: str = "anonymous"
    conv_id: Optional[str] = None


def _services() -> tuple[ModelGateway, AdaptiveRouter, ManagerRuntime]:
    global _gateway, _router, _manager
    if _gateway is None:
        _gateway = ModelGateway()
        _router = AdaptiveRouter(_gateway)
        _manager = ManagerRuntime(_gateway)
    return _gateway, _router, _manager  # type: ignore[return-value]


def _event(kind: str, **data: Any) -> bytes:
    return (json.dumps({"type": kind, **data}, ensure_ascii=False) + "\n").encode()


async def _direct_action(action: str, args: Dict[str, Any]) -> str:
    tool = main_api._tool_manager._tools.get("knowledge_search") if main_api._tool_manager else None
    kb = tool.handler.__self__ if tool else None
    if action == "system_info":
        return "StandardPilot 是面向 3GPP 标准文稿的智能分析工作台，支持文稿入库、知识检索、标准问答、TDoc 摘要、Gap 分析、提案辅助和执行轨迹观测。"
    if action == "knowledge_stats" and kb:
        return f"当前知识库共有 {kb.doc_count} 个文档片段。"
    if action == "document_lookup" and kb:
        rows = kb.search(args["tdoc_id"], top_k=5)
        exact = [row for row in rows if args["tdoc_id"].lower() in (row.get("title", "") + row.get("content", "")).lower()]
        if exact:
            row = exact[0]
            return f"已找到 {args['tdoc_id']}：{row.get('title', '未命名文稿')}\n\n{row.get('content', '')}"
        return f"知识库中未找到明确匹配 {args['tdoc_id']} 的文稿。"
    if action == "meeting_list" and kb:
        data = kb._collection.get(include=["metadatas"])
        meetings = sorted({str(meta.get("meeting")) for meta in (data.get("metadatas") or []) if meta and meta.get("meeting")})
        return "当前会议列表：" + ("、".join(meetings) if meetings else "入库元数据中尚未维护 meeting 字段。")
    if action == "task_status":
        return f"任务 {args.get('task_id')} 尚未接入统一任务状态仓库；当前可在运行轨迹中查询最近请求状态。"
    if action == "ui_action":
        return "请进入“文稿中心”完成导入，或在分析完成后进入报告导出入口。"
    if action == "clarify":
        return args.get("question", "请补充具体任务。")
    raise RuntimeError(f"不支持的直接动作: {action}")


async def _retrieve(message: str, deep: bool) -> tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
    if main_api._tool_manager is None:
        return "", [], {"rounds": 0, "decision": "skip", "reason": "tool_manager_unavailable"}
    with stage("retrieval.round1"):
        first = await main_api._tool_manager.call("knowledge_search", {"query": message, "top_k": 8}, use_cache=True)
    rows = first.data if first.success and isinstance(first.data, list) else []
    top_score = max((float(row.get("score", 0)) for row in rows if isinstance(row, dict)), default=0.0)
    decision = "stop" if len(rows) >= 3 and top_score >= 0.55 else "deepen"
    if decision == "deepen" and deep:
        with stage("retrieval.round2"):
            expanded = await main_api._tool_manager.search_with_rewrite("knowledge_search", message, top_k=8)
        if expanded.success and isinstance(expanded.data, list):
            rows = expanded.data
    evidence = [row for row in rows[:6] if isinstance(row, dict) and row.get("content")]
    context = "\n\n".join(f"[{i+1}] {row.get('title', '')}\n{str(row.get('content', ''))[:800]}" for i, row in enumerate(evidence))
    return context, evidence, {"rounds": 2 if decision == "deepen" and deep else 1, "decision": decision, "top_score": top_score, "candidate_count": len(rows)}


def _agent_for(name: Optional[str]):
    from agents.agent_orchestrator import AgentType
    mapping = {"standard_analyst": AgentType.STANDARD_ANALYST, "tdoc_analyst": AgentType.TDOC_ANALYST, "proposal_writer": AgentType.PROPOSAL_WRITER, "review_defense": AgentType.REVIEW_DEFENSE, "general": AgentType.GENERAL}
    target = mapping.get(name or "general", AgentType.GENERAL)
    return main_api._orchestrator._best_agent(target), target


@router.post("/chat/adaptive/stream")
async def adaptive_chat(body: AdaptiveChatRequest, request: HttpRequest):
    if main_api._orchestrator is None or main_api._memory is None:
        raise HTTPException(503, "服务未就绪")
    gateway, adaptive_router, manager = _services()

    async def generate() -> AsyncIterator[bytes]:
        from agents.agent_orchestrator import Request as OrcRequest
        from memory.conversation_memory import MsgRole
        from api.observability import _trace_store

        capture_token = begin_capture()
        capture_finished = False
        started = time.time()
        trace_id, conv_id = uuid.uuid4().hex, body.conv_id or str(uuid.uuid4())
        trace: Dict[str, Any] = {"trace_id": trace_id, "conv_id": conv_id, "user_id": body.user_id, "question": body.message, "status": "running", "started_at_epoch": started, "spans": [], "decisions": [], "executed_agents": [], "fallback_count": 0}
        response_parts: List[str] = []
        first_token: Optional[float] = None
        yield _event("meta", trace_id=trace_id, conv_id=conv_id)
        try:
            fast = _gate.match(body.message)
            fast_data = {"node": "fast_gate", "matched": fast.matched, "action": fast.action, "reason_code": fast.reason_code}
            trace["fast_gate"] = fast_data
            trace["decisions"].append(fast_data)
            yield _event("decision", **fast_data)
            if fast.matched:
                budget = budget_for(ResponseProfile.BRIEF)
                trace["budget"] = budget.__dict__ | {"profile": budget.profile.value}
                text = await _direct_action(fast.action or "clarify", fast.arguments or {})
                response_parts.append(text)
                first_token = time.time()
                yield _event("first_token", ttft_ms=round((first_token-started)*1000, 1))
                yield _event("delta", content=text)
            else:
                mem = await main_api._memory.get_context(body.user_id, conv_id, query=body.message)
                history = [{"role": item.role.value, "content": item.content} for item in mem.recent_messages[-5:]] if mem.recent_messages else None
                decision = await adaptive_router.decide(body.message, history)
                budget = budget_for(decision.response_profile)
                route_data = {"node": "adaptive_router", **decision.to_dict(), "budget": budget.__dict__ | {"profile": budget.profile.value}}
                trace["route_decision"] = decision.to_dict()
                trace["budget"] = route_data["budget"]
                trace["decisions"].append(route_data)
                yield _event("decision", **route_data)
                if decision.mode == ExecutionMode.CLARIFY:
                    text = decision.clarification_question or "请补充具体文稿、议题或目标。"
                    response_parts.append(text)
                    first_token = time.time()
                    yield _event("first_token", ttft_ms=round((first_token-started)*1000, 1))
                    yield _event("delta", content=text)
                else:
                    context, evidence, retrieval = ("", [], {"rounds": 0, "decision": "skip"})
                    if decision.retrieval_required:
                        context, evidence, retrieval = await _retrieve(body.message, decision.mode == ExecutionMode.MANAGER_AGENT)
                    trace["retrieval"] = retrieval
                    trace["evidence"] = evidence
                    yield _event("retrieval", **retrieval, evidence=evidence)
                    if decision.mode == ExecutionMode.MANAGER_AGENT:
                        workers, outputs = await manager.run_workers(message=body.message, evidence=context, max_tokens=budget.max_tokens)
                        trace["executed_agents"] = workers + ["manager"]
                        yield _event("manager", status="workers_completed", workers=workers, successful_workers=list(outputs))
                        system = "你是研究任务经理。综合专业Worker结果形成统一结论，区分证据、推断与待确认内容。"
                        prompt = manager.synthesis_prompt(body.message, context, outputs)
                        messages = [{"role": "user", "content": prompt}]
                    else:
                        agent, agent_type = _agent_for(decision.specialist if decision.mode == ExecutionMode.SPECIALIST_AGENT else "general")
                        req = OrcRequest(message=body.message, user_id=body.user_id, conv_id=conv_id, context=context, history=history)
                        system = agent._build_system_prompt(req) if agent else "你是通信标准研究助手。"
                        trace["executed_agents"] = [agent_type.value]
                        messages = [{"role": "user", "content": (f"[检索证据]\n{context}\n\n" if context else "") + body.message}]
                    with stage(f"adaptive.generate:{trace['executed_agents'][-1]}"):
                        async for chunk in gateway.stream(messages=messages, system=system, max_tokens=budget.max_tokens, role="generation"):
                            if await request.is_disconnected():
                                raise asyncio.CancelledError()
                            if first_token is None:
                                first_token = time.time()
                                yield _event("first_token", ttft_ms=round((first_token-started)*1000, 1))
                            response_parts.append(chunk)
                            yield _event("delta", content=chunk)
            answer = "".join(response_parts)
            await main_api._memory.add_message(body.user_id, conv_id, MsgRole.USER, body.message)
            await main_api._memory.add_message(body.user_id, conv_id, MsgRole.ASSISTANT, answer)
            calls = finish_capture(capture_token)
            capture_finished = True
            usage = summarize(calls)
            trace["fallback_count"] = sum(1 for call in calls if call.get("status") == "error")
            ended = time.time()
            trace.update({"status": "ok", "response": answer, "llm_calls": calls, **usage, "ttft_ms": round(((first_token or ended)-started)*1000, 1), "e2e_latency_ms": round((ended-started)*1000, 1), "ended_at_epoch": ended})
            store = _trace_store()
            current = await store.get_conversation(body.user_id, conv_id)
            await store.upsert_conversation(body.user_id, conv_id, title=(current or {}).get("title") or body.message[:36], last_message=body.message[:120], message_count=int((current or {}).get("message_count", 0)) + 2, last_trace_id=trace_id)
            await store.save_trace(trace)
            yield _event("done", trace_id=trace_id, conv_id=conv_id, route_decision=trace.get("route_decision"), fast_gate=trace["fast_gate"], executed_agents=trace["executed_agents"], fallback_count=trace["fallback_count"], llm_calls=calls, **usage, ttft_ms=trace["ttft_ms"], e2e_latency_ms=trace["e2e_latency_ms"])
        except asyncio.CancelledError:
            if not capture_finished:
                trace["llm_calls"] = finish_capture(capture_token)
                trace.update(summarize(trace["llm_calls"]))
            trace.update({"status": "cancelled", "ended_at_epoch": time.time()})
            await _trace_store().save_trace(trace)
            raise
        except Exception as exc:
            if not capture_finished:
                trace["llm_calls"] = finish_capture(capture_token)
                trace.update(summarize(trace["llm_calls"]))
            trace.update({"status": "error", "error": str(exc), "ended_at_epoch": time.time()})
            await _trace_store().save_trace(trace)
            yield _event("error", trace_id=trace_id, message=str(exc))

    return StreamingResponse(generate(), media_type="application/x-ndjson", headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})
