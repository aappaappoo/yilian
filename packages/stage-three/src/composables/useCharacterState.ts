import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import type { CharacterState, ConnectionStatus } from '../types'

export interface UseCharacterStateOptions {
  connectionStatus: Ref<ConnectionStatus>
  streamingMessage: Ref<any>
}

export interface UseCharacterStateReturn {
  state: Readonly<Ref<CharacterState>>
  transitionTo: (target: CharacterState) => void
  isActive: ComputedRef<boolean>
}

/** speaking 状态超时时间 ms — 无新 stream 片段则回 idle */
const SPEAKING_TIMEOUT_MS = 10000

/**
 * 角色状态机 composable
 *
 * 状态流转：
 * - loading → idle (成功) / fallback (失败/超时/能力不足)
 * - idle ↔ speaking (stream 推断)
 * - error → fallback (自动)
 * - fallback 是终态，同一会话不回升
 *
 * speaking 进入条件（P1 临时方案）：
 * @deprecated 基于消息推断，后端实现 ai_state 后替换
 * - streamingMessage 从 null → 非 null → speaking
 * - streamingMessage 从 非 null → null → idle
 * - 补充：10s 无新 stream 片段 → idle
 */
export function useCharacterState(options: UseCharacterStateOptions): UseCharacterStateReturn {
  const { connectionStatus, streamingMessage } = options

  const state = ref<CharacterState>('loading')
  let speakingTimeout: ReturnType<typeof setTimeout> | null = null

  const isActive = computed(() => {
    return state.value === 'loading' || state.value === 'idle' || state.value === 'speaking'
  })

  function transitionTo(target: CharacterState) {
    // fallback 是终态，禁止回升
    if (state.value === 'fallback') return

    // error → 自动转为 fallback
    if (target === 'error') {
      state.value = 'fallback'
      return
    }

    state.value = target
  }

  function clearSpeakingTimeout() {
    if (speakingTimeout !== null) {
      clearTimeout(speakingTimeout)
      speakingTimeout = null
    }
  }

  // 监听 streamingMessage 变化推断 speaking 状态
  // TODO: 后端提供 ai_state 事件后，移除此 @deprecated 的消息推断逻辑
  watch(streamingMessage, (newVal, oldVal) => {
    if (state.value === 'fallback') return

    if (newVal && !oldVal) {
      // 开始 speaking
      if (state.value === 'idle') {
        state.value = 'speaking'
      }
    }

    if (newVal) {
      // 重置 10s 超时
      clearSpeakingTimeout()
      speakingTimeout = setTimeout(() => {
        if (state.value === 'speaking') {
          state.value = 'idle'
        }
      }, SPEAKING_TIMEOUT_MS)
    }

    if (!newVal && oldVal) {
      // 停止 speaking
      clearSpeakingTimeout()
      if (state.value === 'speaking') {
        state.value = 'idle'
      }
    }
  })

  // 断连行为：speaking → 过渡回 idle
  watch(connectionStatus, (newStatus) => {
    if (state.value === 'fallback') return
    if (newStatus !== 'connected' && state.value === 'speaking') {
      clearSpeakingTimeout()
      state.value = 'idle'
    }
  })

  return {
    state,
    transitionTo,
    isActive,
  }
}
