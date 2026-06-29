# Soulbot Deployment

当前部署只保留 Web 前端和 FastAPI 后端。后端文本问答、语音问答和实时语音会话统一调用 `plugins/soul-companion`，不再启动独立任务进程。

## 服务

- `backend`：FastAPI、WebRTC 信令、STT/TTS 流水线、Soul companion 文本能力。
- `web`：Soulmeet Web 前端。
- `redis`、`postgres`：按现有环境配置保留，用于会话、缓存或周边能力。

## 已移除

- 独立 task server。
- 任务调度 IPC。
- 旧智能体、流程图和任务编排后端链路。
- 旧技能包运行时。

## 常用命令

```bash
docker compose -f deploy/docker-compose.dev.yml up --build
docker compose -f deploy/docker-compose.prod.yml up --build -d
```

本地前端构建：

```bash
pnpm build:web
```

后端导入检查：

```bash
PYTHONPATH=apps/backend /Users/apapoo/miniforge3/envs/soulbot/bin/python -c "import main; print(main.app.title)"
```
