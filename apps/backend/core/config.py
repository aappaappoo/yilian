"""
统一配置中心
使用 Pydantic BaseSettings，自动从 .env 文件和环境变量读取配置。
全局通过 `from core.config import settings` 使用。
"""

from typing import Literal, Optional
from pydantic_settings import BaseSettings
from pydantic import Field, model_validator
from loguru import logger

from core.logging_utils import STARTUP


class Settings(BaseSettings):
    """
    所有配置项集中定义。
    命名规范：模块名_配置项，全大写映射到环境变量。
    """
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }

    # ── 应用基础 ──
    audience: str = Field(
        default="Liyin",
        description="默认人群插件名（当前端未指定时使用），对应 audiences/ 下的目录名",
    )
    debug: bool = Field(default=False, description="调试模式")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # ── DashScope ──
    dashscope_api_key: str = Field(..., description="DashScope API Key", repr=False)
    dashscope_stt_model: str = Field(default="paraformer-realtime-v2", description="STT 模型名")
    dashscope_tts_model: str = Field(default="cosyvoice-v3-flash", description="TTS 模型名")
    dashscope_tts_voice: str = Field(default="longanhuan", description="TTS 默认音色")
    dashscope_llm_model: str = Field(default="qwen-max", description="LLM 模型名")

    # ── DeepSeek（Soul 陪伴 Agent 默认 provider） ──
    deepseek_api_key: Optional[str] = Field(
        default=None,
        description="DeepSeek API Key（Soul 陪伴 Agent 默认 provider）",
        repr=False,
    )

    # ── Soul 陪伴 Agent（文本轮 LLM 工具调用循环，迁移自易联智慧_gpt） ──
    soul_agent_enabled: bool = Field(
        default=True,
        description="是否为文本轮启用 LLM 工具调用 agent",
    )
    soul_agent_provider: Literal["deepseek", "dashscope"] = Field(
        default="deepseek",
        description="Soul agent LLM 提供方：deepseek（默认）或 dashscope(qwen)",
    )
    soul_agent_model: Optional[str] = Field(
        default=None,
        description="Soul agent 模型名；为空时按 provider 取默认（deepseek→deepseek-chat，dashscope→qwen-plus）",
    )
    soul_agent_base_url: Optional[str] = Field(
        default=None,
        description="Soul agent chat/completions 完整 URL；为空时按 provider 取默认",
    )
    soul_agent_api_key: Optional[str] = Field(
        default=None,
        description="Soul agent API Key；为空时按 provider 取默认 key",
        repr=False,
    )
    soul_agent_max_turns: int = Field(
        default=8,
        description="Soul agent 工具调用最大轮数",
    )
    soul_agent_timeout: float = Field(
        default=60.0,
        description="Soul agent 单次 LLM 请求超时（秒）",
    )
    soul_agent_max_tokens: Optional[int] = Field(
        default=None,
        description="Soul agent 单次 LLM 响应 max_tokens；为空时不传，保持模型默认",
    )
    soul_agent_tool_concurrency: int = Field(
        default=10,
        description="Soul agent 同一轮 tool_calls 的最大并发执行数",
    )
    soul_skills_enabled: bool = Field(
        default=True,
        description="是否启用 Soulbot runtime skill 配置注入",
    )
    soul_skills_dir: str = Field(
        default=".soul_companion_home/skills",
        description="Soulbot runtime skill 安装目录；相对路径按项目根目录解析",
    )
    soul_skills_max_prompt_chars: int = Field(
        default=6000,
        description="最终回复类 skill 注入 prompt 的最大字符数",
    )
    soul_reply_humanizer_enabled: bool = Field(
        default=True,
        description="是否启用已安装的 reply-humanizer 对最终回复做自然表达约束",
    )

    # ── 易联健康接口（演示阶段固定成员） ──
    yilian_health_base_url: str = Field(
        default="https://www.agetech.cc/prod-api",
        description="易联健康接口 Base URL",
    )
    yilian_health_human_id: Optional[str] = Field(
        default=None,
        description="演示阶段固定查询的易联成员 humanId",
    )
    yilian_health_bearer_token: Optional[str] = Field(
        default=None,
        description="易联健康接口 Bearer Token；为空时不带鉴权头",
        repr=False,
    )

    # ── 对话存储（PostgreSQL） ──
    context_sql_url: Optional[str] = Field(
        default=None,
        description="SQL 数据库连接地址。"
                    "例: postgresql+asyncpg://user:pass@localhost:5432/soulmeet_db",
    )
    sql_pool_size: int = Field(default=5, description="数据库连接池大小")
    sql_max_overflow: int = Field(default=10, description="连接池最大溢出数")
    sql_pool_recycle: int = Field(default=3600, description="连接回收时间（秒）")

    # ── Pipeline ──
    vad_enabled: bool = Field(default=True, description="是否启用 VAD")
    stt_enabled: bool = Field(default=True, description="是否启用 STT（关闭后仅支持文字交互）")
    pipeline_enable_metrics: bool = Field(default=False, description="是否开启 Pipeline 指标")
    vad_confidence: float = Field(default=0.85, description="VAD 语音置信度阈值")
    vad_start_secs: float = Field(default=0.4, description="VAD 确认开始说话的持续时间")
    vad_stop_secs: float = Field(default=0.5, description="VAD 确认停止说话的持续时间")
    vad_min_volume: float = Field(default=0.8, description="VAD 最小音量阈值")

    # ── 服务 ──
    host: str = Field(default="0.0.0.0", description="监听地址")
    port: int = Field(default=8080, description="监听端口")

    # ── 对话历史 ──
    max_context_messages: int = Field(default=30, description="对话记录截断条数（全局默认值，可被角色 persona.yaml 覆盖）")
    summary_limit: int = Field(default=5, description="上下文同步时注入的摘要条数（全局默认值，可被角色 persona.yaml 覆盖）")
    events_limit: int = Field(default=20, description="上下文同步时注入的事件条数（全局默认值，可被角色 persona.yaml 覆盖）")

    # ── 记忆分析 LLM（对话记忆压缩/事件提取专用，可与主对话模型不同） ──
    memory_llm_api_key: Optional[str] = Field(
        default=None,
        description="记忆分析 LLM 的 API Key，默认使用 dashscope_api_key",
        repr=False,
    )
    memory_llm_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        description="记忆分析 LLM 的 API Base URL（OpenAI 兼容格式）",
    )
    memory_llm_model: str = Field(
        default="qwen-flash",
        description="记忆分析 LLM 模型名（建议用更便宜的模型）",
    )
    memory_llm_timeout: float = Field(
        default=30.0,
        description="记忆分析 LLM 请求超时时间（秒）",
    )
    quick_actions_llm_enabled: bool = Field(
        default=True,
        description="是否启用聊天页提示气泡 LLM 生成。使用 memory_llm_* 配置，独立于 Soul Agent。",
    )
    quick_actions_llm_model: Optional[str] = Field(
        default=None,
        description="提示气泡生成模型名；为空时复用 memory_llm_model。",
    )
    quick_actions_llm_timeout: float = Field(
        default=8.0,
        description="提示气泡生成请求超时时间（秒），前端也会独立超时，不阻塞主对话。",
    )
    memory_direct_write: bool = Field(
        default=False,
        description="记忆直写模式：跳过 DB 预查询比对/去重/冲突检测，LLM 分析结果直接写入数据库",
    )
    memories_dir: str = Field(
        default="memories",
        description="记忆文件持久化目录。按身份维度组织：user_id/{uid}/、sessions/{sid}/",
    )

    # ── TURN 服务器（NAT 穿透） ──
    voice_transport: Literal["self_webrtc", "livekit"] = Field(
        default="livekit",
        description="语音传输层：self_webrtc 使用当前自建 WebRTC，livekit 使用 LiveKit Cloud",
    )
    livekit_url: Optional[str] = Field(
        default=None,
        description="LiveKit Cloud WebSocket URL，如 wss://xxx.livekit.cloud",
    )
    livekit_api_key: Optional[str] = Field(
        default=None,
        description="LiveKit API Key",
        repr=False,
    )
    livekit_api_secret: Optional[str] = Field(
        default=None,
        description="LiveKit API Secret",
        repr=False,
    )
    livekit_token_ttl_seconds: int = Field(
        default=3600,
        description="LiveKit 前端/Agent token 有效期（秒）",
    )

    turn_url: Optional[str] = Field(
        default=None,
        description="TURN 服务器地址，如 turn:36.138.141.202:3478 或 turn:your-server:3478",
    )
    turn_username: Optional[str] = Field(
        default=None,
        description="TURN 服务器用户名",
    )
    turn_credential: Optional[str] = Field(
        default=None,
        description="TURN 服务器密码",
        repr=False,
    )

    # ── 声音克隆 ──
    voice_clone_api_key: Optional[str] = Field(
        default=None,
        description="声音克隆 API Key，默认使用 dashscope_api_key",
        repr=False,
    )
    voice_clone_target_model: str = Field(
        default="cosyvoice-v2",
        description="声音克隆目标模型",
    )
    voice_clone_max_file_size_mb: int = Field(
        default=50,
        description="声音克隆上传文件最大大小(MB)",
    )

    # ── 阿里云 OSS（声音克隆文件上传） ──
    oss_access_key_id: Optional[str] = Field(
        default=None,
        description="阿里云 OSS Access Key ID",
        repr=False,
    )
    oss_access_key_secret: Optional[str] = Field(
        default=None,
        description="阿里云 OSS Access Key Secret",
        repr=False,
    )
    oss_bucket_name: Optional[str] = Field(
        default=None,
        description="阿里云 OSS Bucket 名称",
    )
    oss_endpoint: Optional[str] = Field(
        default=None,
        description="阿里云 OSS Endpoint，如 oss-cn-beijing.aliyuncs.com",
    )
    oss_voice_clone_prefix: str = Field(
        default="voice-clone/",
        description="声音克隆音频在 OSS 中的路径前缀",
    )

    # ── 认证 ──
    jwt_secret_key: str = Field(default="change-me-in-production", description="JWT 签名密钥")
    jwt_expire_hours: int = Field(default=24, description="JWT 过期时间（小时）")
    admin_username: str = Field(default="yuxx", description="初始管理员用户名")
    admin_password: str = Field(default="yuxx", description="初始管理员密码")

    # ── Embedding 配置 ──
    embedding_model: Optional[str] = Field(
        default=None,
        description="Embedding 模型名称（如 text-embedding-v3），为空时禁用 embedding",
    )
    embedding_dimensions: Optional[int] = Field(
        default=None,
        description="Embedding 向量维度，为空时自动探测（发送一条文本获取维度）",
    )
    embedding_api_key: Optional[str] = Field(
        default=None,
        description="Embedding API Key，默认使用 dashscope_api_key",
        repr=False,
    )
    embedding_api_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
        description="Embedding API Base URL（OpenAI 兼容格式）",
    )
    embedding_api_max_retries: int = Field(
        default=3,
        description="Embedding API 调用失败时的最大重试次数",
    )

    @model_validator(mode="after")
    def _check_sql_url(self) -> "Settings":
        """校验 SQL URL 格式，提醒用户使用 asyncpg 驱动"""
        if self.context_sql_url and "postgresql" in self.context_sql_url:
            if "asyncpg" not in self.context_sql_url:
                logger.warning(
                    f"[{STARTUP}] | Task=环境变量加载 | PostgreSQL URL 建议使用 asyncpg 驱动: "
                    "postgresql+asyncpg://user:pass@host/db"
                )
        return self


# ── 全局单例 ──
settings = Settings()
logger.info(
    f"[{STARTUP}] | Task=环境变量加载 | Settings已加载: audience={settings.audience}, "
    f"sql_url={'已配置' if settings.context_sql_url else '未配置'}, "
    f"voice_transport={settings.voice_transport}, "
    f"livekit={'已配置' if settings.livekit_url and settings.livekit_api_key and settings.livekit_api_secret else '未配置'}",
)


def get_settings() -> Settings:
    return settings
