"""Bounded manager-worker runtime for compound research tasks."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from core.llm_telemetry import stage
from core.model_gateway import ModelGateway


@dataclass(frozen=True)
class WorkerSpec:
    name: str
    system: str


class ManagerRuntime:
    def __init__(self, gateway: ModelGateway) -> None:
        self.gateway = gateway

    def select_workers(self, message: str) -> List[WorkerSpec]:
        text = message.lower()
        candidates: List[WorkerSpec] = []
        if any(key in text for key in ("tdoc", "文稿", "总结", "摘要")):
            candidates.append(WorkerSpec("tdoc_analyst", "你是TDoc文稿分析专家。提取背景、问题、方案、影响实体、开放问题；缺失信息标记待确认。"))
        if any(key in text for key in ("gap", "标准化", "是否覆盖", "实现问题", "价值")):
            candidates.append(WorkerSpec("standard_analyst", "你是3GPP标准化Gap分析专家。区分已有机制、覆盖边界、潜在Gap、标准化价值和风险。"))
        if any(key in text for key in ("公司", "立场", "比较", "观点")):
            candidates.append(WorkerSpec("position_analyst", "你是公司观点分析专家。仅依据证据比较不同公司立场、共识、分歧和未确认内容。"))
        if any(key in text for key in ("challenge", "质疑", "评审", "攻防")):
            candidates.append(WorkerSpec("review_defense", "你是标准会议评审专家。识别scope、实现问题、信令开销、证据不足等challenge并给出回应建议。"))
        if any(key in text for key in ("proposal", "提案", "草稿", "建议")):
            candidates.append(WorkerSpec("proposal_advisor", "你是标准提案顾问。给出Background、Discussion、Proposal、Conclusion层面的建议，但不编造条款。"))
        if not candidates:
            candidates = [
                WorkerSpec("standard_analyst", "你是通信标准分析专家。分析已有机制、证据边界和待确认问题。"),
                WorkerSpec("review_defense", "你是标准会议评审专家。识别潜在challenge和风险。"),
            ]
        deduped = {item.name: item for item in candidates}
        return list(deduped.values())[:2]

    async def run_workers(self, *, message: str, evidence: str, max_tokens: int) -> Tuple[List[str], Dict[str, str]]:
        workers = self.select_workers(message)

        async def run(worker: WorkerSpec) -> tuple[str, str]:
            prompt = (f"[检索证据]\n{evidence}\n\n" if evidence else "") + f"[用户任务]\n{message}"
            with stage(f"manager.worker:{worker.name}"):
                text = await self.gateway.complete(
                    messages=[{"role": "user", "content": prompt}],
                    system=worker.system,
                    max_tokens=max(384, min(max_tokens, 900)),
                    temperature=0.1,
                    role="worker",
                )
            return worker.name, text

        results = await asyncio.gather(*(run(worker) for worker in workers), return_exceptions=True)
        outputs: Dict[str, str] = {}
        for result in results:
            if isinstance(result, tuple):
                outputs[result[0]] = result[1]
        return [worker.name for worker in workers], outputs

    def synthesis_prompt(self, message: str, evidence: str, outputs: Dict[str, str]) -> str:
        worker_text = "\n\n".join(f"[{name}]\n{text}" for name, text in outputs.items())
        return (
            f"[用户任务]\n{message}\n\n"
            f"[检索证据]\n{evidence or '无'}\n\n"
            f"[专业Worker结果]\n{worker_text or '无可用Worker结果'}\n\n"
            "请综合给出最终答案。避免机械拼接，区分已有证据、合理推断和待确认内容。"
        )
