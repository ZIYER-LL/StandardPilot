# StandardPilot

StandardPilot 是面向通信标准研究场景的多 Agent 文稿分析系统。仓库使用根目录 `docker-compose.yml` 统一编排前端、FastAPI 后端、Redis、ChromaDB 和 Prometheus。

## 统一架构

```text
Browser
  │
  ▼
frontend (Nginx + Vue)
  ├─ /                  -> Vue SPA
  └─ /api/python/*      -> backend:8000
                              ├─ redis:6379
                              └─ chromadb:8000

prometheus -> backend:8000/metrics
```

容器通过 `standardpilot-network` 使用服务名通信，不再依赖 `host.docker.internal`，也不需要分别进入前后端目录启动两套 Compose。

## 快速启动

```bash
cp .env.example .env
# 编辑 .env，至少设置 ANTHROPIC_API_KEY 和 REDIS_PASSWORD
docker compose up -d --build
```

也可以使用：

```bash
bash docker-deploy.sh up
```

## 访问地址

- 标准研究工作台：<http://localhost:8080>
- 后端 Swagger（仅本机）：<http://127.0.0.1:8000/docs>
- 网关健康检查：<http://localhost:8080/healthz>
- 后端健康检查：<http://localhost:8080/api/python/health>
- Prometheus（仅本机）：<http://127.0.0.1:9090>

云服务器部署时只需对外开放 `APP_PORT`。后端与 Prometheus 默认绑定到 `127.0.0.1`；Redis 和 ChromaDB 不映射宿主机端口。

## 常用命令

```bash
docker compose ps
docker compose logs -f
docker compose logs -f backend
docker compose up -d --build frontend backend
docker compose down
docker compose down -v
```

所有容器日志均启用轮转：单文件最大 10 MB，最多保留 3 个文件。

## 持久化数据

- `standardpilot-redis-data`
- `standardpilot-chromadb-data`
- `standardpilot-prometheus-data`

执行 `docker compose down` 不会删除数据；只有 `docker compose down -v` 才会清除。

## 目录

- `EchoMind/`：FastAPI、Agent、Memory、RAG、Skills、评测与监控
- `EchoMindFrontend/`：Vue 3 标准研究工作台
- `docker-compose.yml`：完整服务编排的唯一入口
- `.env.example`：统一环境变量模板
- `docker-deploy.sh`：部署辅助脚本
