"""
Soulmeet 应用入口

启动流程:
1. 解析命令行参数 / 环境变量 → 确定 AUDIENCE
2. 初始化前端、语音、记忆和 Soul runtime 所需组件
3. 创建 SessionContext 工厂函数
4. 注册 API 路由 + 静态前端
5. 启动 FastAPI (uvicorn)
"""

from __future__ import annotations
import os
from pathlib import Path
import sys
from datetime import datetime
from typing import Any, Optional
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core.config import settings
from core.conversation.models import init_db
from core.conversation.store import InMemoryStore
from core.conversation.history import HistoryManager
from core.emotion.signal_detector import SignalDetector
from core.tools.registry import ToolRegistry
from core.tools.primitives.http_fetch import HttpFetch
from core.tools.primitives.timer import TimerManager
from core.tools.primitives.kv_store import SQLiteKVStore
from core.api.webrtc import router as webrtc_router
from core.api.session import router as session_router
from core.api.audiences import router as audiences_router
from core.api.auth import router as auth_router, set_session_factory as auth_set_session_factory
from core.api.conversations import router as conversations_router, set_sql_store as conversations_set_sql_store
from core.api.voice_clone import router as voice_clone_router
from core.api.text_runtime import router as text_runtime_router, set_sql_store as text_runtime_set_sql_store
from core.api.weather import router as weather_router
from core.api.speech import router as speech_router
from core.api.quick_actions import router as quick_actions_router
from core.api.webrtc import set_sql_store as webrtc_set_sql_store
from core.auth.service import init_admin
from loguru import logger as loguru_logger
from core.llm_trace import record_llm_request, record_llm_response
from core.logging_utils import STARTUP, log_filter
from core.conversation.sql_store import SQLStore
from core.conversation.context_manager import AsyncContextManager
from core.conversation.runtime_session import SessionContext, conversation_session_manager
from core.conversation.file_store import MemoryFileStore
from core.conversation.embedding_service import EmbeddingService
from core.tools.memory import SaveEventTool, CompressSummaryTool
import logging
import httpx

try:
    import sentry_sdk
except ImportError:  # pragma: no cover - Sentry is optional for local setups.
    sentry_sdk = None

# ═══════════════════════════════════════════════════════════════
#  日志配置 (loguru)
# ═══════════════════════════════════════════════════════════════

sentry_dsn = os.environ.get("SENTRY_DSN", "").strip()


def _drop_noisy_sentry_events(event: dict[str, Any], hint: dict[str, Any]) -> Optional[dict[str, Any]]:
    """过滤第三方语音 SDK 的已知非业务故障噪声。"""
    fragments: list[str] = []

    message = event.get("message")
    if message:
        fragments.append(str(message))

    logentry = event.get("logentry")
    if isinstance(logentry, dict):
        formatted = logentry.get("formatted")
        if formatted:
            fragments.append(str(formatted))
        params = logentry.get("params")
        if params:
            fragments.append(str(params))

    exception = event.get("exception")
    if isinstance(exception, dict):
        for value in exception.get("values") or []:
            if isinstance(value, dict):
                fragments.append(str(value.get("type", "")))
                fragments.append(str(value.get("value", "")))

    for item in event.get("breadcrumbs", {}).get("values", []) if isinstance(event.get("breadcrumbs"), dict) else []:
        if isinstance(item, dict):
            fragments.append(str(item.get("message", "")))

    text = "\n".join(fragments).lower()
    if (
        ("websocket closed" in text and ("opcode=8" in text or "goodbye" in text))
        or "fin=1 opcode=8" in text
        or "no_valid_audio_error" in text
    ):
        return None
    return event


if sentry_sdk is not None and sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        environment=os.environ.get("SENTRY_ENVIRONMENT", os.environ.get("ENVIRONMENT", "production")),
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        send_default_pii=False,
        before_send=_drop_noisy_sentry_events,
    )

# 1. 创建 log 目录
LOG_DIR = Path(os.environ.get("LOG_DIR", "log"))
LOG_DIR.mkdir(exist_ok=True)

# 2. 移除 loguru 默认 handler（避免控制台重复输出）
loguru_logger.remove()

# 3. 统一日志格式（控制台 + 文件保持一致，兼容 bind 的 extra 字段）
_LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}"

# 重新添加控制台输出（保持原有行为 + 日志类别过滤）
_SUPPRESSED_WARNINGS = [
    "No audio frame received within the specified time",
    "No video transceiver is available",
    "No screen video transceiver is available",
    "Timeout establishing the connection to the remote peer",
    "Received an unexpected media stream error while reading the audio"
]


