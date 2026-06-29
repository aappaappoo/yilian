# Soulbot 部署到 Railway 和 Vercel

本文只记录生产部署需要的控制台配置，不提交任何真实密钥。

## 后端发布到 Railway

1. 在 Railway 新建项目，选择从 GitHub 仓库部署。
2. 选择 `aappaappoo/Soulbot` 仓库。
3. 后端服务设置：
   - Root Directory: `apps/backend`
   - Config File Path: `/apps/backend/railway.json`
   - Builder: Dockerfile
   - Healthcheck Path: `/health`
4. Railway 后端环境变量至少配置：

```env
HOST=0.0.0.0
DASHSCOPE_API_KEY=你的 DashScope Key
DEEPSEEK_API_KEY=你的 DeepSeek Key
SOUL_AGENT_PROVIDER=deepseek
SOUL_AGENT_MODEL=deepseek-v4-flash
SOUL_AGENT_ENABLED=true
JWT_SECRET_KEY=换成强随机字符串
ADMIN_USERNAME=你的后台账号
ADMIN_PASSWORD=你的后台密码
CORS_ORIGINS=https://soulmeet.space,https://www.soulmeet.space
```

如果要保留登录、对话历史、记忆等持久化能力，还需要在 Railway 添加 PostgreSQL，并设置：

```env
CONTEXT_SQL_URL=postgresql+asyncpg://user:password@host:5432/database
```

如果启用实时语音，还需要补齐 LiveKit 相关变量：

```env
LIVEKIT_URL=wss://你的-livekit-地址
LIVEKIT_API_KEY=你的 LiveKit Key
LIVEKIT_API_SECRET=你的 LiveKit Secret
```

部署成功后，先用 Railway 自动生成的域名验证：

```bash
curl https://你的后端域名/health
```

正确结果应为：

```json
{"ok":true}
```

## 后端自定义域名

如果希望使用 `https://api.soulmeet.space`：

1. 在 Railway 后端服务的 Networking / Domains 中添加 `api.soulmeet.space`。
2. 按 Railway 给出的 DNS 记录去域名服务商添加记录。
3. 等 DNS 生效后验证：

```bash
curl https://api.soulmeet.space/health
```

注意：后端健康检查是 `/health`，不是 `/api/health`。

## 前端发布到 Vercel

1. 在 Vercel 新建项目，选择同一个 GitHub 仓库。
2. 前端项目设置：
   - Root Directory: 仓库根目录
   - Install Command: `pnpm install --frozen-lockfile`
   - Build Command: `pnpm build:web`
   - Output Directory: `apps/web/dist`
3. Vercel 环境变量至少配置：

```env
VITE_BACKEND_ORIGIN=https://api.soulmeet.space
VITE_VOICE_TRANSPORT=livekit
```

如果暂时没有配置后端自定义域名，就先把 `VITE_BACKEND_ORIGIN` 设置为 Railway 自动生成的后端域名。

Vite 会在构建时写入 `VITE_BACKEND_ORIGIN`，所以修改 Vercel 环境变量后必须重新部署一次前端。

## 当前线上错误的原因

`https://api.soulmeet.space/api/health` 返回 Vercel 的 `DEPLOYMENT_NOT_FOUND`，说明 `api.soulmeet.space` 当前还没有绑定到 Railway 后端。

前端代码会通过 `VITE_BACKEND_ORIGIN` 拼接后端地址。如果 Vercel 没有设置这个变量，浏览器会请求 `https://soulmeet.space/api/...`，然后被 Vercel 的前端站点接管，导致接口看起来像没有生效。
