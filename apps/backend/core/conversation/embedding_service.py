"""
Embedding 服务层

职责：
1. 持有同轮 round_cache（避免重复 embed 相同 contents）
2. 调用 embed API 生成向量
3. 调用 SQLStore.batch_save_embeddings 批量写入
4. 与 SQLStore 和 ContextManager 解耦
5. SQLite 环境自动 disable（不调用 embed API 也不写 embedding 列）

设计原则：
- embedding 是记忆写入的「后处理钩子」，不改变现有 action 决策逻辑
- embedding API 失败时仅记日志，记忆本身不受影响（embedding 列保持 NULL）
- 整个过程放 asyncio.create_task()，不阻塞对话流
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional

import httpx
from loguru import logger

from core.logging_utils import STARTUP, MEM_SYS, truncate_content


class EmbeddingService:
    """
    Embedding 服务类 — 持有 round_cache、调用 embed API、调用 batch_save。

    初始化参数：
        sql_store: SQLStore 实例（用于读取 contents 和写入 embedding）
        api_key: Embedding API Key
        model: Embedding 模型名称（如 text-embedding-v3）
        base_url: Embedding API Base URL（OpenAI 兼容格式）
        dimensions: 向量维度（None 时启动自动探测）
        is_pg: 是否为 PostgreSQL（SQLite 环境自动 disable）
        max_retries: embed API 调用失败时的最大重试次数
    """

    def __init__(
        self,
        sql_store: Any,
        api_key: str,
        model: str,
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
        dimensions: Optional[int] = None,
        is_pg: bool = True,
        max_retries: int = 3,
    ) -> None:
        self._sql = sql_store
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._dimensions = dimensions
        self._is_pg = is_pg
        self._enabled = bool(is_pg and api_key and model)
        self._max_retries = max(1, max_retries)
        self._round_cache: Dict[str, List[float]] = {}

        if not self._enabled:
            reasons = []
            if not is_pg:
                reasons.append("非 PostgreSQL 环境")
            if not api_key:
                reasons.append("未配置 API Key")
            if not model:
                reasons.append("未配置模型名")
            logger.info(
                f"[{STARTUP}] | Task=EmbeddingService初始化 | 已禁用: {', '.join(reasons)}"
            )
        else:
            logger.info(
                f"[{STARTUP}] | Task=EmbeddingService初始化 | 已启用: model={model}, "
                f"dimensions={dimensions or '自动探测'}"
            )

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def dimensions(self) -> Optional[int]:
        return self._dimensions

    def clear_round_cache(self) -> None:
        """清空同轮缓存"""
        self._round_cache.clear()

    async def detect_dimensions(self) -> int:
        """
        自动探测 embedding 维度：发送一条文本获取实际维度。
        仅在 dimensions 未配置时调用。
        """
        if self._dimensions:
            return self._dimensions

        try:
            vectors = await self.embed_texts(
                ["维度探测"], memory_action="dimension_detect"
            )
            if vectors and vectors[0]:
                self._dimensions = len(vectors[0])
                logger.info(
                    f"[{STARTUP}] | Task=EmbeddingService维度探测 | 自动探测维度: {self._dimensions}"
                )
                return self._dimensions
        except Exception as e:
            logger.warning(f"[{MEM_SYS}] | Task=embedding维度不匹配 | 维度探测失败: {e}")

        raise RuntimeError("embedding dimension detection failed")

    async def embed_texts(
        self,
        texts: List[str],
        memory_action: str = "memory_write",
    ) -> List[Optional[List[float]]]:
        """
        批量调用 embedding API 生成向量。

        Args:
            texts: 待 embed 的文本列表
            memory_action: 预留参数，区分意图识别 / 文档检索 / 记忆写入场景

        Returns:
            List[Optional[List[float]]]: 每条文本对应的向量，失败的为 None
        """
        if not self._enabled or not texts:
            return [None] * len(texts)

        # 查缓存，收集需要实际调用的
        results: List[Optional[List[float]]] = [None] * len(texts)
        uncached_indices: List[int] = []
        uncached_texts: List[str] = []

        for i, text in enumerate(texts):
            if text in self._round_cache:
                results[i] = self._round_cache[text]
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)

        if not uncached_texts:
            return results

        last_error = None
        for attempt in range(1, self._max_retries + 1):
            try:
                headers = {
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                }
                payload: Dict[str, Any] = {
                    "model": self._model,
                    "input": uncached_texts,
                }
                if self._dimensions:
                    payload["dimensions"] = self._dimensions

                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post(
                        self._base_url,
                        json=payload,
                        headers=headers,
                    )
                    resp.raise_for_status()
                    data = resp.json()

                embeddings = data.get("data", [])
                for emb_item in embeddings:
                    idx_in_uncached = emb_item.get("index", 0)
                    vector = emb_item.get("embedding")
                    if idx_in_uncached < len(uncached_indices) and vector:
                        original_idx = uncached_indices[idx_in_uncached]
                        results[original_idx] = vector
                        # 写入缓存
                        self._round_cache[uncached_texts[idx_in_uncached]] = vector

                last_error = None
                break  # 成功，退出重试循环

            except Exception as e:
                last_error = e
                if attempt < self._max_retries:
                    wait_time = min(2 ** (attempt - 1), 10)
                    logger.debug(
                        f"[{MEM_SYS}] | Task=embedding API失败 | embed API 第 {attempt}/{self._max_retries} 次调用失败，"
                        f"{wait_time}s 后重试: {e}"
                    )
                    await asyncio.sleep(wait_time)

        if last_error is not None:
            logger.warning(
                f"[{MEM_SYS}] | Task=embedding API失败 | embed API 调用失败（已重试 {self._max_retries} 次，记忆不受影响）: "
                f"{last_error}"
            )

        return results

    async def process_memory_embeddings(
        self,
        ids_to_embed: List[int],
    ) -> None:
        """
        后处理钩子：读取 contents → 批量 embed → 批量写入 embedding 列。

        该方法设计为在 asyncio.create_task() 中调用，不阻塞对话流。
        失败时仅记日志，记忆 embedding 列保持 NULL，检索时自动跳过。
        """
        if not self._enabled or not ids_to_embed:
            return

        try:
            # Step 1: 批量读取 contents
            records = await self._sql.get_memories_by_ids(ids_to_embed)
            if not records:
                return

            # Step 2: 收集需要 embed 的文本（用 dict 缓存避免重复）
            id_text_pairs: List[tuple] = []
            for rec in records:
                contents = rec.get("contents", "")
                if contents:
                    id_text_pairs.append((rec["id"], contents))

            if not id_text_pairs:
                return

            # 去重：相同 contents 只 embed 一次
            unique_texts = list({text for _, text in id_text_pairs})
            vectors = await self.embed_texts(unique_texts, memory_action="memory_write")
            text_to_vector = {}
            for text, vec in zip(unique_texts, vectors):
                if vec is not None:
                    text_to_vector[text] = vec

            # Step 3: 构建 (id, vector_str) 对
            pairs_to_save = []
            for record_id, text in id_text_pairs:
                vec = text_to_vector.get(text)
                if vec is not None:
                    vec_str = json.dumps(vec)
                    pairs_to_save.append((record_id, vec_str))

            # Step 4: 批量写入
            saved_count = 0
            if pairs_to_save:
                saved_count = await self._sql.batch_save_embeddings(pairs_to_save)

            # 合并日志：展示源文本 + 写入结果
            text_previews = [truncate_content(text, 60) for _, text in id_text_pairs]
            logger.info(
                f"[{MEM_SYS}] | Task=embedding后处理 | embedding完成: {len(id_text_pairs)}条文本已向量化, "
                f"写入={saved_count}/{len(pairs_to_save)}条, "
                f"原文={text_previews}"
            )

        except Exception as e:
            logger.warning(
                f"[{MEM_SYS}] | Task=embedding API失败 | process_memory_embeddings 失败"
                f"（记忆不受影响）: {e}"
            )
        finally:
            self.clear_round_cache()

    async def search(
        self,
        query: str,
        speaker_id: str,
        top_k: int = 10,
        memory_action: str = "semantic_search",
        reranker: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """
        语义检索入口：query → embed → search_by_embedding → 可选 reranker。

        Args:
            query: 查询文本
            speaker_id: 说话者 ID
            top_k: 返回前 K 条
            memory_action: 预留参数，区分检索场景
            reranker: 预留 reranker 接口（向量检索后可选二次精排）
                      签名: async def reranker(query, candidates) -> List[Dict]

        Returns:
            List[Dict]: 排序后的记忆列表
        """
        if not self._enabled:
            return []

        # Step 1: 生成查询向量
        vectors = await self.embed_texts([query], memory_action=memory_action)
        if not vectors or vectors[0] is None:
            return []

        query_vector_str = json.dumps(vectors[0])

        # Step 2: 向量检索
        candidates = await self._sql.search_by_embedding(
            query_vector=query_vector_str,
            speaker_id=speaker_id,
            top_k=top_k * 2 if reranker else top_k,  # reranker 需要更多候选
        )

        if not candidates:
            return []

        # Step 3: 可选 reranker 二次精排
        if reranker is not None:
            try:
                candidates = await reranker(query, candidates)
            except Exception as e:
                logger.warning(f"[{MEM_SYS}] | Task=embedding API失败 | reranker 失败: {e}")

        return candidates[:top_k]