def _console_filter(record: dict) -> bool:
    """控制台过滤：抑制指定 WARNING + 日志类别过滤"""
    if (record["level"].name == "WARNING"
            and any(msg in record["message"] for msg in _SUPPRESSED_WARNINGS)):
        return False
    return log_filter(record)


loguru_logger.add(
    sys.stderr,
    format=_LOG_FORMAT,
    filter=_console_filter,
)

# 4. 添加文件输出：按 YYYYMMDDHHmm 格式命名
log_filename = datetime.now().strftime("%Y%m%d%H%M") + ".log"
loguru_logger.add(
    LOG_DIR / log_filename,
    format=_LOG_FORMAT,
    level="DEBUG",
    encoding="utf-8",
    enqueue=True,
    filter=log_filter,
)

# loguru_logger.disable("pipecat.transports.smallwebrtc")
#  标准 logging 配置（保持原有）
logger = logging.getLogger("soulmeet")
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("pipecat.transports.smallwebrtc.transport").setLevel(logging.ERROR)
logging.getLogger("pipecat.transports.smallwebrtc.connection").setLevel(logging.ERROR)
logging.getLogger("pipecat.services.stt_service").setLevel(logging.ERROR)

loguru_logger.disable("pipecat")  # 覆盖 pipecat.* 所有子模块
logging.getLogger("pipecat").setLevel(logging.CRITICAL)
loguru_logger.disable("pipecat_flows")  # pipecat_flows 是独立包名，需单独 disable
logging.getLogger("pipecat_flows").setLevel(logging.CRITICAL)

#  全局单例（底座组件，所有会话共享）
store = InMemoryStore()

history_manager = HistoryManager(store)
signal_detector = SignalDetector()
http_fetch = HttpFetch()
timer_manager = TimerManager()
kv_store = SQLiteKVStore(os.getenv("SOULMEET_KV_SQLITE_PATH", str(Path("data") / "soulmeet_kv.sqlite3")))
tool_registry = ToolRegistry()
sql_store: Optional[SQLStore] = None  # 全局声明
context_manager: Optional[AsyncContextManager] = None  # 全局声明

# Soul companion runtime does not use the legacy task bridge.
result_handler = None


#  SessionContext 工厂函数
def create_session_context(audience: str, session_id: str) -> SessionContext:
    """
    创建 SessionContext 实例（每个 WebRTC 会话调用一次）。

    使用全局共享的底座组件实例，按 audience + session_id 隔离数据。

    Args:
        audience:   人群标识 ("elder" / "child" / "soul")
        session_id: 会话唯一 ID

    Returns:
        SessionContext: 绑定到该会话的上下文实例
    """
    # debug 调试
    fixed_speaker_id = ""
    return SessionContext(
        audience=audience,
        session_id=session_id,
        store=store,
        history_manager=history_manager,
        signal_detector=signal_detector,
        tool_registry=tool_registry,
        http_fetch=http_fetch,
        timer_manager=timer_manager,
        kv_store=kv_store,
        context_manager=context_manager,
        speaker_id=fixed_speaker_id,
        task_packer=None,
        zmq_client=None,
    )


