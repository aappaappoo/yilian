<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import type { Component, ComponentPublicInstance } from 'vue'
import { EMOTION_FALLBACK_LABEL, EMOTION_STATE_HOLD_MS, type EmotionState, type ServerMessage } from '@soulmeet/shared'
import { getChatMessageText, type ChatMessage, type TaskProgressItem } from '../composables/useChat'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { useSessionStore } from '../stores/session'
import { useAuthStore } from '../stores/auth'
import { useWebRTC } from '../composables/useWebRTC'
import { useChat } from '../composables/useChat'
import DesktopChatLayout from '../components/chat/DesktopChatLayout.vue'
import EmotionDebugPanel, { type EmotionDebugOption } from '../components/chat/EmotionDebugPanel.vue'
import MobileChatLayout from '../components/chat/MobileChatLayout.vue'
import AllConversationsModal from '../components/conversations/AllConversationsModal.vue'
import RenameConversationModal from '../components/conversations/RenameConversationModal.vue'
import LoginModal from '../components/LoginModal.vue'
import RegisterModal from '../components/RegisterModal.vue'
import SkillCenterModal from '../components/skills/SkillCenterModal.vue'
import SubscriptionModal from '../components/home/SubscriptionModal.vue'
import { apiUrl } from '../utils/api'
import { buildConversationRounds } from '../utils/conversationRounds'
import { buildQuickActionMessages, createDefaultQuickActions, sanitizeQuickActionSuggestions } from '../utils/quickActionSuggestions'

function isEnabledEnv(value: unknown): boolean {
  const normalized = String(value ?? '').trim().toLowerCase()
  return normalized === '1' || normalized === 'true' || normalized === 'yes'
}

function numberFromEnv(value: unknown): number | null {
  const parsed = Number.parseFloat(String(value ?? '').trim())
  return Number.isFinite(parsed) ? parsed : null
}

function clampNumber(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

const isVrmDisabledByEnv = isEnabledEnv(import.meta.env.VITE_DISABLE_VRM)
const TEXT_RUNTIME_MIN_TIMEOUT_SECONDS = 1
const TEXT_RUNTIME_MAX_TIMEOUT_SECONDS = 120
const TEXT_RUNTIME_DEFAULT_TIMEOUT_SECONDS = 120
const textRuntimeTimeoutSeconds = clampNumber(
  numberFromEnv(import.meta.env.VITE_TEXT_RUNTIME_TIMEOUT_SECONDS) ?? TEXT_RUNTIME_DEFAULT_TIMEOUT_SECONDS,
  TEXT_RUNTIME_MIN_TIMEOUT_SECONDS,
  TEXT_RUNTIME_MAX_TIMEOUT_SECONDS,
)
const AvatarCanvas = defineAsyncComponent({
  loader: async (): Promise<Component> => {
    if (isVrmDisabledByEnv) {
      return (await import('../components/AvatarErrorFallback.vue')).default
    }
    return (await import('@soulmeet/stage-three')).AvatarCanvas as Component
  },
  errorComponent: () => import('../components/AvatarErrorFallback.vue'),
  timeout: 10000,
})

if (isVrmDisabledByEnv) {
  console.info('[Soulmeet] 3D VRM 已禁用：跳过 stage-three 和 model.vrm 加载')
}

marked.setOptions({ breaks: true })

function normalizeSoftTildes(text: string): string {
  let result = ''
  for (let i = 0; i < text.length; i++) {
    const char = text[i]
    if (char === '~' && text[i - 1] !== '~' && text[i + 1] !== '~') {
      result += '～'
    } else {
      result += char
    }
  }
  return result
}

function renderMarkdown(text: string): string {
  const html = marked.parse(normalizeSoftTildes(text)) as string
  return DOMPurify.sanitize(html)
}

function createClientSessionId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
}

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const sessionStore = useSessionStore()
const authStore = useAuthStore()
const { connect, disconnect, onMessage, setMicMuted, voiceEnabled, toggleVoice, vadInterruptEnabled, toggleVadInterrupt, interruptResponse } = useWebRTC()
const { messages, streamingMessage, taskProgress, assistantProcessText, handleServerMessage, addLocalUserMessage, startAssistantPending, clearAssistantPending, stopAssistantOutput, clearTaskProgress, resetChat, replaceMessages } = useChat()

const audienceFromRoute = route.params.audience as string
if (audienceFromRoute && audienceFromRoute !== sessionStore.selectedAudience) {
  sessionStore.setAudience(audienceFromRoute)
}

const inputText = ref('')
const inputMode = ref<'text' | 'ptt'>('text')
const isRealtimeChatOn = ref(false)
const isHoldingToTalk = ref(false)
const isVoiceChannelOpen = ref(false)
const messagesContainer = ref<HTMLElement | null>(null)
const statusPanelOpen = ref(false)
const sideDrawerOpen = ref(false)
const privateSpaceOpen = ref(false)
const skillCenterOpen = ref(false)
const subscriptionOpen = ref(false)
const showLoginModal = ref(false)
const showRegisterModal = ref(false)
const showAllDialog = ref(false)
const renameDialogOpen = ref(false)
const renameTarget = ref<{ sessionId: string; title: string } | null>(null)
const sendError = ref('')
const isSendingText = ref(false)
const isRetryingTask = ref(false)
const isStoppingResponse = ref(false)
const isSpeechRecording = ref(false)
const isSpeechTranscribing = ref(false)
const textChatSessionId = ref('')
const activeConversationId = ref('')
const isConversationHydrating = ref(false)
const keyboardInset = ref(0)
const viewportWidth = ref(typeof window !== 'undefined' ? window.innerWidth : 1024)
const isMobileUa = ref(false)
const isDesktopStageCollapsed = ref(false)
const isVrmDisabled = computed(() => isVrmDisabledByEnv)
let sendErrorTimer: ReturnType<typeof setTimeout> | null = null
let speechAudioContext: AudioContext | null = null
let speechSource: MediaStreamAudioSourceNode | null = null
let speechProcessor: ScriptProcessorNode | null = null
let speechProcessingDestination: MediaStreamAudioDestinationNode | null = null
let speechStream: MediaStream | null = null
let speechChunks: Float32Array[] = []
let speechInputSampleRate = 48000
let speechStartedAt = 0
let speechCaptureRequestId = 0
let textProgressEventSource: EventSource | null = null
let textProgressEventSessionId = ''
let textProgressReadyPromise: Promise<void> | null = null
let textMessageAbortController: AbortController | null = null
let quickActionAbortController: AbortController | null = null
let quickActionRefreshTimer: ReturnType<typeof setTimeout> | null = null
let quickActionRequestSeq = 0
let weatherRefreshTimer: ReturnType<typeof setInterval> | null = null
let emotionDebugResetTimer: ReturnType<typeof setTimeout> | null = null
let messagesScrollFrameId: number | null = null

const TITLE_MAX_CHARS = 15
const SPEECH_LOG_PREFIX = '[SpeechInput]'
const WEATHER_REFRESH_MS = 60 * 60 * 1000
const QUICK_ACTION_REFRESH_DELAY_MS = 360
const QUICK_ACTION_REQUEST_TIMEOUT_MS = 8000

const routeConversationId = computed(() => {
  const value = route.params.conversationId
  return Array.isArray(value) ? value[0] || '' : String(value || '')
})
const isGuestRoute = computed(() => routeConversationId.value === 'guest')
const isGuestMode = computed(() => !authStore.isLoggedIn || isGuestRoute.value)

function authJsonHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (authStore.token) headers.Authorization = `Bearer ${authStore.token}`
  return headers
}

function makeDebugEmotionState(
  label: string,
  scores: Partial<Pick<EmotionState, 'sadness' | 'anxiety' | 'anger'>> = {},
): EmotionState {
  return {
    sadness: scores.sadness ?? 0,
    anxiety: scores.anxiety ?? 0,
    anger: scores.anger ?? 0,
    label,
    keywords: [`debug:${label}`],
  }
}

const emotionDebugOptions: EmotionDebugOption[] = [
  { label: 'neutral', title: '中性', source: 'frontend/backend', icon: 'i-carbon-face-neutral', state: makeDebugEmotionState('neutral') },
  { label: 'happy', title: '开心', source: 'frontend', icon: 'i-carbon-face-satisfied', state: makeDebugEmotionState('happy') },
  { label: 'joy', title: '喜悦', source: 'frontend', icon: 'i-carbon-face-activated', state: makeDebugEmotionState('joy') },
  { label: 'calm', title: '平静', source: 'frontend', icon: 'i-carbon-face-cool', state: makeDebugEmotionState('calm') },
  { label: 'relaxed', title: '放松', source: 'frontend', icon: 'i-carbon-face-cool', state: makeDebugEmotionState('relaxed') },
  { label: 'sad', title: '伤心', source: 'frontend/backend', icon: 'i-carbon-face-dissatisfied', state: makeDebugEmotionState('sad', { sadness: 0.8 }) },
  { label: 'sorrow', title: '哀伤', source: 'frontend', icon: 'i-carbon-face-dissatisfied', state: makeDebugEmotionState('sorrow', { sadness: 0.85 }) },
  { label: 'missing_someone', title: '想念', source: 'backend', icon: 'i-carbon-favorite', state: makeDebugEmotionState('missing_someone', { sadness: 0.85 }) },
  { label: 'lonely', title: '孤独', source: 'backend', icon: 'i-carbon-user-favorite-alt', state: makeDebugEmotionState('lonely', { sadness: 0.75 }) },
  { label: 'anxious', title: '焦虑', source: 'backend', icon: 'i-carbon-warning-alt', state: makeDebugEmotionState('anxious', { anxiety: 0.85 }) },
  { label: 'angry', title: '生气', source: 'frontend/stt', icon: 'i-carbon-warning-filled', state: makeDebugEmotionState('angry', { anger: 0.85 }) },
  { label: 'surprise', title: '惊讶', source: 'frontend', icon: 'i-carbon-face-wink', state: makeDebugEmotionState('surprise', { anxiety: 0.65 }) },
  { label: 'urgent', title: '紧急', source: 'backend', icon: 'i-carbon-alarm', state: makeDebugEmotionState('urgent', { anxiety: 0.95, anger: 0.15 }) },
]

