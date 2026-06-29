"""
日志工具模块

提供：
- session_logger: 返回绑定 sid（session_id 前 8 位）和 module 的 loguru logger
- 生命周期标记常量（以产品功能命名，便于按功能过滤日志）
- 日志过滤功能：通过 LOG_FILTER 列表控制仅输出指定类别的日志
"""

import os
import re
from loguru import logger as _logger

# ── 生命周期标记 ──
# 每条日志都携带一个标记，标识该日志影响的产品功能。
# 使用方式: logger.info(f"[{STARTUP}] | Task=XXX | 描述 ...")
STARTUP = "启动"                # 系统初始化、组件加载、数据库连接、管道组装
SESSION_START = "会话开始"       # WebRTC 会话建立
SESSION_END = "会话结束"         # WebRTC 断开、资源清理
USER_INPUT = "用户输入"          # 用户消息到达（STT 转写结果 / 文字输入）
AI_REPLY = "AI回复"              # LLM 回复发送给用户
STT = "语音识别"                 # STT 处理
TTS = "语音合成"                 # TTS 处理
EMOTION = "情绪感知"             # 情绪信号检测与策略决策
SAFETY = "安全拦截"              # 不安全内容被拦截
CONTEXT_SYNC = "上下文同步"      # LLM 上下文截断、历史记忆注入
CONV_STATE = "对话状态管理"      # 会话状态、连接状态和运行时操作
MEM_SYS = "记忆系统"             # 记忆分析 / 读取 / 写入 / 摘要 / 提取 / 失败 统一收敛

TOOL_CALL = "工具调用"           # 工具执行（天气 / 提醒 / 备忘等）

# ── 日志过滤 ──
# LOG_FILTER: 控制日志输出的过滤列表。
# - 为空列表 [] 时：输出所有日志（不过滤）
# - 填入类别名后：仅输出包含指定类别的日志
#
# 支持主类别和子任务过滤：
#   - 填 "记忆系统"            → 匹配所有 [记忆系统] | Task=* 子任务日志
#   - 填 "记忆系统-LLM分析请求" → 仅匹配该子任务
#
# 也可通过环境变量 LOG_FILTER 设置（逗号分隔）：
#   export LOG_FILTER="启动,记忆系统,AI回复"
#
# 示例：仅查看启动和记忆相关日志
# LOG_FILTER = ["启动", "记忆系统"]
# 子任务过滤示例：仅查看记忆系统的 LLM 分析请求
# 格式为 "类别-子任务"，匹配 [记忆系统] | Task=LLM分析请求 的日志
# LOG_FILTER = ["记忆系统-LLM分析请求"]
LOG_FILTER: list[str] = []

# 从环境变量加载过滤列表（优先级高于代码中直接赋值）
_env_filter = os.environ.get("LOG_FILTER", "").strip()
if _env_filter:
    LOG_FILTER = [f.strip() for f in _env_filter.split(",") if f.strip()]

# 预编译：从日志消息中提取 [类别] 标签
_TAG_PATTERN = re.compile(r"\[([^\[\]]+)\]")
# 预编译：从日志消息中提取 Task=子任务 值
_TASK_PATTERN = re.compile(r"Task=(\S+)")


def log_filter(record: dict) -> bool:
    """
    loguru filter 函数：根据 LOG_FILTER 列表过滤日志。

    当 LOG_FILTER 为空时，放行所有日志。
    当 LOG_FILTER 非空时，仅放行消息中包含匹配标签的日志。
    匹配规则：
      - 精确匹配：LOG_FILTER 中 "记忆系统-LLM分析请求" 匹配 [记忆系统] | Task=LLM分析请求
      - 前缀匹配：LOG_FILTER 中 "记忆系统" 匹配 [记忆系统] | Task=LLM分析请求、[记忆系统] | Task=知识更新 等
    """
    if not LOG_FILTER:
        return True

    message = record["message"]
    tags = _TAG_PATTERN.findall(message)
    if not tags:
        # 没有标签的日志（如第三方库）始终放行
        return True

    # 提取 Task 值（如果存在）
    task_match = _TASK_PATTERN.search(message)
    task_value = task_match.group(1) if task_match else ""

    for tag in tags:
        for allowed in LOG_FILTER:
            if "-" not in allowed:
                # 主类别匹配
                if tag == allowed:
                    return True
                continue
            # 子任务精确匹配：将 "记忆系统-LLM分析请求" 拆为类别+子任务
            allowed_tag, allowed_task = allowed.split("-", 1)
            if tag == allowed_tag and task_value == allowed_task:
                return True
    return False


def truncate_content(text: str, max_len: int = 60) -> str:
    """
    截断长文本用于日志展示，保留首尾各一部分。

    超过 max_len 时显示为: 前缀...后缀
    """
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    half = max_len // 2
    return f"{text[:half]}...{text[-half:]}"


def flatten_content(text: str, max_len: int = 0) -> str:
    """
    将多行文本合并为单行，用于日志单行展示。

    先将换行符替换为空格，压缩连续空格。
    当 max_len > 0 时，再调用 truncate_content 截断。
    max_len=0（默认）不截断，返回完整的单行文本。
    """
    if not text:
        return ""
    oneline = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    # 压缩连续空格为单个
    while "  " in oneline:
        oneline = oneline.replace("  ", " ")
    result = oneline.strip()
    if max_len > 0:
        return truncate_content(result, max_len)
    return result


def session_logger(session_id: str, module: str):
    """
    返回绑定了 sid（session_id 前 8 位）和 module 的 loguru logger。

    Args:
        session_id: 完整的会话 ID（UUID 格式）
        module:     模块标识（如 'core.webrtc'、'core.flow_engine'）

    Returns:
        loguru BoundLogger 实例
    """
    sid = session_id[:8] if session_id else ""
    return _logger.bind(sid=sid, module=module)
