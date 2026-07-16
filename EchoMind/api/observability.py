"""Observable chat, conversation management, and trace query APIs."""
from __future__ import annotations

import asyncio
import json
import math
import os
import time
import uuid
from collections import Counter
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request as HttpRequest
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import api.main as main_api
from core.llm_stream import stream_text
from core.llm_telemetry import begin_capture, finish_capture, stage, summarize
from core.trace_store import TraceStore

router = APIRouter(tags=["Observability"])
_store: Optional[TraceStore] = None


class StreamChatRequest(BaseModel):
    message: str
    user_id: str = "anonymous"
    conv_id: Optional[str] = None


def _trace_store() -> TraceStore:
    global _store
    if _store is None:
        _store = TraceStore(os.getenv("REDIS_URL", "redis://redis:6379/0"))
    return _store


def _event(event_type: str, **data: Any) -> bytes:
    return (json.dumps({"type": event_type, **data}, ensure_ascii=False) + "\n").encode("utf-8")


def _percentile(values: List[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return round(ordered[index], 1)


def _span_start(trace: Dict[str, Any], name: str, **attributes: Any) -> Dict[str, Any]:
    span = {
        "span_id": uuid.uuid4().hex[:16],
        "name": name,
        "status": "running",
        "started_at_epoch": time.time(),
        "attributes": attributes,
    }
    trace["spans"].append(span)
    return span


def _span_end(span: Dict[str, Any], status: str = "ok", error: Optional[str] = None, **attributes: Any) -> None:
    ended = time.time()
    span["ended_at_epoch"] = ended
    span["latency_ms"] = round((ended - span["started_at_epoch"]) * 1000, 1)
    span["status"] = status
    span["attributes"].update(attributes)
    if error:
        span["error"] = error


async def _knowledge_context(message: str) -> tuple[str, bool, List[Dict[str, Any]]]:
    if main_api._tool_manager is None or not main_api._should_use_knowledge(message):
        return "", False, []
    result = await main_api._tool_manager.search_with_rewrite("knowledge_search", message, top_k=3)
    if not result.success or not isinstance(result.data, list) or not result.data:
        return "", False, []
    evidence: List[Dict[str, Any]] = []
    parts = ["[知识库检索结果]"]
    for index, item in enumerate(result.data[:3], start=1):
        if not isinstance(item, dict):
            continue
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        evidence.append({
            "title": str(item.get("title", "未命名文档")),
            "score": item.get("score"),
            "chunk": item.get("chunk"),
            "content": content[:800],
        })
        parts.append(
            f"{index}. 标题: {item.get('title', '未命名文档')}\n"
            f"   相关度: {item.get('score', '')}\n"
            f"   内容: {content[:600]}"
        )
    if not evidence:
        return "", False, []
    parts.append("请优先依据以上标准文稿知识库内容回答；如果知识库内容不足，请区分已有证据、合理推断和待确认内容。")
    return "\n".join(parts), True, evidence


async def _stream_agent(agent: Any, orc_req: Any) -> AsyncIterator[str]:
    messages: List[Dict[str, str]] = []
    if orc_req.context:
        messages.append({"role": "user", "content": f"[背景信息]\n{orc_req.context}"})
        messages.append({"role": "assistant", "content": "好的，我已了解背景信息。"})
    messages.append({"role": "user", "content": orc_req.message})
    client = agent._client
    async for token in stream_text(
        api_key=client.api_key,
        base_url=client.base_url,
        model=agent._model,
        messages=messages,
        system=agent._build_system_prompt(orc_req),
        max_tokens=1024,
    ):
        yield token


@router.post("/chat/stream")
async def chat_stream(body: StreamChatRequest, request: HttpRequest):
    if main_api._orchestrator is None or main_api._memory is None:
        raise HTTPException(503, "服务未就绪")

    async def generate() -> AsyncIterator[bytes]:
        from agents.agent_orchestrator import AgentType, Request as OrcRequest
        from memory.conversation_memory import MsgRole

        capture_token = begin_capture()
        capture_finished = False
        started = time.time()
        trace_id = uuid.uuid4().hex
        conv_id = body.conv_id or str(uuid.uuid4())
        trace: Dict[str, Any] = {
            "trace_id": trace_id,
            "request_id": uuid.uuid4().hex[:8],
            "user_id": body.user_id,
            "conv_id": conv_id,
            "question": body.message,
            "status": "running",
            "started_at_epoch": started,
            "spans": [],
            "executed_agents": [],
            "fallback_count": 0,
            "llm_calls": [],
        }
        response_parts: List[str] = []
        first_token_at: Optional[float] = None
        generation_started_at: Optional[float] = None
        selected_agent: Optional[str] = None
        intent_value = "other"
        knowledge_used = False
        evidence: List[Dict[str, Any]] = []

        yield _event("meta", trace_id=trace_id, request_id=trace["request_id"], conv_id=conv_id, started_at_epoch=started)

        try:
            span = _span_start(trace, "memory.read")
            yield _event("stage", span_id=span["span_id"], stage=span["name"], status="running")
            mem_ctx = await main_api._memory.get_context(body.user_id, conv_id, query=body.message)
            history = [
                {"role": message.role.value, "content": message.content}
                for message in mem_ctx.recent_messages[-5:]
            ] if mem_ctx.recent_messages else None
            _span_end(span, history_messages=len(history or []))
            yield _event("stage", span_id=span["span_id"], stage=span["name"], status="completed", latency_ms=span["latency_ms"])

            span = _span_start(trace, "rag.retrieve")
            yield _event("stage", span_id=span["span_id"], stage=span["name"], status="running")
            with stage("rag.retrieve"):
                knowledge_text, knowledge_used, evidence = await _knowledge_context(body.message)
            _span_end(span, knowledge_used=knowledge_used, retrieved_chunks=len(evidence))
            yield _event(
                "stage",
                span_id=span["span_id"],
                stage=span["name"],
                status="completed",
                latency_ms=span["latency_ms"],
                knowledge_used=knowledge_used,
                evidence=evidence,
            )

            context_parts = [mem_ctx.to_prompt_text()]
            if knowledge_text:
                context_parts.append(knowledge_text)
            orc_req = OrcRequest(
                message=body.message,
                user_id=body.user_id,
                conv_id=conv_id,
                context="\n\n".join(part for part in context_parts if part),
                history=history,
                request_id=trace["request_id"],
            )

            span = _span_start(trace, "intent.recognize")
            yield _event("stage", span_id=span["span_id"], stage=span["name"], status="running")
            with stage("intent.recognize"):
                intent_result = await main_api._orchestrator._intent_recognizer.recognize(body.message, history=history)
            orc_req.intent = intent_result.intent
            orc_req.urgency = intent_result.urgency
            intent_value = intent_result.intent.value if intent_result.intent else "other"
            _span_end(span, intent=intent_value, urgency=intent_result.urgency.value if intent_result.urgency else None)
            yield _event("stage", span_id=span["span_id"], stage=span["name"], status="completed", latency_ms=span["latency_ms"], intent=intent_value)

            span = _span_start(trace, "agent.route")
            collaboration = main_api._orchestrator._collaboration_targets(orc_req)
            agent_type = collaboration[0] if collaboration else main_api._orchestrator._route(orc_req.intent, orc_req.urgency)
            agent = main_api._orchestrator._best_agent(agent_type)
            if agent is None:
                agent_type = AgentType.GENERAL
                agent = main_api._orchestrator._best_agent(agent_type)
                trace["fallback_count"] += 1
            if agent is None:
                raise RuntimeError("没有可用 Agent")
            selected_agent = agent_type.value
            trace["selected_agent"] = selected_agent
            trace["planned_agents"] = [item.value for item in collaboration] or [selected_agent]
            _span_end(span, selected_agent=selected_agent, planned_agents=trace["planned_agents"])
            yield _event("route", span_id=span["span_id"], intent=intent_value, selected_agent=selected_agent, planned_agents=trace["planned_agents"], latency_ms=span["latency_ms"])

            async def run_selected(current_agent: Any, current_type: Any) -> AsyncIterator[bytes]:
                nonlocal first_token_at, generation_started_at
                agent_span = _span_start(trace, "agent.generate", agent=current_type.value, model=current_agent._model)
                trace["executed_agents"].append(current_type.value)
                current_agent.stats.total += 1
                generation_started_at = time.time()
                yield _event("agent", span_id=agent_span["span_id"], agent=current_type.value, status="running")
                success = False
                before_chars = len("".join(response_parts))
                try:
                    with stage(f"agent.generate:{current_type.value}"):
                        async for token in _stream_agent(current_agent, orc_req):
                            if await request.is_disconnected():
                                raise asyncio.CancelledError()
                            if first_token_at is None:
                                first_token_at = time.time()
                                trace["ttft_ms"] = round((first_token_at - started) * 1000, 1)
                                yield _event("first_token", ttft_ms=trace["ttft_ms"], agent=current_type.value)
                            response_parts.append(token)
                            yield _event("delta", content=token)
                    success = len("".join(response_parts)) > before_chars
                    if not success:
                        raise RuntimeError("模型流未返回文本")
                    current_agent.stats.success += 1
                finally:
                    elapsed = (time.time() - generation_started_at) * 1000
                    current_agent.stats.total_ms += elapsed
                    _span_end(agent_span, "ok" if success else "error", output_chars=len("".join(response_parts)) - before_chars)
                    yield _event("agent", span_id=agent_span["span_id"], agent=current_type.value, status="completed" if success else "failed", latency_ms=agent_span["latency_ms"])

            try:
                async for event in run_selected(agent, agent_type):
                    yield event
            except Exception as primary_error:
                if agent_type == AgentType.GENERAL or response_parts:
                    raise
                trace["fallback_count"] += 1
                fallback = main_api._orchestrator._best_agent(AgentType.GENERAL)
                if fallback is None:
                    raise
                yield _event("fallback", from_agent=agent_type.value, to_agent=AgentType.GENERAL.value, reason=str(primary_error))
                async for event in run_selected(fallback, AgentType.GENERAL):
                    yield event
                selected_agent = AgentType.GENERAL.value
                trace["selected_agent"] = selected_agent

            response_text = "".join(response_parts)
            span = _span_start(trace, "memory.write")
            await main_api._memory.add_message(body.user_id, conv_id, MsgRole.USER, body.message)
            await main_api._memory.add_message(body.user_id, conv_id, MsgRole.ASSISTANT, response_text)
            _span_end(span, messages_written=2)
            yield _event("stage", span_id=span["span_id"], stage=span["name"], status="completed", latency_ms=span["latency_ms"])

            llm_calls = finish_capture(capture_token)
            capture_finished = True
            usage = summarize(llm_calls)
            ended = time.time()
            trace.update({
                "status": "ok",
                "response": response_text,
                "intent": intent_value,
                "knowledge_used": knowledge_used,
                "evidence": evidence,
                "llm_calls": llm_calls,
                **usage,
                "ended_at_epoch": ended,
                "e2e_latency_ms": round((ended - started) * 1000, 1),
                "generation_ms": round((ended - (first_token_at or generation_started_at or ended)) * 1000, 1),
            })
            conversation = await _trace_store().get_conversation(body.user_id, conv_id)
            message_count = int((conversation or {}).get("message_count", 0)) + 2
            await _trace_store().upsert_conversation(
                body.user_id,
                conv_id,
                title=(conversation or {}).get("title") or body.message[:36],
                last_message=body.message[:120],
                message_count=message_count,
                last_trace_id=trace_id,
            )
            await _trace_store().save_trace(trace)
            asyncio.create_task(main_api._memory.update_profile(body.user_id, conv_id))
            yield _event(
                "done",
                trace_id=trace_id,
                conv_id=conv_id,
                intent=intent_value,
                agent_type=selected_agent,
                executed_agents=trace["executed_agents"],
                knowledge_used=knowledge_used,
                fallback_count=trace["fallback_count"],
                llm_calls=llm_calls,
                **usage,
                ttft_ms=trace.get("ttft_ms"),
                generation_ms=trace["generation_ms"],
                e2e_latency_ms=trace["e2e_latency_ms"],
            )
        except asyncio.CancelledError:
            if not capture_finished:
                trace["llm_calls"] = finish_capture(capture_token)
                trace.update(summarize(trace["llm_calls"]))
            trace["status"] = "cancelled"
            trace["ended_at_epoch"] = time.time()
            trace["e2e_latency_ms"] = round((trace["ended_at_epoch"] - started) * 1000, 1)
            await _trace_store().save_trace(trace)
            raise
        except Exception as error:
            if not capture_finished:
                trace["llm_calls"] = finish_capture(capture_token)
                trace.update(summarize(trace["llm_calls"]))
            trace["status"] = "error"
            trace["error"] = str(error)
            trace["ended_at_epoch"] = time.time()
            trace["e2e_latency_ms"] = round((trace["ended_at_epoch"] - started) * 1000, 1)
            await _trace_store().save_trace(trace)
            yield _event("error", trace_id=trace_id, message=str(error))

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@router.get("/conversations")
async def list_conversations(user_id: str = "anonymous", limit: int = 50):
    return {"conversations": await _trace_store().list_conversations(user_id, limit)}


@router.get("/conversations/{conv_id}")
async def get_conversation(conv_id: str, user_id: str = "anonymous"):
    conversation = await _trace_store().get_conversation(user_id, conv_id)
    traces = await _trace_store().list_traces(limit=100, user_id=user_id, conv_id=conv_id)
    if conversation is None and not traces:
        raise HTTPException(404, "会话不存在")
    ordered = sorted(traces, key=lambda item: item.get("started_at_epoch", 0))
    messages: List[Dict[str, Any]] = []
    for trace in ordered:
        messages.append({"role": "user", "content": trace.get("question", ""), "trace_id": trace.get("trace_id")})
        if trace.get("response"):
            messages.append({
                "role": "assistant",
                "content": trace["response"],
                "trace_id": trace.get("trace_id"),
                "meta": {
                    "intent": trace.get("intent"),
                    "agent_type": trace.get("selected_agent"),
                    "ttft_ms": trace.get("ttft_ms"),
                    "e2e_latency_ms": trace.get("e2e_latency_ms"),
                },
            })
    return {"conversation": conversation, "messages": messages, "traces": ordered}


@router.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: str, user_id: str = "anonymous"):
    return {"deleted": await _trace_store().delete_conversation(user_id, conv_id)}


@router.get("/traces")
async def list_traces(limit: int = 50, user_id: Optional[str] = None, conv_id: Optional[str] = None):
    return {"traces": await _trace_store().list_traces(limit=limit, user_id=user_id, conv_id=conv_id)}


@router.get("/traces/{trace_id}")
async def get_trace(trace_id: str):
    trace = await _trace_store().get_trace(trace_id)
    if trace is None:
        raise HTTPException(404, "Trace 不存在")
    return trace


@router.get("/observability/summary")
async def observability_summary(limit: int = 100):
    traces = await _trace_store().list_traces(limit=max(1, min(limit, 500)))
    completed = [trace for trace in traces if trace.get("status") in {"ok", "error"}]
    ttft = [float(trace["ttft_ms"]) for trace in completed if trace.get("ttft_ms") is not None]
    e2e = [float(trace["e2e_latency_ms"]) for trace in completed if trace.get("e2e_latency_ms") is not None]
    agent_counts = Counter(trace.get("selected_agent", "unknown") for trace in completed)
    success_count = sum(1 for trace in completed if trace.get("status") == "ok")
    fallback_count = sum(1 for trace in completed if int(trace.get("fallback_count", 0)) > 0)
    return {
        "sample_size": len(completed),
        "success_rate": round(success_count / len(completed), 4) if completed else 0.0,
        "fallback_rate": round(fallback_count / len(completed), 4) if completed else 0.0,
        "total_llm_calls": sum(int(trace.get("llm_call_count", 0)) for trace in completed),
        "total_input_tokens": sum(int(trace.get("input_tokens", 0)) for trace in completed),
        "total_output_tokens": sum(int(trace.get("output_tokens", 0)) for trace in completed),
        "ttft_ms": {"avg": round(sum(ttft) / len(ttft), 1) if ttft else 0.0, "p50": _percentile(ttft, 0.50), "p95": _percentile(ttft, 0.95)},
        "e2e_latency_ms": {"avg": round(sum(e2e) / len(e2e), 1) if e2e else 0.0, "p50": _percentile(e2e, 0.50), "p95": _percentile(e2e, 0.95)},
        "agent_counts": dict(agent_counts),
        "recent_traces": traces[:20],
    }