function handleDebugEmotionSelect(option: EmotionDebugOption) {
  if (emotionDebugResetTimer !== null) {
    clearTimeout(emotionDebugResetTimer)
    emotionDebugResetTimer = null
  }

  sessionStore.updateEmotionState({
    ...option.state,
    keywords: [...option.state.keywords],
  })

  emotionDebugResetTimer = setTimeout(() => {
    sessionStore.updateEmotionState(makeDebugEmotionState(EMOTION_FALLBACK_LABEL))
    emotionDebugResetTimer = null
  }, EMOTION_STATE_HOLD_MS)
}

function resetDebugEmotion() {
  if (emotionDebugResetTimer !== null) {
    clearTimeout(emotionDebugResetTimer)
    emotionDebugResetTimer = null
  }
  sessionStore.updateEmotionState(makeDebugEmotionState(EMOTION_FALLBACK_LABEL))
}

function scheduleMessagesScrollToBottom() {
  if (messagesScrollFrameId !== null) return
  messagesScrollFrameId = window.requestAnimationFrame(() => {
    messagesScrollFrameId = null
    void nextTick(() => {
      const container = messagesContainer.value
      if (!container) return
      container.scrollTop = container.scrollHeight
    })
  })
}

interface WeatherInfo {
  city: string
  temp: string
  condition: string
  icon: string
}

function formatConversationTitle(title: string): string {
  if (!title) return '新对话'
  const chars = Array.from(title)
  return chars.length > TITLE_MAX_CHARS ? `${chars.slice(0, TITLE_MAX_CHARS).join('')}...` : title
}

interface RawSession {
  id: number
  sessionId: string
  icon: string
  title: string
  time: string
  preview?: string
  active?: boolean
  starred?: boolean
}

interface ArchivedConversation extends RawSession {
  messages: ChatMessage[]
  messageCount: number
  updatedAt: number
}

interface ConversationRecord {
  conversation_id: string
  title: string
  preview?: string
  updated_at?: string
  created_at?: string
  last_session_id?: string
  message_count?: number
}

interface ConversationMessageRecord {
  id: string
  role: 'user' | 'assistant'
  content: string
  source?: string
  artifact?: Record<string, unknown> | null
  created_at?: string
}

interface ConversationArchiveOptions {
  preserveOrder?: boolean
}

const CONVERSATION_TITLE_OVERRIDES_KEY = 'soulmeet.chat.conversationTitleOverrides.v1'
const GUEST_RUNTIME_SESSION_KEY = 'soulmeet.chat.guestRuntimeSessionId.v1'

const ARCHIVE_PREVIEW_MESSAGE_LIMIT = 8

function cloneMessagesForArchive(source: ChatMessage[], limit = ARCHIVE_PREVIEW_MESSAGE_LIMIT): ChatMessage[] {
  return source
    .filter(message => getChatMessageText(message).trim())
    .slice(-limit)
    .map(message => ({
      id: message.id,
      role: message.role,
      text: getChatMessageText(message),
      contentBlocks: message.contentBlocks?.map(block => ({ ...block })),
      source: message.source,
      timestamp: new Date(message.timestamp),
      artifact: message.artifact,
    }))
}

function persistArchivedConversations() {
  // 登录用户的对话列表以数据库为准；访客不创建左侧列表。
}

function restoreConversationTitleOverrides(): Record<string, string> {
  if (typeof window === 'undefined') return {}
  try {
    const raw = window.localStorage.getItem(CONVERSATION_TITLE_OVERRIDES_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as Record<string, unknown>
    return Object.fromEntries(
      Object.entries(parsed)
        .map(([sessionId, title]) => [sessionId, String(title || '').trim()] as const)
        .filter(([sessionId, title]) => sessionId && title),
    )
  } catch (err) {
    console.warn('[Conversations] 读取自定义对话名称失败:', err)
    return {}
  }
}

const conversationTitleOverrides = ref<Record<string, string>>(restoreConversationTitleOverrides())

function persistConversationTitleOverrides() {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(CONVERSATION_TITLE_OVERRIDES_KEY, JSON.stringify(conversationTitleOverrides.value))
  } catch (err) {
    console.warn('[Conversations] 保存自定义对话名称失败:', err)
  }
}

function resolveConversationTitle(sessionId: string, fallback: string): string {
  return conversationTitleOverrides.value[sessionId]?.trim() || fallback || '新对话'
}

function deriveConversationTitle(source: ChatMessage[]): string {
  return source.find(message => message.role === 'user')?.text.trim() || '新对话'
}

function deriveConversationPreview(source: ChatMessage[]): string {
  const latest = [...source].reverse().find(message => getChatMessageText(message).trim())
  return latest ? getChatMessageText(latest).trim() : ''
}

function upsertConversationArchive(sessionId: string, sourceMessages: ChatMessage[], options: ConversationArchiveOptions = {}) {
  if (!authStore.isLoggedIn) return
  const archivedMessages = cloneMessagesForArchive(sourceMessages)
  if (!sessionId || archivedMessages.length === 0) return

  const updatedAt = Date.now()
  const existingIndex = conversationArchives.value.findIndex(item => item.sessionId === sessionId)
  const existingArchive = existingIndex >= 0 ? conversationArchives.value[existingIndex] : undefined
  const archive: ArchivedConversation = {
    id: 1,
    sessionId,
    icon: 'i-carbon-chat',
    title: resolveConversationTitle(sessionId, deriveConversationTitle(sourceMessages)),
    time: formatTime(new Date(updatedAt)),
    preview: deriveConversationPreview(sourceMessages),
    active: false,
    starred: existingArchive?.starred ?? false,
    messages: archivedMessages,
    messageCount: sourceMessages.filter(message => getChatMessageText(message).trim()).length,
    updatedAt,
  }

  if (options.preserveOrder && existingIndex >= 0) {
    conversationArchives.value = conversationArchives.value.map((item, index) => ({
      ...(index === existingIndex ? archive : item),
      id: index + 1,
      active: false,
    }))
    persistArchivedConversations()
    return
  }

  const withoutSame = conversationArchives.value.filter(item => item.sessionId !== sessionId)
  conversationArchives.value = [archive, ...withoutSame].map((item, index) => ({
    ...item,
    id: index + 1,
    active: false,
  }))
  persistArchivedConversations()
}

function archiveCurrentConversation(options: ConversationArchiveOptions = {}) {
  const sessionId = activeConversationId.value
  if (!sessionId) return
  upsertConversationArchive(sessionId, messages.value, options)
}

function removeConversationArchive(sessionId: string) {
  conversationArchives.value = conversationArchives.value
    .filter(item => item.sessionId !== sessionId)
    .map((item, index) => ({
      ...item,
      id: index + 1,
      active: false,
    }))
  persistArchivedConversations()
}

function conversationRecordToArchive(item: ConversationRecord, messagesForItem: ChatMessage[] = []): ArchivedConversation {
  const updatedAt = item.updated_at ? new Date(item.updated_at).getTime() : Date.now()
  const previewMessages = cloneMessagesForArchive(messagesForItem)
  return {
    id: 1,
    sessionId: item.conversation_id,
    icon: 'i-carbon-chat',
    title: item.title || '新对话',
    time: formatTime(new Date(updatedAt)),
    preview: item.preview || '',
    active: false,
    starred: false,
    updatedAt,
    messages: previewMessages,
    messageCount: item.message_count ?? messagesForItem.filter(message => getChatMessageText(message).trim()).length,
  }
}

function apiMessageToChatMessage(item: ConversationMessageRecord): ChatMessage {
  const text = item.content
  return {
    id: item.id,
    role: item.role,
    text,
    contentBlocks: item.role === 'assistant' && text.trim()
      ? [{
          id: 'main',
          type: 'markdown',
          text,
          source: item.source || undefined,
        }]
      : undefined,
    source: item.source || undefined,
    timestamp: item.created_at ? new Date(item.created_at) : new Date(),
    artifact: item.artifact || undefined,
  }
}

