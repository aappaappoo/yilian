import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { AudienceType, SessionInfo, EmotionState } from '@soulmeet/shared'

export type ConnectionStatus = 'idle' | 'connecting' | 'connected' | 'disconnected' | 'error'

export const useSessionStore = defineStore('session', () => {
  // 连接状态
  const status = ref<ConnectionStatus>('idle')
  const errorMessage = ref<string | null>(null)

  // 会话信息
  const sessionInfo = ref<SessionInfo | null>(null)
  const selectedAudience = ref<AudienceType>('Liyin')
  const audienceVrmUrl = ref<string>('')

  // 情绪状态
  const emotionState = ref<EmotionState>({
    sadness: 0,
    anxiety: 0,
    anger: 0,
    label: '',
    keywords: [],
  })

  // 当前流程节点
  const currentNode = ref<string>('')

  // 可用工具列表
  const availableTools = ref<string[]>([])

  // 计算属性
  const isConnected = computed(() => status.value === 'connected')
  const isConnecting = computed(() => status.value === 'connecting')

  // Actions
  function setStatus(newStatus: ConnectionStatus) {
    status.value = newStatus
    if (newStatus !== 'error') {
      errorMessage.value = null
    }
  }

  function setError(message: string) {
    status.value = 'error'
    errorMessage.value = message
  }

  function setSessionInfo(info: SessionInfo) {
    sessionInfo.value = info
    currentNode.value = info.currentNode
  }

  function setAudience(audience: AudienceType, vrmUrl?: string) {
    selectedAudience.value = audience
    audienceVrmUrl.value = vrmUrl || ''
  }

  function updateEmotionState(emotion: EmotionState) {
    emotionState.value = { ...emotion }
  }

  function updateCurrentNode(node: string) {
    currentNode.value = node
  }

  function updateAvailableTools(tools: string[]) {
    availableTools.value = tools
  }

  function reset() {
    status.value = 'idle'
    errorMessage.value = null
    sessionInfo.value = null
    currentNode.value = ''
    availableTools.value = []
    emotionState.value = { sadness: 0, anxiety: 0, anger: 0, label: '', keywords: [] }
  }

  return {
    status,
    errorMessage,
    sessionInfo,
    selectedAudience,
    audienceVrmUrl,
    emotionState,
    currentNode,
    availableTools,
    isConnected,
    isConnecting,
    setStatus,
    setError,
    setSessionInfo,
    setAudience,
    updateEmotionState,
    updateCurrentNode,
    updateAvailableTools,
    reset,
  }
})
