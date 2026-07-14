# StandardPilot Frontend

Vue 3 + Vite 标准研究工作台，提供标准问答、TDoc 摘要、Gap 分析、Proposal 草稿、会议 Challenge、知识检索和文稿导入界面。

## 推荐启动方式

完整联调统一从仓库根目录启动：

```bash
cp .env.example .env
# Edit ANTHROPIC_API_KEY in .env
docker compose up -d --build
```

前端 Nginx 会将 `/api/python/*` 代理到同一 Docker 网络内的 `backend:8000`，不再使用 `host.docker.internal`，也不需要单独启动前端 Compose。

默认访问：<http://localhost:8080>

## 单独开发前端

后端在本机 `8000` 端口运行时：

```bash
npm ci
npm run dev
```

Vite 会将 `/api/python` 代理到 `http://localhost:8000`。也可以通过环境变量覆盖：

```bash
VITE_API_URL=http://localhost:8000 npm run dev
```

## 生产镜像

`Dockerfile` 使用多阶段构建：Node.js 阶段执行 `npm ci && npm run build`，Nginx 阶段只保留静态产物和反向代理配置。因此不需要提前在宿主机生成 `dist/`。