async function loadConversationList() {
  if (!authStore.isLoggedIn) {
    conversationArchives.value = []
    return
  }
  const response = await fetch(apiUrl(`/api/conversations?audience=${encodeURIComponent(sessionStore.selectedAudience)}`), {
    headers: authJsonHeaders(),
  })
  if (!response.ok) {
    throw new Error(`读取对话列表失败: ${response.status}`)
  }
  const items = await response.json() as ConversationRecord[]
  conversationArchives.value = items.map((item, index) => ({
    ...conversationRecordToArchive(item),
    id: index + 1,
  }))
}

async function createLoggedConversation(): Promise<ArchivedConversation> {
  const response = await fetch(apiUrl('/api/conversations'), {
    method: 'POST',
    headers: authJsonHeaders(),
    body: JSON.stringify({
      audience: sessionStore.selectedAudience,
      title: '新对话',
    }),
  })
  if (!response.ok) {
    throw new Error(`创建对话失败: ${response.status}`)
  }
  const record = await response.json() as ConversationRecord
  const archive = conversationRecordToArchive(record)
  conversationArchives.value = [archive, ...conversationArchives.value.filter(item => item.sessionId !== archive.sessionId)]
    .map((item, index) => ({ ...item, id: index + 1, active: false }))
  return archive
}

async function loadConversationDetail(conversationId: string) {
  if (!authStore.isLoggedIn || !conversationId || conversationId === 'guest') return
  isConversationHydrating.value = true
  try {
    const response = await fetch(apiUrl(`/api/conversations/${encodeURIComponent(conversationId)}`), {
      headers: authJsonHeaders(),
    })
    if (!response.ok) {
      if (response.status === 404) {
        const created = await createLoggedConversation()
        await router.replace(`/chat/${sessionStore.selectedAudience}/${created.sessionId}`)
        return
      }
      throw new Error(`读取对话失败: ${response.status}`)
    }
    const data = await response.json() as { conversation: ConversationRecord; messages: ConversationMessageRecord[] }
    const restoredMessages = data.messages.map(apiMessageToChatMessage)
    activeConversationId.value = data.conversation.conversation_id
    textChatSessionId.value = data.conversation.last_session_id || createClientSessionId()
    sessionStore.setSessionInfo({
      sessionId: textChatSessionId.value,
      audience: sessionStore.selectedAudience,
      currentNode: '',
      connectedAt: new Date().toISOString(),
    })
    replaceMessages(restoredMessages)
    const archive = conversationRecordToArchive(data.conversation, restoredMessages)
    conversationArchives.value = [archive, ...conversationArchives.value.filter(item => item.sessionId !== archive.sessionId)]
      .map((item, index) => ({ ...item, id: index + 1, active: false }))
  } finally {
    isConversationHydrating.value = false
  }
}

async function ensureLoggedConversation(): Promise<string> {
  if (!authStore.isLoggedIn) return ''
  if (activeConversationId.value && activeConversationId.value !== 'guest') {
    return activeConversationId.value
  }
  const created = await createLoggedConversation()
  activeConversationId.value = created.sessionId
  await router.replace(`/chat/${sessionStore.selectedAudience}/${created.sessionId}`)
  return created.sessionId
}

function resetGuestRuntime() {
  const previousGuestSessionId = typeof window !== 'undefined'
    ? window.sessionStorage.getItem(GUEST_RUNTIME_SESSION_KEY) || ''
    : ''
  closeTextProgressEvents()
  disconnect()
  resetChat()
  inputText.value = ''
  activeConversationId.value = ''
  textChatSessionId.value = createClientSessionId()
  conversationArchives.value = []
  const audience = sessionStore.selectedAudience
  sessionStore.reset()
  sessionStore.setAudience(audience)
  sessionStore.setSessionInfo({
    sessionId: textChatSessionId.value,
    audience,
    currentNode: '',
    connectedAt: new Date().toISOString(),
  })
  if (typeof window !== 'undefined') {
    window.sessionStorage.setItem(GUEST_RUNTIME_SESSION_KEY, textChatSessionId.value)
  }
  if (previousGuestSessionId && previousGuestSessionId !== textChatSessionId.value) {
    void fetch(apiUrl(`/api/text-runtime/session/${encodeURIComponent(previousGuestSessionId)}?preserve_db=true`), {
      method: 'DELETE',
    }).catch((err) => {
      console.warn('[Conversations] 清理访客运行态失败:', err)
    })
  }
}

const conversationArchives = ref<ArchivedConversation[]>([])

const displayedSessions = computed(() => {
  if (!authStore.isLoggedIn) return []
  const activeSessionId = activeConversationId.value
  const currentSession = activeSessionId
    ? {
        id: 0,
        sessionId: activeSessionId,
        icon: 'i-carbon-chat',
        title: resolveConversationTitle(activeSessionId, deriveConversationTitle(messages.value)),
        time: messages.value.length ? formatTime(messages.value[messages.value.length - 1].timestamp) : '刚刚',
        preview: deriveConversationPreview(messages.value),
        active: true,
      }
    : null

  const archived = conversationArchives.value.map(item => {
    if (item.sessionId !== activeSessionId) {
      return {
        ...item,
        title: resolveConversationTitle(item.sessionId, item.title),
        active: false,
      }
    }
    return {
      ...item,
      title: currentSession?.title || resolveConversationTitle(item.sessionId, item.title),
      time: currentSession?.time || item.time,
      preview: currentSession?.preview || item.preview,
      active: true,
    }
  })
  const hasActiveArchive = !!activeSessionId && conversationArchives.value.some(item => item.sessionId === activeSessionId)
  const sessions = currentSession && !hasActiveArchive ? [currentSession, ...archived] : archived
  return sessions.slice(0, 5).map(item => ({
    ...item,
    displayTitle: formatConversationTitle(item.title),
  }))
})
const hasMoreSessions = computed(() => {
  if (!authStore.isLoggedIn) return false
  const activeSessionId = activeConversationId.value
  const hasActiveArchive = !!activeSessionId && conversationArchives.value.some(item => item.sessionId === activeSessionId)
  return conversationArchives.value.length + (activeSessionId && !hasActiveArchive ? 1 : 0) > 5
})

const allConversationModalItems = computed(() => conversationArchives.value.map((item) => {
    const userMessages = item.messages.filter(message => message.role === 'user')
    const recentMessages = item.messages.slice(-4).map(message => ({
    role: message.role,
    name: message.role === 'assistant' ? 'Aini' : '你',
    time: formatTime(message.timestamp),
    text: message.text,
  }))
  return {
    id: item.sessionId,
    icon: '💬',
    title: item.title,
    time: item.time,
    createdAt: formatTime(new Date(item.updatedAt)),
    updatedAt: item.updatedAt,
    category: '陪伴对话',
    type: '聊天',
    rounds: Math.max(userMessages.length, Math.ceil(item.messageCount / 2)),
    starred: !!item.starred,
    summary: item.preview || item.title,
    detailSummary: item.preview || '这是一段你和 Aini 的对话记录。',
    keyInfo: [
      { label: '会话 ID', value: item.sessionId.slice(0, 8) },
      { label: '消息数', value: `${item.messageCount} 条` },
    ],
    recentMessages,
  }
}))

const quickActions = ref<string[]>(createDefaultQuickActions())

const weather = ref({
  city: '定位中',
  temp: '--°C',
  condition: '天气更新中',
  icon: 'i-carbon-partly-cloudy',
} satisfies WeatherInfo)

const WEATHER_CONDITION_ZH: Record<string, string> = {
  sunny: '晴',
  clear: '晴',
  'partly cloudy': '局部多云',
  cloudy: '多云',
  overcast: '阴',
  mist: '薄雾',
  fog: '雾',
  'freezing fog': '冻雾',
  'patchy rain possible': '局部有雨',
  'patchy light rain': '局部小雨',
  'light rain': '小雨',
  'moderate rain': '中雨',
  'heavy rain': '大雨',
  'rain shower': '阵雨',
  'light rain shower': '小阵雨',
  'moderate or heavy rain shower': '阵雨较强',
  'thundery outbreaks possible': '可能有雷雨',
  'patchy snow possible': '局部有雪',
  'light snow': '小雪',
  'moderate snow': '中雪',
  'heavy snow': '大雪',
  'light sleet': '小雨夹雪',
  'moderate or heavy sleet': '雨夹雪较强',
}

function localizeWeatherCondition(condition?: string): string {
  const source = condition?.trim()
  if (!source) return ''
  if (/[\u4e00-\u9fa5]/.test(source)) return source
  return WEATHER_CONDITION_ZH[source.toLowerCase().replace(/\s+/g, ' ')] || '天气更新中'
}

