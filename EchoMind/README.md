# StandardPilot Backend

StandardPilot 后端是面向通信标准研究的 FastAPI 多 Agent 服务，包含意图识别、Agent 路由、Skills 注入、Redis 工作记忆、ChromaDB 情景记忆与 RAG、评测和 Prometheus 指标。

## 核心链路

```text
用户请求
→ 读取记忆上下文
→ 标准任务意图识别
→ 标准文稿知识库检索
→ Agent 路由
→ Skills 注入
→ Agent 生成回答
→ 写入记忆
→ 返回用户
```

## 支持接口

- `/chat`：标准文稿对话入口
- `/knowledge/add`：导入标准文稿
- `/knowledge/upload`：上传 txt、md、json 文稿
- `/knowledge/stats`：知识库统计
- `/search`：知识库检索
- `/eval/run`：标准任务评测
- `/monitor`：Agent 监控
- `/metrics`：Prometheus 指标
- `/health`：健康检查

## 容器化运行

请从仓库根目录使用统一 Compose：

```bash
cp .env.example .env
docker compose up -d --build
```

统一编排会自动注入 Redis、ChromaDB、Skills 和评测路径配置。后端不再单独维护 Compose，也不需要额外的后端 Nginx；浏览器请求由前端 Nginx 通过 `/api/python/*` 转发到 `backend:8000`。

默认 Swagger 调试地址：<http://127.0.0.1:8000/docs>