conversation_session_manager.configure(
    session_factory=create_session_context,
    result_handler=result_handler,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理: 启动初始化和关闭清理"""
    global sql_store, context_manager

    # 初始化 PostgreSQL
    if settings.context_sql_url:
        session_factory = await init_db(
            db_url=settings.context_sql_url,
            pool_size=settings.sql_pool_size,
            max_overflow=settings.sql_max_overflow,
            pool_recycle=settings.sql_pool_recycle,
        )
        sql_store = SQLStore(session_factory)
        text_runtime_set_sql_store(sql_store)
        conversations_set_sql_store(sql_store)
        webrtc_set_sql_store(sql_store)
        logger.info(f"[{STARTUP}] | Task=PostgreSQL引擎初始化 | PostgreSQL SQLStore 初始化完成")
        # 注入 session_factory 到认证模块
        auth_set_session_factory(session_factory)
        # 初始化管理员账号（首次启动时自动创建）
        await init_admin(session_factory)

    else:
        logger.warning(f"[{STARTUP}] | Task=PostgreSQL引擎初始化 | 未配置 CONTEXT_SQL_URL，摘要和事件不会持久化")

    # 创建 AsyncContextManager（使用 PostgreSQL 持久存储）
    if sql_store is not None:
        async def llm_caller(messages: list) -> str:
            """使用独立配置的 LLM API 进行记忆分析（独立于 Pipecat Pipeline）"""
            try:
                api_key = settings.memory_llm_api_key or settings.dashscope_api_key
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": settings.memory_llm_model,
                    "messages": messages,
                }
                call_id = record_llm_request(
                    source="memory_llm",
                    provider="dashscope_compatible",
                    model=settings.memory_llm_model,
                    base_url=settings.memory_llm_base_url,
                    payload=payload,
                )
                async with httpx.AsyncClient(timeout=settings.memory_llm_timeout) as client:
                    try:
                        resp = await client.post(
                            settings.memory_llm_base_url,
                            json=payload,
                            headers=headers,
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        result = data["choices"][0]["message"]["content"]
                        record_llm_response(
                            call_id=call_id,
                            source="memory_llm",
                            provider="dashscope_compatible",
                            model=settings.memory_llm_model,
                            response={
                                "status_code": resp.status_code,
                                "data": data,
                            },
                        )
                        return result
                    except Exception as exc:
                        record_llm_response(
                            call_id=call_id,
                            source="memory_llm",
                            provider="dashscope_compatible",
                            model=settings.memory_llm_model,
                            status="failed",
                            error=exc,
                        )
                        raise
            except Exception as e:
                logger.error(f"[{STARTUP}] | Task=AsyncContextManager初始化 | Memory LLM Caller 调用失败: {e}")
                return ""

        embedding_api_key = settings.embedding_api_key or settings.dashscope_api_key
        embedding_model = settings.embedding_model or "text-embedding-v3"
        embedding_base_url = settings.embedding_api_base_url
        embedding_dimensions = settings.embedding_dimensions
        is_pg = bool(settings.context_sql_url and "postgresql" in settings.context_sql_url)

        embedding_service = EmbeddingService(
            sql_store=sql_store,
            api_key=embedding_api_key,
            model=embedding_model,
            base_url=embedding_base_url,
            dimensions=embedding_dimensions,
            is_pg=is_pg,
            max_retries=settings.embedding_api_max_retries,
        )
        file_store = MemoryFileStore(base_dir=settings.memories_dir)
        context_manager = AsyncContextManager(
            sql_store=sql_store,
            llm_caller=llm_caller,
            embedding_service=embedding_service,
            max_context_messages=settings.max_context_messages,
            direct_write=settings.memory_direct_write,
            file_store=file_store,
        )
        logger.info(
            f"[{STARTUP}] | Task=AsyncContextManager初始化 | AsyncContextManager 初始化完成（内存+文件模式，落盘目录={settings.memories_dir}）")
    else:
        logger.warning(
            f"[{STARTUP}] | Task=AsyncContextManager初始化 | 未配置 CONTEXT_SQL_URL，跳过 AsyncContextManager")

    # 注册核心记忆工具（save_important_event + compress_conversation）
    for core_tool in [SaveEventTool(), CompressSummaryTool()]:
        if not tool_registry.has(core_tool.name):
            tool_registry.register(core_tool)
    logger.info(
        f"[{STARTUP}] | Task=核心记忆工具注册 | 核心记忆工具已注册: save_important_event, compress_conversation")

    await conversation_session_manager.start_reminder_scheduler()
    try:
        yield
    finally:
        await conversation_session_manager.stop_reminder_scheduler()


app = FastAPI(
    title="Soulmeet",
    description="情感陪伴语音机器人平台",
    version="0.1.0",
    lifespan=lifespan
)

# 允许前端 dev server (http://localhost:5173) 及生产域名跨域访问
# 通过环境变量 CORS_ORIGINS 追加额外的允许来源（逗号分隔）
# 例如: CORS_ORIGINS=https://36.138.141.202:5173,https://192.168.0.84:5173
_cors_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://localhost:5173",
    "https://127.0.0.1:5173",
]
_extra_origins = os.environ.get("CORS_ORIGINS", "")
if _extra_origins:
    _cors_origins.extend([o.strip() for o in _extra_origins.split(",") if o.strip()])
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
async def health() -> dict[str, bool]:
    return {"ok": True}


app.include_router(webrtc_router)
app.include_router(session_router)
app.include_router(audiences_router)
app.include_router(auth_router)
app.include_router(conversations_router)
app.include_router(voice_clone_router)
app.include_router(text_runtime_router)
app.include_router(weather_router)
app.include_router(speech_router)
app.include_router(quick_actions_router)

if __name__ == "__main__":
    # pnpm dev:web --host
    # python main.py
    ssl_keyfile = "192.168.1.100+2-key.pem"
    ssl_certfile = "192.168.1.100+2.pem"
    use_ssl = Path(ssl_keyfile).exists() and Path(ssl_certfile).exists()

    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        ssl_keyfile=ssl_keyfile if use_ssl else None,
        ssl_certfile=ssl_certfile if use_ssl else None,
        access_log=False,
    )
#