function weatherIconForCondition(...conditions: Array<string | undefined>): string {
  const source = conditions
    .map(condition => condition?.trim())
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
  if (!source) return 'i-carbon-partly-cloudy'
  if (/(雷|thunder)/.test(source)) return 'i-carbon-thunderstorm'
  if (/(雨夹雪|sleet)/.test(source)) return 'i-carbon-sleet'
  if (/(雪|snow)/.test(source)) return 'i-carbon-snow'
  if (/(冻雨|冰雨|freezing rain|hail|ice)/.test(source)) return 'i-carbon-sleet'
  if (/(毛毛雨|小雨|drizzle)/.test(source)) return 'i-carbon-rain-drizzle'
  if (/(雨|阵雨|rain|shower)/.test(source)) return 'i-carbon-rain'
  if (/(雾|薄雾|fog|mist)/.test(source)) return 'i-carbon-fog'
  if (/(霾|haze|smog)/.test(source)) return 'i-carbon-haze'
  if (/(阴|overcast)/.test(source)) return 'i-carbon-cloudy'
  if (/(多云|局部多云|cloudy|partly cloudy|mostly cloudy)/.test(source)) return 'i-carbon-partly-cloudy'
  if (/(晴|sunny|clear)/.test(source)) return 'i-carbon-sun'
  return 'i-carbon-partly-cloudy'
}

const stageBackgroundUrl = computed(() => {
  if (sessionStore.selectedAudience === 'Aini') {
    return apiUrl('/api/audiences/Aini/background/3.png')
  }
  return '/k5.jpg'
})

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '')
}

function audienceCdnModelUrl(audience: string): string {
  const exactUrl = audience === 'Aini'
    ? import.meta.env.VITE_AINI_VRM_URL
    : audience === 'Liyin'
      ? import.meta.env.VITE_LIYIN_VRM_URL
      : ''
  if (exactUrl) return exactUrl

  const baseUrl = import.meta.env.VITE_VRM_ASSET_BASE_URL
  if (!baseUrl) return ''
  return `${trimTrailingSlash(baseUrl)}/${encodeURIComponent(audience)}/model.vrm`
}

const modelUrl = computed(() => {
  const cdnUrl = audienceCdnModelUrl(sessionStore.selectedAudience)
  if (cdnUrl) {
    return cdnUrl
  }
  if (sessionStore.audienceVrmUrl) {
    return sessionStore.audienceVrmUrl
  }
  return apiUrl(`/api/audiences/${sessionStore.selectedAudience}/assets/model.vrm`)
})

const botAvatarUrl = computed(() => apiUrl(`/api/audiences/${sessionStore.selectedAudience}/assets/head_avatar.png`))
const botDisplayName = computed(() => sessionStore.selectedAudience)
const userAvatarUrl = computed(() => {
  const avatarUrl = authStore.user?.avatarUrl
  if (!authStore.isLoggedIn || !avatarUrl) return '/default_head.png'
  return avatarUrl.startsWith('http') || avatarUrl.startsWith('/') || avatarUrl.startsWith('data:')
    ? avatarUrl
    : apiUrl(avatarUrl)
})
const userDisplayName = computed(() => {
  if (!authStore.isLoggedIn || !authStore.user) return '未登入'
  return authStore.user.displayName || authStore.user.username
})
const userAccountName = computed(() => {
  if (!authStore.isLoggedIn || !authStore.user) return '未登入'
  return authStore.user.username
})
const userSubscriptionLabel = computed(() => authStore.isLoggedIn ? 'PRO Lv.3' : '未登入')

const connectionIndicator = computed(() => {
  if (!isVoiceChannelOpen.value) {
    return { color: 'bg-yellow-400', ring: 'ring-yellow-300', label: '文本可用 · 语音通道关', pulse: false }
  }

  switch (sessionStore.status) {
    case 'connected':
      return { color: 'bg-green-500', ring: 'ring-green-300', label: '语音已连接', pulse: false }
    case 'connecting':
      return { color: 'bg-yellow-400', ring: 'ring-yellow-300', label: '文本可用 · 语音连接中', pulse: true }
    case 'error':
      return {
        color: 'bg-yellow-400',
        ring: 'ring-yellow-300',
        label: '文本可用 · 语音异常',
        pulse: false,
      }
    case 'disconnected':
    case 'idle':
    default:
      return { color: 'bg-yellow-400', ring: 'ring-yellow-300', label: '文本可用 · 语音未连接', pulse: false }
  }
})

const conversationRounds = computed(() => buildConversationRounds(messages.value, formatTime))

const recentConversationRounds = computed(() => conversationRounds.value.slice(-2).reverse())
const desktopEmotionState = computed<EmotionState>(() => (
  isDesktopStageCollapsed.value
    ? {
        sadness: 0,
        anxiety: 0,
        anger: 0,
        label: EMOTION_FALLBACK_LABEL,
        keywords: ['stage:collapsed'],
      }
    : sessionStore.emotionState
))
const desktopStreamingMessage = computed<ChatMessage | null>(() => (
  isDesktopStageCollapsed.value ? null : streamingMessage.value
))

const isBotResponding = computed(() => {
  return isSendingText.value
    || isRetryingTask.value
    || isStoppingResponse.value
    || Boolean(streamingMessage.value?.streaming)
    || Boolean(streamingMessage.value?.pending)
})

const isMobileLayout = computed(() => isMobileUa.value || viewportWidth.value < 768)
const canReconnect = computed(() => {
  return !!sessionStore.sessionInfo?.sessionId
    && (sessionStore.status === 'disconnected' || sessionStore.status === 'error')
})

watch(isMobileLayout, (isMobile) => {
  if (isMobile) {
    isDesktopStageCollapsed.value = false
  }
})

function setMessagesContainer(el: Element | ComponentPublicInstance | null) {
  messagesContainer.value = el instanceof HTMLElement ? el : null
}

function formatTime(date: Date): string {
  return `${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`
}

function showSendError(message: string) {
  sendError.value = message
  if (sendErrorTimer !== null) {
    clearTimeout(sendErrorTimer)
  }
  sendErrorTimer = setTimeout(() => {
    sendError.value = ''
    sendErrorTimer = null
  }, 2500)
}

class TextChannelError extends Error {
  constructor(public status: number) {
    const message = status >= 500
      ? '文本服务暂时没有连接上，请确认后端已启动后再试。'
      : `文本主通道响应错误: ${status}`
    super(message)
  }
}

function textSendErrorMessage(err: unknown): string {
  if (err instanceof TextChannelError) return err.message
  if (err instanceof TypeError) return '文本服务暂时没有连接上，请确认后端已启动后再试。'
  return err instanceof Error ? err.message : '文本发送失败，请稍后重试'
}

function isAbortError(err: unknown): boolean {
  return err instanceof DOMException && err.name === 'AbortError'
}

function clearQuickActionRefreshTimer() {
  if (quickActionRefreshTimer !== null) {
    clearTimeout(quickActionRefreshTimer)
    quickActionRefreshTimer = null
  }
}

function stopQuickActionRequest() {
  clearQuickActionRefreshTimer()
  quickActionAbortController?.abort()
  quickActionAbortController = null
}

async function refreshQuickActionsFromLlm() {
  clearQuickActionRefreshTimer()
  const requestSeq = ++quickActionRequestSeq
  quickActionAbortController?.abort()

  const controller = new AbortController()
  quickActionAbortController = controller
  const timeoutTimer = setTimeout(() => controller.abort(), QUICK_ACTION_REQUEST_TIMEOUT_MS)

  try {
    const response = await fetch(apiUrl('/api/quick-actions/suggestions'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
      body: JSON.stringify({
        audience: sessionStore.selectedAudience,
        messages: buildQuickActionMessages(messages.value),
        limit: 4,
      }),
    })
    if (!response.ok) return
    const data = await response.json() as { actions?: unknown }
    const actions = sanitizeQuickActionSuggestions(data.actions)
    if (requestSeq !== quickActionRequestSeq || controller.signal.aborted) return
    if (actions.length) {
      quickActions.value = actions
    }
  } catch (err) {
    if (!isAbortError(err)) {
      console.warn('[QuickActions] 提示气泡生成失败:', err)
    }
  } finally {
    clearTimeout(timeoutTimer)
    if (quickActionAbortController === controller) {
      quickActionAbortController = null
    }
  }
}

function scheduleQuickActionRefresh(delay = QUICK_ACTION_REFRESH_DELAY_MS) {
  clearQuickActionRefreshTimer()
  quickActionRefreshTimer = setTimeout(() => {
    quickActionRefreshTimer = null
    void refreshQuickActionsFromLlm()
  }, delay)
}

function ensureTextRuntimeSession(): string {
  const existingSessionId = sessionStore.sessionInfo?.sessionId || textChatSessionId.value
  if (existingSessionId) {
    textChatSessionId.value = existingSessionId
    return existingSessionId
  }

  const sessionId = createClientSessionId()
  textChatSessionId.value = sessionId
  sessionStore.setSessionInfo({
    sessionId,
    audience: sessionStore.selectedAudience,
    currentNode: '',
    connectedAt: new Date().toISOString(),
  })
  return sessionId
}

function closeTextProgressEvents() {
  if (textProgressEventSource) {
    textProgressEventSource.close()
    textProgressEventSource = null
  }
  textProgressEventSessionId = ''
  textProgressReadyPromise = null
}

