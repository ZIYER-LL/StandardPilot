# StandardPilot

StandardPilot 是一个面向通信标准工程师的标准文稿处理助手，支持标准文档问答、TDoc 摘要、标准化 Gap 分析、提案草稿生成和会议 challenge 准备。

项目保留原有工程骨架与技术栈，基于 FastAPI、Redis、ChromaDB、Prometheus、Nginx、Docker Compose、Agent Router、Skills 和 Eval 构建。

## 核心链路

用户请求
→ 读取记忆上下文
→ 标准任务意图识别
→ 标准文稿知识库检索
→ Agent 路由
→ Skills 注入
→ Agent 生成回答
→ 写入记忆
→ 返回用户

## 保留技术栈

- FastAPI
- Redis
- ChromaDB
- Prometheus
- Nginx
- Docker Compose
- AgentOrchestrator
- IntentRecognizer
- MemoryManager
- KnowledgeBase
- Skills 机制
- Eval 评测框架

## 支持接口

- `/chat`：标准文稿对话入口
- `/knowledge/add`：导入标准文稿
- `/knowledge/upload`：上传标准文稿文件（当前支持 txt/md/json）
- `/knowledge/stats`：查看标准文稿知识库统计
- `/search`：检索标准文稿知识库
- `/eval/run`：运行标准任务评测
- `/monitor`：查看 Agent 监控
- `/metrics`：Prometheus 指标

## Agent 边界

- `StandardAnalystAgent`：负责围绕标准化 topic 做跨文档、跨机制判断，输出已有机制、覆盖范围、潜在 Gap、标准化价值、推进风险与会议 challenge。
- `TDocAnalystAgent`：负责读懂单篇或一组 TDoc，抽取 Background、Problem、Proposed Solution、Impact、Company、Agenda、Meeting、TDoc ID、Open Issues 和 Potential Controversies。
- `ProposalWriterAgent`：负责生成包含 Title、Background、Discussion、Proposal、Conclusion 的 TDoc 草稿。
- `ReviewDefenseAgent`：负责检查 evidence、WG scope、实现问题、新增 NF 风险和会议 challenge。

## 快速启动

```bash
docker compose up --build
```

启动后访问：

- Health: <http://localhost:8000/health>
- Docs: <http://localhost:8000/docs>
- Prometheus metrics: <http://localhost:8000/metrics>
