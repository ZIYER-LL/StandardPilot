"""
RAG 知识库 —— 基于 ChromaDB 的真实检索实现。

功能：
  1. 文档导入：将文本切片后存入 ChromaDB（自动生成 Embedding）
  2. 语义检索：根据 query 从知识库中检索最相关的文档片段
  3. 与 MCP 工具框架集成：作为 knowledge_search 工具的真实 handler

ChromaDB 在这里的角色：
  - memory/ 中用于存储对话记忆（情景记忆 + 用户画像）
  - 这里用于存储知识库文档（RAG 检索）
  两者是不同的 collection，互不干扰。
"""
import hashlib
import logging
from typing import Any, Dict, List, Optional

import chromadb

logger = logging.getLogger(__name__)


class KnowledgeBase:
    """
    基于 ChromaDB 的 RAG 知识库。

    ChromaDB 内置了 Embedding 模型（all-MiniLM-L6-v2），
    调用 add() 时自动生成向量，query() 时自动做语义匹配。
    不需要额外调用 Anthropic Embeddings API。
    """

    COLLECTION_NAME = "knowledge_base"

    def __init__(
        self,
        chroma_host: str = "localhost",
        chroma_port: int = 8000,
        chroma_path: str = "./data/chroma",
    ):
        # 优先连接独立 ChromaDB 服务（服务端内置 embedding 模型，客户端无需下载）
        self._use_server = False
        try:
            # HttpClient 默认也会初始化 ChromaDB telemetry；显式关闭避免 posthog 兼容性错误日志。
            self._client = chromadb.HttpClient(
                host=chroma_host,
                port=chroma_port,
                settings=chromadb.Settings(anonymized_telemetry=False),
            )
            self._client.heartbeat()
            self._use_server = True
            logger.info(f"知识库 ChromaDB 已连接: {chroma_host}:{chroma_port}")
        except Exception:
            logger.info(f"知识库 ChromaDB 服务不可用，使用本地模式: {chroma_path}")
            self._client = chromadb.PersistentClient(
                path=chroma_path,
                settings=chromadb.Settings(anonymized_telemetry=False),
            )

        # 使用服务端时不传 embedding_function，让服务端处理
        # 本地模式时也不传，使用 ChromaDB 默认的（会触发模型下载）
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"description": "StandardPilot 标准文稿 RAG 知识库"},
        )

        # 如果知识库为空，导入默认文档
        if self._collection.count() == 0:
            self._load_default_docs()

    # ── 文档管理 ──────────────────────────────────────────────────────────────

    def add_documents(self, documents: List[Dict[str, str]]) -> int:
        """
        批量导入文档到知识库。

        documents 格式: [{"title": "...", "content": "..."}, ...]
        长文档会自动切片（每片 500 字）。
        """
        ids, docs, metas = [], [], []

        for doc in documents:
            title   = doc.get("title", "")
            content = doc.get("content", "")
            chunks  = self._chunk_text(content, chunk_size=500)

            for i, chunk in enumerate(chunks):
                doc_id = hashlib.md5(f"{title}_{i}_{chunk[:50]}".encode()).hexdigest()
                ids.append(doc_id)
                docs.append(chunk)
                metas.append({"title": title, "chunk_index": i, "total_chunks": len(chunks)})

        if ids:
            # ChromaDB 会自动生成 Embedding
            self._collection.add(ids=ids, documents=docs, metadatas=metas)
            logger.info(f"知识库导入 {len(ids)} 个文档片段")

        return len(ids)

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        语义检索：根据 query 返回最相关的文档片段。

        ChromaDB 内部自动将 query 转为向量，与存储的文档向量做余弦相似度匹配。
        """
        results = self._collection.query(
            query_texts=[query],
            n_results=top_k,
        )

        items = []
        if results["documents"] and results["documents"][0]:
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ):
                items.append({
                    "title":    meta.get("title", ""),
                    "content":  doc,
                    "score":    round(1.0 - dist, 4),  # ChromaDB 返回距离，转为相似度
                    "chunk":    meta.get("chunk_index", 0),
                })

        return items

    @property
    def doc_count(self) -> int:
        return self._collection.count()

    # ── MCP 工具 handler ─────────────────────────────────────────────────────

    async def search_handler(self, params: Dict[str, Any], context: Any) -> List[Dict]:
        """
        作为 MCP 工具的 handler 注册。

        MCPToolManager.register(Tool(
            name="knowledge_search",
            handler=kb.search_handler,
            ...
        ))
        """
        query = params.get("query", "")
        top_k = params.get("top_k", 5)
        return self.search(query, top_k=top_k)

    # ── 内部方法 ──────────────────────────────────────────────────────────────

    def _chunk_text(self, text: str, chunk_size: int = 500) -> List[str]:
        """将长文本按 chunk_size 切片，保留语义完整性（按句号/换行切分）。"""
        if len(text) <= chunk_size:
            return [text] if text.strip() else []

        chunks = []
        current = ""
        # 按句子切分
        sentences = text.replace("\n", "。").split("。")
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            if len(current) + len(sent) + 1 > chunk_size:
                if current:
                    chunks.append(current)
                current = sent
            else:
                current = f"{current}。{sent}" if current else sent

        if current:
            chunks.append(current)

        return chunks

    def _load_default_docs(self) -> None:
        """导入默认知识库文档（通信标准文稿处理场景）。"""
        default_docs = [
            {
                "title": "3GPP SA2 标准提案流程说明",
                "content": (
                    "SA2 主要讨论系统架构和业务流程。TDoc 通常包含 Background、Discussion、Proposal、Conclusion。"
                    "一个标准提案需要说明问题背景、现有机制、标准化必要性、架构影响和协议影响。"
                    "会议讨论中常见问题包括：是否属于实现问题、是否已有机制覆盖、是否需要新增网元、是否超出 WG scope。"
                ),
            },
            {
                "title": "5GC 相关机制示例",
                "content": (
                    "5GC 中 AMF 负责接入与移动性管理，SMF 负责会话管理，PCF 负责策略控制，"
                    "NWDAF 负责网络数据分析，NEF 负责能力开放，UPF 负责用户面转发。"
                    "QoS Flow、Policy Control、PDU Session Modification、Analytics Exposure 等机制常用于分析新业务需求是否已有标准支持。"
                ),
            },
            {
                "title": "AI Service in 5GC 研究背景",
                "content": (
                    "AI 推理服务可能涉及 UE、边缘节点、核心网策略、服务连续性、执行位置选择、服务实例可用性和能力暴露。"
                    "标准化分析时需要判断：现有 QoS 和 Policy 是否足够，NWDAF 是否能提供相关分析，"
                    "是否需要新增信息元素，是否需要改变现有过程。"
                ),
            },
            {
                "title": "标准提案常见 Challenge",
                "content": (
                    "标准会议中常见 challenge 包括：该问题是否只是实现问题；现有 QoS、Policy Control、NWDAF 是否已经足够；"
                    "是否需要新增 NF；是否增加 UE 影响；是否增加信令开销；是否超出 SA2 scope；"
                    "是否缺少运营商需求支撑；Candidate Spec Text 是否过强。"
                ),
            },
            {
                "title": "TDoc 草稿写作规范",
                "content": (
                    "TDoc 草稿应包含 Title、Background、Discussion、Proposal、Conclusion。Background 说明问题来源，"
                    "Discussion 分析已有机制与不足，Proposal 给出具体建议，Conclusion 总结期望会议讨论结果。"
                    "研究早期应避免过强规范语气，不要轻易使用 shall。"
                ),
            },
            {
                "title": "TDoc 文稿分析字段说明",
                "content": (
                    "分析单篇 TDoc 时应重点提取 Background、Problem、Proposed Solution、Impacted Entities、"
                    "Impacted Procedures、Company、Agenda、Meeting、TDoc ID、Open Issues 和 Potential Controversies。"
                    "缺失字段应标记未知，不要补写不存在的信息。"
                ),
            },
        ]
        self.add_documents(default_docs)
        logger.info(f"已导入默认知识库: {len(default_docs)} 篇文档")