function openTextProgressEvents(sessionId: string): Promise<void> {
  if (typeof EventSource === 'undefined') return Promise.resolve()
  if (
    textProgressEventSource
    && textProgressEventSessionId === sessionId
    && textProgressEventSource.readyState !== EventSource.CLOSED
  ) {
    return textProgressEventSource.readyState === EventSource.OPEN
      ? Promise.resolve()
      : textProgressReadyPromise || Promise.resolve()
  }

  closeTextProgressEvents()
  const params = new URLSearchParams({
    audience: sessionStore.selectedAudience,
  })
  if (authStore.token) {
    params.set('token', authStore.token)
  }
  if (activeConversationId.value) {
    params.set('conversation_id', activeConversationId.value)
  }
  const source = new EventSource(apiUrl(`/api/text-runtime/events/${encodeURIComponent(sessionId)}?${params.toString()}`))
  textProgressEventSource = source
  textProgressEventSessionId = sessionId

  let readySettled = false
  let readyTimer: ReturnType<typeof setTimeout> | null = null
  const readyPromise = new Promise<void>((resolve) => {
    const settleReady = () => {
      if (readySettled) return
      readySettled = true
      if (readyTimer !== null) {
        clearTimeout(readyTimer)
        readyTimer = null
      }
      resolve()
    }

    readyTimer = setTimeout(settleReady, 700)
    source.onopen = settleReady
    source.onerror = () => {
      if (source.readyState === EventSource.CLOSED) {
        settleReady()
      }
    }
    source.onmessage = (event) => {
      if (!event.data) return
      try {
        const msg = JSON.parse(event.data) as { type?: string }
        if (msg.type === 'text_progress_connected') {
          settleReady()
          return
        }
        if (
          msg.type === 'assistant_process'
          || msg.type === 'task_progress'
          || msg.type === 'assistant_text'
          || msg.type === 'assistant_message_start'
          || msg.type === 'assistant_sources'
          || msg.type === 'content_block_start'
          || msg.type === 'content_block_delta'
          || msg.type === 'content_block_finish'
          || msg.type === 'assistant_message_finish'
          || msg.type === 'assistant_text_interrupted'
        ) {
          handleServerMessage(msg as ServerMessage)
        }
      } catch (err) {
        console.warn('[TextProgress] 进度消息解析失败:', err, '原始数据:', event.data)
      }
    }
  })
  textProgressReadyPromise = readyPromise
  return readyPromise
}

async function refreshWeather() {
  try {
    const params = new URLSearchParams({
      audience: sessionStore.selectedAudience,
    })
    const response = await fetch(apiUrl(`/api/weather/current?${params.toString()}`), {
      cache: 'no-store',
    })
    if (!response.ok) return
    const data = await response.json() as Partial<WeatherInfo>
    const condition = localizeWeatherCondition(data.condition) || weather.value.condition
    weather.value = {
      city: data.city || weather.value.city,
      temp: data.temp || weather.value.temp,
      condition,
      icon: weatherIconForCondition(condition, data.condition),
    }
  } catch (err) {
    console.warn('[Weather] 天气刷新失败:', err)
  }
}

async function sendChatMessage(text: string) {
  if (authStore.isLoggedIn) {
    await ensureLoggedConversation()
  }
  const sessionId = ensureTextRuntimeSession()
  await openTextProgressEvents(sessionId)
  const controller = new AbortController()
  textMessageAbortController = controller

  try {
    const response = await fetch(apiUrl('/api/text-runtime/message'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
      body: JSON.stringify({
        text,
        audience: sessionStore.selectedAudience,
        session_id: sessionId,
        conversation_id: activeConversationId.value || undefined,
        timeout_seconds: textRuntimeTimeoutSeconds,
        token: authStore.token ?? '',
      }),
    })
    if (!response.ok) {
      throw new TextChannelError(response.status)
    }
    const data = await response.json() as {
      session_id: string
      conversation_id: string
      audience: string
      text: string
      source: string
      artifact?: Record<string, unknown>
    }
    textChatSessionId.value = data.session_id
    activeConversationId.value = data.conversation_id || activeConversationId.value
    if (!sessionStore.sessionInfo || sessionStore.sessionInfo.sessionId !== data.session_id) {
      sessionStore.setSessionInfo({
        sessionId: data.session_id,
        audience: data.audience,
        currentNode: '',
        connectedAt: new Date().toISOString(),
      })
    }
    if (data.source !== 'interrupted' || data.text.trim()) {
      handleServerMessage({ type: 'assistant_text', text: data.text, source: data.source, artifact: data.artifact || undefined })
    }
    upsertConversationArchive(activeConversationId.value, messages.value)
  } finally {
    if (textMessageAbortController === controller) {
      textMessageAbortController = null
    }
  }
}

async function interruptTextRuntimeSession(sessionId: string) {
  if (!sessionId) return
  const response = await fetch(apiUrl(`/api/text-runtime/session/${encodeURIComponent(sessionId)}/interrupt`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      audience: sessionStore.selectedAudience,
      conversation_id: activeConversationId.value || undefined,
      token: authStore.token ?? '',
    }),
  })
  if (!response.ok) {
    throw new TextChannelError(response.status)
  }
}

async function retryTextRuntimeTask(item: TaskProgressItem) {
  const retryToken = item.retryToken
  const sessionId = sessionStore.sessionInfo?.sessionId || textChatSessionId.value
  if (!retryToken || !sessionId) {
    showSendError('这次失败信息已失效，请重新发起任务')
    return
  }
  if (isRetryingTask.value) return

  openTextProgressEvents(sessionId)
  isRetryingTask.value = true
  try {
    const response = await fetch(apiUrl(`/api/text-runtime/session/${encodeURIComponent(sessionId)}/task-retry`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        audience: sessionStore.selectedAudience,
        conversation_id: activeConversationId.value || undefined,
        token: authStore.token ?? '',
        retry_token: retryToken,
        timeout_seconds: textRuntimeTimeoutSeconds,
      }),
    })
    if (!response.ok) {
      throw new TextChannelError(response.status)
    }
    const data = await response.json() as {
      session_id: string
      conversation_id: string
      audience: string
      text: string
      source: string
      artifact?: Record<string, unknown>
    }
    textChatSessionId.value = data.session_id
    activeConversationId.value = data.conversation_id || activeConversationId.value
    if (!sessionStore.sessionInfo || sessionStore.sessionInfo.sessionId !== data.session_id) {
      sessionStore.setSessionInfo({
        sessionId: data.session_id,
        audience: data.audience,
        currentNode: '',
        connectedAt: new Date().toISOString(),
      })
    }
    if (data.text.trim()) {
      handleServerMessage({
        type: 'assistant_text',
        text: data.text,
        source: data.source || 'task_retry',
        artifact: data.artifact || undefined,
      })
    }
    if (activeConversationId.value) {
      upsertConversationArchive(activeConversationId.value, messages.value)
    }
  } catch (err) {
    const message = err instanceof TextChannelError && err.status === 404
      ? '重试信息已过期，请重新发起任务'
      : err instanceof TextChannelError && err.status === 409
        ? '这次失败不能继续重试，请重新发起任务'
        : '重试失败，请稍后再试'
    showSendError(message)
    console.warn('[Chat] 任务重试失败:', err)
  } finally {
    isRetryingTask.value = false
  }
}

async function handleStopBotResponse() {
  if (!isBotResponding.value || isStoppingResponse.value) {
    return
  }

  const sessionId = sessionStore.sessionInfo?.sessionId || textChatSessionId.value
  isStoppingResponse.value = true
  stopAssistantOutput()
  clearTaskProgress()
  textMessageAbortController?.abort()
  isSendingText.value = false
  interruptResponse()

  try {
    await interruptTextRuntimeSession(sessionId)
  } catch (err) {
    console.warn('[Chat] 停止回复失败:', err)
  } finally {
    isStoppingResponse.value = false
    if (activeConversationId.value) {
      upsertConversationArchive(activeConversationId.value, messages.value)
    }
  }
}

async function handleSend() {
  const text = inputText.value.trim()
  if (!text) return
  if (isBotResponding.value) {
    return
  }
  addLocalUserMessage(text)
  startAssistantPending('typing')
  inputText.value = ''

  isSendingText.value = true
  try {
    await sendChatMessage(text)
  } catch (err) {
    if (isAbortError(err)) {
      return
    }
    clearAssistantPending()
    showSendError(textSendErrorMessage(err))
  } finally {
    isSendingText.value = false
  }
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    void handleSend()
  }
}

function handleQuickAction(action: string) {
  inputText.value = action
  void handleSend()
}

function toggleInputMode() {
  inputMode.value = inputMode.value === 'text' ? 'ptt' : 'text'
}

