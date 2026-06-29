# Soulbot

Soulbot 当前保留前端体验、语音输入输出和实时语音交互通道，后端问答与生活出行能力已切换到从 `~/Desktop/易联智慧_gpt` 迁移来的 Soul companion 能力。

## 当前能力

- 天气查询：高德地图天气接口。
- 动车/高铁查询：12306 公开车次与余票接口。
- 附近美食查询：高德地图 POI 接口。
- 老人友好旅行攻略：组合天气、车次、景点和美食结果，偏向少走路、雨天防滑、打车直达和午休节奏。
- 文本入口：`soul_cli.py`；另保留用户指定的验收脚本入口。
- 前端入口：保留原 Soulmeet Web、聊天输入、语音控制、天气展示、侧栏和实时语音连接。

## 后端结构

- `apps/backend/core/soul_companion/runtime.py`：Soulbot 后端调用 Soul companion 工具的统一入口。
- `plugins/soul-companion/`：从 `~/Desktop/易联智慧_gpt/plugins/elder-companion` 复制并改名后的确定性工具插件。
- `apps/backend/core/conversation/runtime_session.py`：会话、历史、事件、TTS 处理；用户文本直接交给 Soul companion。
- `apps/backend/core/pipeline/factory.py`：实时语音流水线，保留 STT、情绪信号、Soul companion 回复和 TTS。
- `apps/backend/core/api/webrtc.py`：WebRTC 数据通道和语音会话入口。

旧 agent、闲聊、任务调度、技能包、Flow 状态图和独立 task server 后端代码已删除，不再做旧路径兼容。

## 本地验证

```bash
python3 -m compileall -q apps/backend plugins soul_cli.py
pnpm --filter @soulmeet/web typecheck
pnpm build:web
```

另外按用户指定的四条验收脚本命令验证天气、动车、美食和老人友好一日游输出。

## 运行

开发前端：

```bash
pnpm dev:web
```

后端：

```bash
/Users/apapoo/miniforge3/envs/soulbot/bin/python apps/backend/main.py
```

如需高德接口覆盖默认配置，可设置：

```bash
export SOUL_AMAP_API_KEY=你的高德Key
```
