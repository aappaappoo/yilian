"""
文件持久化存储 + 内存缓存

替代 DB 存储链路，实现"内存读写→LLM分析→内存更新+异步落盘到文件"。

内存缓存以身份维度组织，每个用户/会话的记忆存放在独立的缓存条目中。
异步落盘使用 asyncio.to_thread 将文件 I/O 放到线程池执行，不阻塞对话流。

文件组织（引入时间分区 {time_bucket}，格式为 YYYYMMDDHH00）：
  memories/
    ├── user_id/{user_id}/
    │   └── {time_bucket}/
    │       ├── {audiences}.json | {audiences}.md
    │       ├── audio/
    │       │   └── {YYYYMMDDHHMMSSffffff}-{role}.wav
    │       └── speaker_id/{speaker_id}/
    │                         ├── {audiences}.json | {audiences}.md
    │                         └── audio/
    │                             └── {YYYYMMDDHHMMSSffffff}-{role}.wav
    └── sessions/{session_id}/
        └── {time_bucket}/
            ├── {audiences}.json | {audiences}.md
            └── audio/
                └── {YYYYMMDDHHMMSSffffff}-{role}.wav

写入：始终写入当前小时分区。
加载：优先当前小时，若不存在则自动回溯至最新已有分区。
音频：每段发言（用户或机器人）单独保存为一个 WAV 文件，文件名前缀为发言开始时间（YYYYMMDDHHMMSSffffff）。
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import wave
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from loguru import logger

from core.logging_utils import MEM_SYS


_TIME_BUCKET_RE = re.compile(r"^\d{12}$")


class MemoryFileStore:
    """
    文件持久化存储 + 内存缓存。

    内存缓存按身份维度组织：
    - cache_key = f"{audiences}:{identity_type}:{identity_value}"
    - 每个 cache_key 对应一组完整的记忆数据（memories + summaries + events + categories）

    记忆 ID 使用自增计数器生成（无需数据库自增 ID）。
    """

    def __init__(self, base_dir: str = "memories") -> None:
        self._base_dir = base_dir
        # 内存缓存：key → MemoryData (dict)
        self._cache: Dict[str, Dict[str, Any]] = {}
        # 自增 ID 计数器
        self._next_id: int = 1
        # 异步写入任务集合（防止 GC 回收）
        self._write_tasks: Set[asyncio.Task] = set()

    # ── 路径解析 ──

    @staticmethod
    def _time_bucket() -> str:
        """返回当前时间分区标识（小时粒度：YYYYMMDDHH00）"""
        return datetime.now().strftime("%Y%m%d%H00")

    def _resolve_dir(
        self,
        user_id: str = "",
        speaker_id: str = "",
        session_id: str = "",
        time_bucket: str = "",
    ) -> str:
        """
        根据 3 级身份和时间分区解析文件目录路径。

        优先级：
        1. user_id + speaker_id → memories/user_id/{user_id}/{time_bucket}/speaker_id/{speaker_id}/
        2. user_id → memories/user_id/{user_id}/{time_bucket}/
        3. session_id → memories/sessions/{session_id}/{time_bucket}/

        time_bucket 默认为当前小时（YYYYMMDDHH00）。
        """
        tb = time_bucket or self._time_bucket()
        if user_id and speaker_id:
            return os.path.join(self._base_dir, "user_id", user_id, tb, "speaker_id", speaker_id)
        elif user_id:
            return os.path.join(self._base_dir, "user_id", user_id, tb)
        else:
            return os.path.join(self._base_dir, "sessions", session_id, tb)

    def _resolve_audio_dir(
        self,
        user_id: str = "",
        speaker_id: str = "",
        session_id: str = "",
        time_bucket: str = "",
    ) -> str:
        """
        解析音频文件目录路径（在 _resolve_dir 结果下新建 audio 子目录）。

        结构示例：
          memories/user_id/{user_id}/{time_bucket}/audio/
          memories/user_id/{user_id}/{time_bucket}/speaker_id/{speaker_id}/audio/
          memories/sessions/{session_id}/{time_bucket}/audio/
        """
        base = self._resolve_dir(user_id, speaker_id, session_id, time_bucket)
        return os.path.join(base, "audio")

    def _resolve_latest_json_path(
        self,
        user_id: str = "",
        speaker_id: str = "",
        session_id: str = "",
        audiences: str = "",
    ) -> Optional[str]:
        """
        从已存在的时间分区目录中，找到最新一个包含目标 JSON 文件的路径。

        扫描身份根目录下的所有子目录（按名称倒序），依次检查目标文件是否存在。
        用于 load_from_file 时自动回溯最近分区，避免跨小时切换后记忆丢失。

        Returns:
            str | None: 找到的 JSON 文件绝对路径，或 None（无任何历史数据）。
        """
        filename = f"{audiences}.json"
        if user_id and speaker_id:
            identity_base = os.path.join(self._base_dir, "user_id", user_id)
            def _json_path(tb: str) -> str:
                return os.path.join(identity_base, tb, "speaker_id", speaker_id, filename)
        elif user_id:
            identity_base = os.path.join(self._base_dir, "user_id", user_id)
            def _json_path(tb: str) -> str:
                return os.path.join(identity_base, tb, filename)
        else:
            identity_base = os.path.join(self._base_dir, "sessions", session_id)
            def _json_path(tb: str) -> str:
                return os.path.join(identity_base, tb, filename)

        if not os.path.isdir(identity_base):
            return None
        try:
            buckets = sorted(
                [
                    d for d in os.listdir(identity_base)
                    if _TIME_BUCKET_RE.match(d) and os.path.isdir(os.path.join(identity_base, d))
                ],
                reverse=True,
            )
        except OSError:
            return None
        for tb in buckets:
            path = _json_path(tb)
            if os.path.exists(path):
                return path
        return None

    @staticmethod
    def _cache_key(
        audiences: str,
        user_id: str = "",
        speaker_id: str = "",
        session_id: str = "",
    ) -> str:
        """
        根据 3 级身份生成缓存 key。

        与 _resolve_dir 使用相同的优先级逻辑。
        """
        if user_id and speaker_id:
            return f"{audiences}:speaker:{speaker_id}"
        elif user_id:
            return f"{audiences}:user:{user_id}"
        else:
            return f"{audiences}:session:{session_id}"

    def _alloc_id(self) -> int:
        """分配一个自增 ID"""
        rid = self._next_id
        self._next_id += 1
        return rid

    # ── 内存读取 ──

    def get_summaries(
        self,
        audiences: str,
        user_id: str = "",
        speaker_id: str = "",
        session_id: str = "",
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """从内存缓存获取摘要列表（零 IO）"""
        key = self._cache_key(audiences, user_id, speaker_id, session_id)
        data = self._cache.get(key, {})
        return list(data.get("summaries", [])[:limit])

    def get_events(
        self,
        audiences: str,
        user_id: str = "",
        speaker_id: str = "",
        session_id: str = "",
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """从内存缓存获取事实/事件列表（零 IO）"""
        key = self._cache_key(audiences, user_id, speaker_id, session_id)
        data = self._cache.get(key, {})
        return list(data.get("events", [])[:limit])

    def get_memories(
        self,
        audiences: str,
        user_id: str = "",
        speaker_id: str = "",
        session_id: str = "",
    ) -> List[Dict[str, Any]]:
        """从内存缓存获取全量记忆记录（供 LLM 分析 prompt 用）"""
        key = self._cache_key(audiences, user_id, speaker_id, session_id)
        data = self._cache.get(key, {})
        return list(data.get("memories", []))

    # ── 内存更新 ──

    def update_memories(
        self,
        audiences: str,
        user_id: str = "",
        speaker_id: str = "",
        session_id: str = "",
        memories: Optional[List[Dict[str, Any]]] = None,
        summary_msg_type: str = "对话摘要",
    ) -> None:
        """用 LLM 分析结果更新内存缓存。"""
        if not memories:
            return

        key = self._cache_key(audiences, user_id, speaker_id, session_id)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        new_full_memories: List[Dict[str, Any]] = []
        new_summaries: List[Dict[str, Any]] = []
        new_events: List[Dict[str, Any]] = []

        for m in memories:
            msg_type = m.get("msg_type", "")
            content_type = m.get("content_type", "")
            contents = m.get("contents", "")

            if not contents:
                continue

            new_id = self._alloc_id()
            record = {
                "id": new_id,
                "msg_type": msg_type,
                "content_type": content_type,
                "contents": contents,
                "importance": m.get("importance", 5),
                "status": m.get("status", "valid"),
                "create_time": now_str,
            }
            new_full_memories.append(record)

            if msg_type == summary_msg_type:
                new_summaries.append({
                    "id": new_id,
                    "create_time": now_str,
                    "contents": contents,
                })
            else:
                new_events.append({
                    "id": new_id,
                    "content_type": content_type,
                    "contents": contents,
                    "importance": m.get("importance", 5),
                })

        self._cache[key] = {
            "memories": new_full_memories,
            "summaries": new_summaries,
            "events": new_events,
            "llm_analysis": list(memories),
        }

    # ── 异步文件写入 ──

    def schedule_write_json(
        self,
        user_id: str = "",
        speaker_id: str = "",
        session_id: str = "",
        audiences: str = "",
    ) -> None:
        """调度异步 JSON 写入（摘要+事实数据）"""
        key = self._cache_key(audiences, user_id, speaker_id, session_id)
        data = self._cache.get(key)
        if not data:
            return

        task = asyncio.create_task(
            self._async_write_json(user_id, speaker_id, session_id, audiences, data)
        )
        self.register_write_task(task)

    async def flush_json(
        self,
        user_id: str = "",
        speaker_id: str = "",
        session_id: str = "",
        audiences: str = "",
    ) -> None:
        """
        同步（awaited）写入 JSON 文件，确保写入完成后再返回。

        用于会话断开时保证 {audiences}.json 一定被覆盖写入，
        不会因 fire-and-forget 任务未完成而丢失数据。
        """
        key = self._cache_key(audiences, user_id, speaker_id, session_id)
        data = self._cache.get(key)
        if not data:
            return
        await self._async_write_json(user_id, speaker_id, session_id, audiences, data)

    def schedule_write_md(
        self,
        user_id: str = "",
        speaker_id: str = "",
        session_id: str = "",
        audiences: str = "",
        messages: Optional[List[Dict[str, str]]] = None,
    ) -> None:
        """调度异步 MD 写入（原始对话数据）"""
        if not messages:
            return

        task = asyncio.create_task(
            self._async_write_md(user_id, speaker_id, session_id, audiences, messages)
        )
        self.register_write_task(task)

    async def _async_write_json(
        self,
        user_id: str,
        speaker_id: str,
        session_id: str,
        audiences: str,
        data: Dict[str, Any],
    ) -> None:
        """异步写入 JSON 文件（摘要+事实数据）"""
        dir_path = self._resolve_dir(user_id, speaker_id, session_id)
        filepath = os.path.join(dir_path, f"{audiences}.json")
        try:
            # 序列化为 JSON 字符串
            file_data = {
                "summaries": data.get("summaries", []),
                "events": data.get("events", []),
                "memories": data.get("memories", []),
                "llm_analysis": data.get("llm_analysis", []),
            }
            content = json.dumps(file_data, ensure_ascii=False, indent=2)
            await asyncio.to_thread(self._write_file, dir_path, filepath, content)
            logger.info(
                f"[{MEM_SYS}] | Task=异步摘要和事实数据JSON写入 | "
                f"文件={filepath}, "
                f"summaries={len(file_data['summaries'])}条, "
                f"events={len(file_data['events'])}条, "
                f"memories={len(file_data['memories'])}条, "
                f"llm_analysis={len(file_data['llm_analysis'])}条"
            )
        except Exception as e:
            logger.error(
                f"[{MEM_SYS}] | Task=异步摘要和事实数据JSON写入 | "
                f"写入失败: {filepath}, error={e}"
            )

    async def _async_write_md(
        self,
        user_id: str,
        speaker_id: str,
        session_id: str,
        audiences: str,
        messages: List[Dict[str, str]],
    ) -> None:
        """异步追加写入 MD 文件（原始对话数据）"""
        dir_path = self._resolve_dir(user_id, speaker_id, session_id)
        filepath = os.path.join(dir_path, f"{audiences}.md")
        try:
            lines = []
            for m in messages:
                ts = m.get("timestamp", "")
                round_id = m.get("round_id", 0)
                role = m.get("role", "user")
                content = m.get("content", "")
                # 格式: 2026-04-03 13:06:35 round=1 user: xxxx
                lines.append(f"{ts} round={round_id} {role}: {content}")

            text = "\n".join(lines) + "\n"
            await asyncio.to_thread(self._append_file, dir_path, filepath, text)
            logger.info(
                f"[{MEM_SYS}] | Task=异步原始对话MD写入 | "
                f"文件={filepath}, 消息={len(messages)}条"
            )
        except Exception as e:
            logger.error(
                f"[{MEM_SYS}] | Task=异步原始对话MD写入 | "
                f"写入失败: {filepath}, error={e}"
            )

    # ── 文件加载（启动时） ──

    async def load_from_file(
        self,
        user_id: str = "",
        speaker_id: str = "",
        session_id: str = "",
        audiences: str = "",
    ) -> bool:
        """
        从 JSON 文件加载记忆到内存缓存。

        优先尝试当前小时分区；若当前分区不存在则自动回溯至最近已有分区。

        Returns:
            bool: 加载是否成功（文件不存在也视为成功但返回 False）
        """
        filepath = await asyncio.to_thread(
            self._resolve_latest_json_path, user_id, speaker_id, session_id, audiences
        )

        if not filepath or not os.path.exists(filepath):
            return False

        try:
            content = await asyncio.to_thread(self._read_file, filepath)
            data = json.loads(content)

            key = self._cache_key(audiences, user_id, speaker_id, session_id)
            self._cache[key] = {
                "memories": data.get("memories", []),
                "summaries": data.get("summaries", []),
                "events": data.get("events", []),
            }

            # 更新 ID 计数器，避免与已有记录 ID 冲突
            max_id = 0
            for m in data.get("memories", []):
                mid = m.get("id", 0)
                if isinstance(mid, int) and mid > max_id:
                    max_id = mid
            if max_id >= self._next_id:
                self._next_id = max_id + 1

            logger.info(
                f"[{MEM_SYS}] | Task=文件加载记忆 | "
                f"文件={filepath}, "
                f"summaries={len(data.get('summaries', []))}条, "
                f"events={len(data.get('events', []))}条"
            )
            return True
        except Exception as e:
            logger.error(
                f"[{MEM_SYS}] | Task=文件加载记忆 | "
                f"加载失败: {filepath}, error={e}"
            )
            return False

    def register_write_task(self, task: asyncio.Task) -> None:
        """注册一个异步写入任务，防止其被 GC 回收（fire-and-forget 安全）。"""
        self._write_tasks.add(task)
        task.add_done_callback(self._write_tasks.discard)

    # ── 音频文件写入 ──

    async def save_audio_file(
        self,
        user_id: str = "",
        speaker_id: str = "",
        session_id: str = "",
        role: str = "user",
        start_time: Optional[datetime] = None,
        pcm_data: bytes = b"",
        sample_rate: int = 16000,
    ) -> None:
        """
        将 PCM 音频数据保存为 WAV 文件（异步，不阻塞对话流）。

        文件命名：{YYYYMMDDHHMMSSffffff}-{role}.wav
        写入目录：{resolve_audio_dir}/

        Args:
            user_id:     用户标识
            speaker_id:  说话者标识
            session_id:  会话标识
            role:        角色名（"user" 或 audiences 名称）
            start_time:  本轮发言开始时间（用于文件名前缀，默认当前时间）
            pcm_data:    原始 PCM 音频字节（16-bit，mono）
            sample_rate: 采样率（Hz）
        """
        if not pcm_data:
            return

        ts = (start_time or datetime.now()).strftime("%Y%m%d%H%M%S%f")
        filename = f"{ts}-{role}.wav"
        audio_dir = self._resolve_audio_dir(user_id, speaker_id, session_id)
        filepath = os.path.join(audio_dir, filename)

        try:
            await asyncio.to_thread(
                self._write_wav_file, audio_dir, filepath, pcm_data, sample_rate
            )
            logger.info(
                f"[{MEM_SYS}] | Task=音频文件写入 | "
                f"文件={filepath}, 大小={len(pcm_data)}字节, 采样率={sample_rate}Hz"
            )
        except Exception as e:
            logger.error(
                f"[{MEM_SYS}] | Task=音频文件写入 | "
                f"写入失败: {filepath}, error={e}"
            )

    # ── 底层文件操作（同步，在线程池执行） ──

    @staticmethod
    def _write_file(dir_path: str, filepath: str, content: str) -> None:
        """同步写入文件（覆盖）"""
        os.makedirs(dir_path, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

    @staticmethod
    def _append_file(dir_path: str, filepath: str, content: str) -> None:
        """同步追加写入文件"""
        os.makedirs(dir_path, exist_ok=True)
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(content)

    @staticmethod
    def _read_file(filepath: str) -> str:
        """同步读取文件"""
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()

    @staticmethod
    def _write_wav_file(
        dir_path: str, filepath: str, pcm_data: bytes, sample_rate: int
    ) -> None:
        """同步写入 WAV 文件（16-bit PCM, mono）"""
        os.makedirs(dir_path, exist_ok=True)
        with wave.open(filepath, "wb") as wf:
            wf.setnchannels(1)      # mono
            wf.setsampwidth(2)      # 16-bit
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_data)