async function startHoldToTalk() {
  if (inputMode.value !== 'ptt') {
    return
  }
  if (isHoldingToTalk.value || isSpeechRecording.value || isSpeechTranscribing.value || isSendingText.value) {
    console.debug(SPEECH_LOG_PREFIX, 'ignore start: busy', {
      isHoldingToTalk: isHoldingToTalk.value,
      isSpeechRecording: isSpeechRecording.value,
      isSpeechTranscribing: isSpeechTranscribing.value,
      isSendingText: isSendingText.value,
    })
    return
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    console.warn(SPEECH_LOG_PREFIX, 'mediaDevices.getUserMedia unavailable')
    showSendError('当前浏览器不支持麦克风录音')
    return
  }
  const requestId = ++speechCaptureRequestId
  isHoldingToTalk.value = true
  try {
    console.info(SPEECH_LOG_PREFIX, 'recording start request')
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
      video: false,
    })
    if (requestId !== speechCaptureRequestId || !isHoldingToTalk.value) {
      for (const track of stream.getTracks()) {
        track.stop()
      }
      console.info(SPEECH_LOG_PREFIX, 'recording start cancelled before microphone became ready')
      return
    }
    speechStream = stream
    speechAudioContext = new AudioContext()
    speechInputSampleRate = speechAudioContext.sampleRate
    speechChunks = []
    speechStartedAt = Date.now()
    speechSource = speechAudioContext.createMediaStreamSource(speechStream)
    speechProcessor = speechAudioContext.createScriptProcessor(4096, 1, 1)
    speechProcessor.onaudioprocess = (event) => {
      if (!isSpeechRecording.value) return
      const input = event.inputBuffer.getChannelData(0)
      speechChunks.push(new Float32Array(input))
    }
    speechSource.connect(speechProcessor)
    speechProcessingDestination = speechAudioContext.createMediaStreamDestination()
    speechProcessor.connect(speechProcessingDestination)
    isSpeechRecording.value = true
    console.info(SPEECH_LOG_PREFIX, 'recording started', {
      inputSampleRate: speechInputSampleRate,
      tracks: speechStream.getAudioTracks().length,
    })
  } catch (err) {
    if (requestId !== speechCaptureRequestId) {
      return
    }
    const message = err instanceof Error && err.name === 'NotAllowedError'
      ? '需要允许麦克风权限后才能语音输入'
      : '无法开启麦克风，请检查浏览器权限'
    console.warn(SPEECH_LOG_PREFIX, 'recording start failed', err)
    showSendError(message)
    isHoldingToTalk.value = false
    await cleanupSpeechRecording()
  }
}

async function endHoldToTalk() {
  isHoldingToTalk.value = false
  if (!isSpeechRecording.value) {
    await cleanupSpeechRecording()
    return
  }
  const durationMs = Date.now() - speechStartedAt
  const chunks = speechChunks.slice()
  const inputSampleRate = speechInputSampleRate
  isSpeechRecording.value = false
  await cleanupSpeechRecording()
  console.info(SPEECH_LOG_PREFIX, 'recording ended', {
    durationMs,
    chunks: chunks.length,
    inputSampleRate,
  })

  if (durationMs < 450 || chunks.length === 0) {
    console.warn(SPEECH_LOG_PREFIX, 'recording too short', { durationMs, chunks: chunks.length })
    showSendError('录音太短，请按住说完后再松开')
    return
  }

  isSpeechTranscribing.value = true
  try {
    const pcm = encodePcm16(downsampleAudio(mergeAudioChunks(chunks), inputSampleRate, 16000))
    if (pcm.byteLength < 800) {
      console.warn(SPEECH_LOG_PREFIX, 'pcm too short', { bytes: pcm.byteLength })
      showSendError('录音太短，请按住说完后再松开')
      return
    }
    const uploadStartedAt = performance.now()
    console.info(SPEECH_LOG_PREFIX, 'transcribe upload start', {
      bytes: pcm.byteLength,
      inputSampleRate,
      targetSampleRate: 16000,
    })
    const formData = new FormData()
    formData.append('sample_rate', '16000')
    formData.append('audio', new Blob([pcm], { type: 'application/octet-stream' }), 'speech.pcm')
    const response = await fetch(apiUrl('/api/speech/transcribe'), {
      method: 'POST',
      body: formData,
    })
    if (!response.ok) {
      const payload = await response.json().catch(() => null) as { detail?: string } | null
      throw new Error(payload?.detail || '语音识别失败，请稍后重试')
    }
    const data = await response.json() as { text: string }
    const text = data.text.trim()
    if (!text) {
      console.warn(SPEECH_LOG_PREFIX, 'transcribe returned empty text')
      showSendError('没有识别到清晰语音')
      return
    }
    console.info(SPEECH_LOG_PREFIX, 'transcribe success', {
      elapsedMs: Math.round(performance.now() - uploadStartedAt),
      textLength: text.length,
      preview: text.length > 20 ? `${text.slice(0, 20)}...` : text,
    })
    inputText.value = text
    await handleSend()
  } catch (err) {
    const message = err instanceof Error ? err.message : '语音识别失败，请稍后重试'
    console.warn(SPEECH_LOG_PREFIX, 'transcribe failed', err)
    showSendError(message)
  } finally {
    isSpeechTranscribing.value = false
  }
}

async function cleanupSpeechRecording() {
  speechCaptureRequestId += 1

  const processor = speechProcessor
  const source = speechSource
  const processingDestination = speechProcessingDestination
  const audioContext = speechAudioContext
  const stream = speechStream

  speechProcessor = null
  speechSource = null
  speechProcessingDestination = null
  speechAudioContext = null
  speechStream = null

  if (stream) {
    for (const track of stream.getTracks()) {
      track.stop()
    }
  }
  if (processor) {
    processor.onaudioprocess = null
    processor.disconnect()
  }
  source?.disconnect()
  if (processingDestination) {
    for (const track of processingDestination.stream.getTracks()) {
      track.stop()
    }
    processingDestination.disconnect()
  }
  if (audioContext && audioContext.state !== 'closed') {
    try {
      await audioContext.close()
    } catch (err) {
      console.warn(SPEECH_LOG_PREFIX, 'audio context close failed', err)
    }
  }
}

function mergeAudioChunks(chunks: Float32Array[]) {
  const totalLength = chunks.reduce((sum, chunk) => sum + chunk.length, 0)
  const merged = new Float32Array(totalLength)
  let offset = 0
  for (const chunk of chunks) {
    merged.set(chunk, offset)
    offset += chunk.length
  }
  return merged
}

function downsampleAudio(input: Float32Array, sourceRate: number, targetRate: number) {
  if (sourceRate === targetRate) return input
  const ratio = sourceRate / targetRate
  const outputLength = Math.floor(input.length / ratio)
  const output = new Float32Array(outputLength)
  for (let i = 0; i < outputLength; i++) {
    const start = Math.floor(i * ratio)
    const end = Math.min(Math.floor((i + 1) * ratio), input.length)
    let sum = 0
    for (let j = start; j < end; j++) {
      sum += input[j]
    }
    output[i] = sum / Math.max(1, end - start)
  }
  return output
}

function encodePcm16(input: Float32Array) {
  const buffer = new ArrayBuffer(input.length * 2)
  const view = new DataView(buffer)
  for (let i = 0; i < input.length; i++) {
    const sample = Math.max(-1, Math.min(1, input[i]))
    view.setInt16(i * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true)
  }
  return buffer
}

function toggleRealtimeChat() {
  if (!isVoiceChannelOpen.value) {
    showSendError('语音通道已关闭，文字聊天仍可使用')
    return
  }
  isRealtimeChatOn.value = !isRealtimeChatOn.value
}

async function handleReconnect() {
  isVoiceChannelOpen.value = true
  const conversationId = authStore.isLoggedIn ? await ensureLoggedConversation() : activeConversationId.value
  const connected = await connect(sessionStore.selectedAudience, {
    sessionId: sessionStore.sessionInfo?.sessionId,
    conversationId,
  })
  if (connected?.conversationId) {
    activeConversationId.value = connected.conversationId
  }
}

async function handleToggleWebrtcConnection() {
  if (sessionStore.status === 'connected') {
    isVoiceChannelOpen.value = !isVoiceChannelOpen.value
    if (!isVoiceChannelOpen.value) {
      setMicMuted(true)
      if (voiceEnabled.value) toggleVoice()
      if (vadInterruptEnabled.value) toggleVadInterrupt()
      isRealtimeChatOn.value = false
      isHoldingToTalk.value = false
    }
    return
  }

  if (sessionStore.status === 'connecting') {
    disconnect()
    isVoiceChannelOpen.value = false
    isRealtimeChatOn.value = false
    isHoldingToTalk.value = false
    return
  }
  isVoiceChannelOpen.value = true
  const conversationId = authStore.isLoggedIn ? await ensureLoggedConversation() : activeConversationId.value
  const connected = await connect(sessionStore.selectedAudience, {
    sessionId: sessionStore.sessionInfo?.sessionId,
    conversationId,
  })
  if (connected?.conversationId) {
    activeConversationId.value = connected.conversationId
  }
}

async function handleNewConversation() {
  if (!authStore.isLoggedIn) {
    return
  }
  archiveCurrentConversation({ preserveOrder: true })
  // 清空所有前端会话状态（消息、流式、任务卡、工具结果、错误）
  closeTextProgressEvents()
  disconnect()
  resetChat()
  inputText.value = ''
  const created = await createLoggedConversation()
  activeConversationId.value = created.sessionId
  const nextSessionId = createClientSessionId()
  textChatSessionId.value = nextSessionId
  isVoiceChannelOpen.value = false
  isRealtimeChatOn.value = false
  isHoldingToTalk.value = false
  if (sendErrorTimer !== null) {
    clearTimeout(sendErrorTimer)
    sendErrorTimer = null
  }
  sendError.value = ''
  // 关闭侧边抽屉（移动端体验）
  sideDrawerOpen.value = false
  // 重置会话信息，确保 connect 时不会带上旧 session_id
  const audience = sessionStore.selectedAudience
  sessionStore.reset()
  sessionStore.setAudience(audience)
  sessionStore.setSessionInfo({
    sessionId: nextSessionId,
    audience,
    currentNode: '',
    connectedAt: new Date().toISOString(),
  })
  await router.push(`/chat/${audience}/${created.sessionId}`)
}

function openSkillCenter() {
  skillCenterOpen.value = true
}

function openLogin() {
  showRegisterModal.value = false
  showLoginModal.value = true
}

function openRegister() {
  showLoginModal.value = false
  showRegisterModal.value = true
}

function closeAuthModals() {
  showLoginModal.value = false
  showRegisterModal.value = false
  if (authStore.isLoggedIn) {
    void (async () => {
      await loadConversationList()
      await handleNewConversation()
    })()
  }
}

function openSubscription() {
  subscriptionOpen.value = true
}

function closeSubscription() {
  subscriptionOpen.value = false
}

function handleSubscribe(plan: { id: string; title: string; tierName: string }) {
  console.log('[SoulMeet Pro] selected subscription:', plan)
  closeSubscription()
}

function handleLogout() {
  authStore.logout()
  privateSpaceOpen.value = false
  sideDrawerOpen.value = false
  void router.replace(`/chat/${sessionStore.selectedAudience}/guest`)
  resetGuestRuntime()
}

function handleUpdateUserAvatar(avatarUrl: string) {
  authStore.updateLocalProfile({ avatarUrl })
}

function handleUpdateUserDisplayName(displayName: string) {
  authStore.updateLocalProfile({ displayName })
}

async function handleContinueArchiveConversation(conversationId: string) {
  showAllDialog.value = false
  const item = conversationArchives.value.find(session => session.sessionId === conversationId)
  await handleContinueSession({
    sessionId: conversationId,
    title: item?.title || '历史对话',
    preview: item?.preview,
  })
}

async function handleContinueSession(payload: { sessionId: string; title: string; preview?: string }) {
  if (!authStore.isLoggedIn) return
  const sessionId = payload.sessionId.trim()
  if (!sessionId) {
    showSendError('这段对话缺少 sessionId，暂时不能继续')
    return
  }

  archiveCurrentConversation({ preserveOrder: true })
  closeTextProgressEvents()
  disconnect()
  inputText.value = ''
  sendError.value = ''
  showAllDialog.value = false
  sideDrawerOpen.value = false

  await router.push(`/chat/${sessionStore.selectedAudience}/${sessionId}`)
  await loadConversationDetail(sessionId)
  openTextProgressEvents(textChatSessionId.value)
}

async function handleDeleteSession(payload: { sessionId: string; title: string }) {
  if (!authStore.isLoggedIn) return
  const sessionId = payload.sessionId.trim()
  if (!sessionId) return

  const activeSessionId = activeConversationId.value
  const isDeletingActive = sessionId === activeSessionId
  removeConversationArchive(sessionId)
  if (conversationTitleOverrides.value[sessionId]) {
    const { [sessionId]: _removed, ...rest } = conversationTitleOverrides.value
    conversationTitleOverrides.value = rest
    persistConversationTitleOverrides()
  }

  if (isDeletingActive) {
    closeTextProgressEvents()
    disconnect()
    resetChat()
    inputText.value = ''
    textChatSessionId.value = ''
    isVoiceChannelOpen.value = false
    isRealtimeChatOn.value = false
    isHoldingToTalk.value = false
    const audience = sessionStore.selectedAudience
    sessionStore.reset()
    sessionStore.setAudience(audience)
  }

  try {
    const response = await fetch(apiUrl(`/api/conversations/${encodeURIComponent(sessionId)}`), {
      method: 'DELETE',
      headers: authJsonHeaders(),
    })
    if (!response.ok) {
      throw new Error(`删除会话失败: ${response.status}`)
    }
  } catch (err) {
    console.warn('[Conversations] 删除后端会话失败:', err)
    showSendError('这段对话已从本地移除，后端稍后再同步删除')
  }

  if (isDeletingActive && authStore.isLoggedIn) {
    const next = conversationArchives.value[0] || await createLoggedConversation()
    activeConversationId.value = next.sessionId
    await router.replace(`/chat/${sessionStore.selectedAudience}/${next.sessionId}`)
    await loadConversationDetail(next.sessionId)
  }
}

function handleRenameSession(payload: { sessionId: string; title: string }) {
  const sessionId = payload.sessionId.trim()
  if (!sessionId) return
  renameTarget.value = {
    sessionId,
    title: resolveConversationTitle(sessionId, payload.title || '新对话'),
  }
  renameDialogOpen.value = true
}

function handleRenameConversationFromArchive(payload: { conversationId: string; title: string }) {
  handleRenameSession({
    sessionId: payload.conversationId,
    title: payload.title,
  })
}

function handleToggleStarConversation(conversationId: string) {
  const sessionId = conversationId.trim()
  if (!sessionId) return

  conversationArchives.value = conversationArchives.value.map(item => (
    item.sessionId === sessionId
      ? { ...item, starred: !item.starred }
      : item
  ))
  persistArchivedConversations()
}

async function handleConfirmRenameConversation(title: string) {
  const target = renameTarget.value
  if (!target) return
  const sessionId = target.sessionId
  const nextTitle = title.trim()
  if (!sessionId || !nextTitle) return

  conversationTitleOverrides.value = {
    ...conversationTitleOverrides.value,
    [sessionId]: nextTitle,
  }
  persistConversationTitleOverrides()
  conversationArchives.value = conversationArchives.value.map(item => (
    item.sessionId === sessionId
      ? { ...item, title: nextTitle }
      : item
  ))
  persistArchivedConversations()
  if (authStore.isLoggedIn) {
    try {
      await fetch(apiUrl(`/api/conversations/${encodeURIComponent(sessionId)}`), {
        method: 'PATCH',
        headers: authJsonHeaders(),
        body: JSON.stringify({ title: nextTitle }),
      })
    } catch (err) {
      console.warn('[Conversations] 重命名同步失败:', err)
    }
  }
  renameTarget.value = null
}

async function initializeConversationRoute() {
  quickActions.value = createDefaultQuickActions()
  const audience = sessionStore.selectedAudience
  if (!authStore.isLoggedIn) {
    if (!isGuestRoute.value) {
      await router.replace(`/chat/${audience}/guest`)
    }
    resetGuestRuntime()
    return
  }

  await loadConversationList()
  const requestedConversationId = routeConversationId.value
  if (!requestedConversationId || requestedConversationId === 'guest') {
    const created = await createLoggedConversation()
    activeConversationId.value = created.sessionId
    await router.replace(`/chat/${audience}/${created.sessionId}`)
    resetChat()
    textChatSessionId.value = createClientSessionId()
    sessionStore.setSessionInfo({
      sessionId: textChatSessionId.value,
      audience,
      currentNode: '',
      connectedAt: new Date().toISOString(),
    })
    return
  }

  await loadConversationDetail(requestedConversationId)
}

function updateMobileFlags() {
  viewportWidth.value = window.innerWidth
  isMobileUa.value = /Android|iPhone|iPad|iPod|Mobile|HarmonyOS/i.test(navigator.userAgent)
}

function updateKeyboardInset() {
  if (!isMobileLayout.value) {
    keyboardInset.value = 0
    return
  }
  const vv = window.visualViewport
  if (!vv) {
    keyboardInset.value = 0
    return
  }
  keyboardInset.value = Math.max(0, Math.round(window.innerHeight - vv.height - vv.offsetTop))
}

onMessage.value = handleServerMessage

onMounted(() => {
  scheduleQuickActionRefresh(0)
  void (async () => {
    if (authStore.token && !authStore.user) {
      await authStore.fetchMe()
    }
    await initializeConversationRoute()
    scheduleQuickActionRefresh(0)
  })()
  updateMobileFlags()
  updateKeyboardInset()
  refreshWeather()
  weatherRefreshTimer = setInterval(refreshWeather, WEATHER_REFRESH_MS)
  window.addEventListener('resize', updateMobileFlags)
  window.visualViewport?.addEventListener('resize', updateKeyboardInset)
  window.visualViewport?.addEventListener('scroll', updateKeyboardInset)
})

onUnmounted(() => {
  disconnect()
  closeTextProgressEvents()
  stopQuickActionRequest()
  void cleanupSpeechRecording()
  window.removeEventListener('resize', updateMobileFlags)
  window.visualViewport?.removeEventListener('resize', updateKeyboardInset)
  window.visualViewport?.removeEventListener('scroll', updateKeyboardInset)
  if (sendErrorTimer !== null) {
    clearTimeout(sendErrorTimer)
    sendErrorTimer = null
  }
  if (weatherRefreshTimer !== null) {
    clearInterval(weatherRefreshTimer)
    weatherRefreshTimer = null
  }
  if (emotionDebugResetTimer !== null) {
    clearTimeout(emotionDebugResetTimer)
    emotionDebugResetTimer = null
  }
  if (messagesScrollFrameId !== null) {
    window.cancelAnimationFrame(messagesScrollFrameId)
    messagesScrollFrameId = null
  }
})

watch([isRealtimeChatOn, isVoiceChannelOpen], ([realtimeOn, voiceOpen]) => {
  setMicMuted(!(voiceOpen && realtimeOn))
}, { immediate: true })

watch(inputMode, (mode) => {
  if (mode === 'text') {
    isHoldingToTalk.value = false
    isSpeechRecording.value = false
    void cleanupSpeechRecording()
  }
})

watch(messages, () => {
  scheduleMessagesScrollToBottom()
  scheduleQuickActionRefresh()
})

watch(() => streamingMessage.value?.streamVersion, () => {
  scheduleMessagesScrollToBottom()
})

watch(assistantProcessText, () => {
  scheduleMessagesScrollToBottom()
})

watch(() => messages.value[messages.value.length - 1]?.text, () => {
  scheduleMessagesScrollToBottom()
})

watch(() => sessionStore.selectedAudience, () => {
  quickActions.value = createDefaultQuickActions()
  scheduleQuickActionRefresh(0)
})

watch(routeConversationId, (next, prev) => {
  if (next === prev || isConversationHydrating.value) return
  void initializeConversationRoute()
})
</script>

<template>
  <MobileChatLayout
    v-if="isMobileLayout"
    :avatar-canvas="AvatarCanvas"
    :stage-background-url="stageBackgroundUrl"
    :model-url="modelUrl"
    :vrm-disabled="isVrmDisabled"
    :bot-avatar-url="botAvatarUrl"
    :bot-display-name="botDisplayName"
    :connection-indicator="connectionIndicator"
    :weather="weather"
    :voice-enabled="voiceEnabled"
    :voice-channel-open="isVoiceChannelOpen"
    :vad-interrupt-enabled="vadInterruptEnabled"
    :is-realtime-chat-on="isRealtimeChatOn"
    :quick-actions="quickActions"
    :input-mode="inputMode"
    :input-text="inputText"
    :quick-actions-disabled="isBotResponding"
    :is-bot-responding="isBotResponding"
    :is-speech-recording="isSpeechRecording"
    :is-speech-transcribing="isSpeechTranscribing"
    :send-error="sendError"
    :input-placeholder="t('chat.inputPlaceholder')"
    :displayed-sessions="displayedSessions"
    :has-more-sessions="hasMoreSessions"
    :conversation-rounds="conversationRounds"
    :recent-conversation-rounds="recentConversationRounds"
    :show-all-dialog="showAllDialog"
    :side-drawer-open="sideDrawerOpen"
    :private-space-open="privateSpaceOpen"
    :keyboard-inset="keyboardInset"
    :session-status="sessionStore.status"
    :emotion-state="sessionStore.emotionState"
    :streaming-message="streamingMessage"
    :assistant-process-text="assistantProcessText"
    :render-markdown="renderMarkdown"
    :user-avatar-url="userAvatarUrl"
    :user-display-name="userDisplayName"
    :user-subscription-label="userSubscriptionLabel"
    :is-user-logged-in="authStore.isLoggedIn"
    :task-progress="taskProgress"
    :can-reconnect="canReconnect"
    @update:input-text="inputText = $event"
    @update:show-all-dialog="showAllDialog = $event"
    @update:side-drawer-open="sideDrawerOpen = $event"
    @update:private-space-open="privateSpaceOpen = $event"
    @toggle-voice="toggleVoice"
    @toggle-vad-interrupt="toggleVadInterrupt"
    @toggle-webrtc-connection="handleToggleWebrtcConnection"
    @toggle-realtime-chat="toggleRealtimeChat"
    @toggle-input-mode="toggleInputMode"
    @send="handleSend"
    @stop-response="handleStopBotResponse"
    @quick-action="handleQuickAction"
    @keydown-enter="handleKeydown"
    @start-hold-to-talk="startHoldToTalk"
    @end-hold-to-talk="endHoldToTalk"
    @reconnect="handleReconnect"
    @retry-task="retryTextRuntimeTask"
    @open-skill-center="openSkillCenter"
    @new-conversation="handleNewConversation"
    @continue-session="handleContinueSession"
    @rename-session="handleRenameSession"
    @delete-session="handleDeleteSession"
    @logout="handleLogout"
    @open-login="openLogin"
    @open-register="openRegister"
    @open-subscription="openSubscription"
  />

  <DesktopChatLayout
    v-else
    :avatar-canvas="AvatarCanvas"
    :stage-background-url="stageBackgroundUrl"
    :model-url="modelUrl"
    :vrm-disabled="isVrmDisabled"
    :bot-avatar-url="botAvatarUrl"
    :bot-display-name="botDisplayName"
    :connection-indicator="connectionIndicator"
    :weather="weather"
    :voice-enabled="voiceEnabled"
    :voice-channel-open="isVoiceChannelOpen"
    :vad-interrupt-enabled="vadInterruptEnabled"
    :is-realtime-chat-on="isRealtimeChatOn"
    :quick-actions="quickActions"
    :input-mode="inputMode"
    :input-text="inputText"
    :quick-actions-disabled="isBotResponding"
    :is-bot-responding="isBotResponding"
    :is-speech-recording="isSpeechRecording"
    :is-speech-transcribing="isSpeechTranscribing"
    :send-error="sendError"
    :input-placeholder="t('chat.inputPlaceholder')"
    :displayed-sessions="displayedSessions"
    :has-more-sessions="hasMoreSessions"
    :conversation-rounds="conversationRounds"
    :show-all-dialog="showAllDialog"
    :status-panel-open="statusPanelOpen"
    :private-space-open="privateSpaceOpen"
    :session-status="sessionStore.status"
    :emotion-state="desktopEmotionState"
    :streaming-message="desktopStreamingMessage"
    :assistant-process-text="assistantProcessText"
    :render-markdown="renderMarkdown"
    :user-avatar-url="userAvatarUrl"
    :user-display-name="userDisplayName"
    :user-account-name="userAccountName"
    :user-subscription-label="userSubscriptionLabel"
    :is-user-logged-in="authStore.isLoggedIn"
    :set-messages-container="setMessagesContainer"
    :task-progress="taskProgress"
    :can-reconnect="canReconnect"
    @update:input-text="inputText = $event"
    @update:show-all-dialog="showAllDialog = $event"
    @update:status-panel-open="statusPanelOpen = $event"
    @update:private-space-open="privateSpaceOpen = $event"
    @toggle-voice="toggleVoice"
    @toggle-vad-interrupt="toggleVadInterrupt"
    @toggle-webrtc-connection="handleToggleWebrtcConnection"
    @toggle-realtime-chat="toggleRealtimeChat"
    @toggle-input-mode="toggleInputMode"
    @send="handleSend"
    @stop-response="handleStopBotResponse"
    @quick-action="handleQuickAction"
    @keydown-enter="handleKeydown"
    @start-hold-to-talk="startHoldToTalk"
    @end-hold-to-talk="endHoldToTalk"
    @reconnect="handleReconnect"
    @retry-task="retryTextRuntimeTask"
    @open-skill-center="openSkillCenter"
    @new-conversation="handleNewConversation"
    @continue-session="handleContinueSession"
    @rename-session="handleRenameSession"
    @delete-session="handleDeleteSession"
    @logout="handleLogout"
    @open-login="openLogin"
    @open-register="openRegister"
    @open-subscription="openSubscription"
    @update-user-avatar="handleUpdateUserAvatar"
    @update-user-display-name="handleUpdateUserDisplayName"
    @update-stage-panel-collapsed="isDesktopStageCollapsed = $event"
  />

  <EmotionDebugPanel
    v-if="!isDesktopStageCollapsed"
    :options="emotionDebugOptions"
    :current-label="sessionStore.emotionState.label"
    boundary-selector="[data-emotion-boundary='interaction-stage']"
    @select-emotion="handleDebugEmotionSelect"
    @reset="resetDebugEmotion"
  />

  <AllConversationsModal
    v-model:open="showAllDialog"
    :bot-avatar-url="botAvatarUrl"
    :conversations="allConversationModalItems"
    @continue="handleContinueArchiveConversation"
    @rename="handleRenameConversationFromArchive"
    @delete="sessionId => handleDeleteSession({ sessionId, title: '历史对话' })"
    @toggle-star="handleToggleStarConversation"
  />

  <RenameConversationModal
    v-model:open="renameDialogOpen"
    :title="renameTarget?.title || ''"
    @confirm="handleConfirmRenameConversation"
  />

  <SkillCenterModal
    v-model:open="skillCenterOpen"
    :bot-avatar-url="botAvatarUrl"
    :bot-display-name="botDisplayName"
  />

  <SubscriptionModal
    v-if="subscriptionOpen"
    @close="closeSubscription"
    @subscribe="handleSubscribe"
  />

  <LoginModal
    v-if="showLoginModal"
    @close="closeAuthModals"
    @switch-to-register="openRegister"
  />

  <RegisterModal
    v-if="showRegisterModal"
    @close="closeAuthModals"
    @switch-to-login="openLogin"
  />
</template>
