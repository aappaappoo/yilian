<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import type { Component, ComponentPublicInstance } from 'vue'
import { Capacitor, registerPlugin, type PluginListenerHandle } from '@capacitor/core'
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
import SubscriptionModal from '../components/SubscriptionModal.vue'
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
const TEXT_RUNTIME_HTTP_REQUEST_TIMEOUT_MS = 45_000
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

interface NativeTextProgressEvent {
  data?: string
  message?: string
  status?: number
}

interface NativeKeyboardInsetEventDetail {
  height?: number
}

interface NativeTextProgressPlugin {
  start(options: { url: string }): Promise<void>
  stop(): Promise<void>
  addListener(
    eventName: 'open' | 'message' | 'error' | 'closed',
    listenerFunc: (event: NativeTextProgressEvent) => void,
  ): Promise<PluginListenerHandle>
}

const NativeTextProgress = registerPlugin<NativeTextProgressPlugin>('TextProgress')

interface LocalReminderPlugin {
  schedule(options: { id: string; title: string; body: string; dueAt: string }): Promise<{ scheduled?: boolean; permission?: string }>
  cancel(options: { id: string }): Promise<void>
}

const LocalReminder = registerPlugin<LocalReminderPlugin>('LocalReminder')

interface NativeVoiceBroadcastPlugin {
  speak(options: { url: string; text: string }): Promise<{ bytes?: number; duration?: number }>
  stop(): Promise<void>
}

const NativeVoiceBroadcast = registerPlugin<NativeVoiceBroadcastPlugin>('VoiceBroadcast')

interface VoiceBroadcastQueueItem {
  key: string
  messageId?: string
  text: string
  segmentIndex?: number
}

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
const { connect, disconnect, onMessage, setMicMuted, voiceEnabled, toggleVoice, vadInterruptEnabled, toggleVadInterrupt, interruptResponse, sendRealtimeEvent } = useWebRTC()
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
const messagesAutoFollow = ref(true)
const hasNewMessagesBelow = ref(false)
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
let textProgressNativeSessionId = ''
let textProgressNativeListenerHandles: PluginListenerHandle[] = []
let textProgressReadyPromise: Promise<void> | null = null
let textProgressRequestSeq = 0
let activeTextProgressRequestSeq = 0
let textProgressAcceptingMessages = false
let textProgressReplayAcceptingMessages = false
let textProgressActiveSessionId = ''
let lastTextProgressEventSeq = 0
const PASSIVE_TEXT_PROGRESS_SOURCES = new Set(['soul_companion:reminder'])
const passiveTextProgressMessageIds = new Set<string>()
let textMessageAbortController: AbortController | null = null
let textRuntimeRecoveryNeeded = false
let textRuntimeRecoveryTimer: ReturnType<typeof setTimeout> | null = null
let textRuntimeRecoverySeq = 0
let quickActionAbortController: AbortController | null = null
let quickActionRefreshTimer: ReturnType<typeof setTimeout> | null = null
let quickActionRequestSeq = 0
let weatherRefreshTimer: ReturnType<typeof setInterval> | null = null
let emotionDebugResetTimer: ReturnType<typeof setTimeout> | null = null
let messagesScrollFrameId: number | null = null
let messagesScrollElement: HTMLElement | null = null
let keyboardInsetRefreshTimers: ReturnType<typeof setTimeout>[] = []
let nativeKeyboardInset = 0
let layoutViewportMaxHeight = typeof window !== 'undefined'
  ? Math.max(window.innerHeight, document.documentElement.clientHeight || 0)
  : 0
let layoutViewportBaselineWidth = typeof window !== 'undefined' ? window.innerWidth : 0
let realtimeInteractionRequestSeq = 0
let currentVoiceBroadcastAudio: HTMLAudioElement | null = null
let currentVoiceBroadcastObjectUrl = ''
let voiceBroadcastAudioElement: HTMLAudioElement | null = null
let voiceBroadcastUnlockObjectUrl = ''
let voiceBroadcastPlaybackUnlocked = false
let voiceBroadcastUnlockPromise: Promise<void> | null = null
let voiceBroadcastAbortController: AbortController | null = null
let activeVoiceBroadcastKey = ''
let lastVoiceBroadcastKey = ''
let voiceBroadcastGeneration = 0
let voiceBroadcastQueueRunning = false
let voiceBroadcastStreamActive = false
let voiceBroadcastStreamMessageId = ''
let voiceBroadcastStreamBuffer = ''
let voiceBroadcastStreamHadSegments = false
let voiceBroadcastStreamSequence = 0
let voiceBroadcastQueue: VoiceBroadcastQueueItem[] = []
const completedVoiceBroadcastMessageIds = new Set<string>()
let liveKitVoiceBroadcastMessageId = ''
let liveKitVoiceBroadcastHadDelta = false
let liveKitVoiceBroadcastConnectPromise: Promise<boolean> | null = null

const TITLE_MAX_CHARS = 15
const SPEECH_LOG_PREFIX = '[SpeechInput]'
const VOICE_BROADCAST_LOG_PREFIX = '[VoiceBroadcast]'
const VOICE_BROADCAST_STREAM_MIN_CHARS = 18
const VOICE_BROADCAST_STREAM_MAX_CHARS = 72
const VOICE_BROADCAST_STREAM_BREAK_CHARS = '。！？!?；;\n'
const VOICE_BROADCAST_STREAM_SOFT_BREAK_CHARS = '，,、：: '
const WEATHER_REFRESH_MS = 60 * 60 * 1000
const QUICK_ACTION_REFRESH_DELAY_MS = 360
const QUICK_ACTION_REQUEST_TIMEOUT_MS = 8000
const KEYBOARD_INSET_MIN_PX = 80
const KEYBOARD_INSET_REFRESH_DELAYS_MS = [0, 40, 120, 260, 520]
const MESSAGE_AUTO_SCROLL_BOTTOM_THRESHOLD_PX = 120

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

function isVoiceBroadcastSupported(): boolean {
  return typeof window !== 'undefined'
    && typeof Audio !== 'undefined'
    && typeof URL !== 'undefined'
    && typeof fetch !== 'undefined'
}

function shouldUseNativeVoiceBroadcast(): boolean {
  return Capacitor.isNativePlatform() && Capacitor.getPlatform() === 'ios'
}

function normalizeVoiceBroadcastText(raw: string): string {
  const withoutReferences = raw.replace(/(?:^|\n)\s*(?:参考链接|References?)\s*[:：]?[\s\S]*$/i, '')
  return withoutReferences
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/!\[([^\]]*)]\([^)]+\)/g, '$1')
    .replace(/\[([^\]]+)]\([^)]+\)/g, '$1')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/^>\s?/gm, '')
    .replace(/^\s*[-*+]\s+/gm, '')
    .replace(/^\s*\d+\.\s+/gm, '')
    .replace(/https?:\/\/\S+/g, '')
    .replace(/[|*_>#]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function voiceBroadcastSignature(text: string): string {
  const normalized = normalizeVoiceBroadcastText(text)
  return `${normalized.length}:${normalized.slice(0, 160)}`
}

function voiceBroadcastKey(messageId: string | undefined, text: string): string {
  return messageId ? `id:${messageId}` : `text:${voiceBroadcastSignature(text)}`
}

function revokeVoiceBroadcastObjectUrl() {
  if (!currentVoiceBroadcastObjectUrl) return
  URL.revokeObjectURL(currentVoiceBroadcastObjectUrl)
  currentVoiceBroadcastObjectUrl = ''
}

function revokeVoiceBroadcastUnlockObjectUrl() {
  if (!voiceBroadcastUnlockObjectUrl) return
  URL.revokeObjectURL(voiceBroadcastUnlockObjectUrl)
  voiceBroadcastUnlockObjectUrl = ''
}

function createSilentWavObjectUrl(): string {
  const sampleRate = 8000
  const samples = 80
  const dataBytes = samples * 2
  const buffer = new ArrayBuffer(44 + dataBytes)
  const view = new DataView(buffer)
  let offset = 0
  const writeString = (value: string) => {
    for (let index = 0; index < value.length; index += 1) {
      view.setUint8(offset + index, value.charCodeAt(index))
    }
    offset += value.length
  }
  writeString('RIFF')
  view.setUint32(offset, 36 + dataBytes, true); offset += 4
  writeString('WAVE')
  writeString('fmt ')
  view.setUint32(offset, 16, true); offset += 4
  view.setUint16(offset, 1, true); offset += 2
  view.setUint16(offset, 1, true); offset += 2
  view.setUint32(offset, sampleRate, true); offset += 4
  view.setUint32(offset, sampleRate * 2, true); offset += 4
  view.setUint16(offset, 2, true); offset += 2
  view.setUint16(offset, 16, true); offset += 2
  writeString('data')
  view.setUint32(offset, dataBytes, true)
  return URL.createObjectURL(new Blob([buffer], { type: 'audio/wav' }))
}

function ensureVoiceBroadcastAudioElement(): HTMLAudioElement | null {
  if (!isVoiceBroadcastSupported()) return null
  if (voiceBroadcastAudioElement) return voiceBroadcastAudioElement
  const audio = new Audio()
  audio.preload = 'auto'
  audio.setAttribute('playsinline', 'true')
  audio.style.position = 'fixed'
  audio.style.width = '1px'
  audio.style.height = '1px'
  audio.style.opacity = '0'
  audio.style.pointerEvents = 'none'
  audio.setAttribute('aria-hidden', 'true')
  if (typeof document !== 'undefined' && !audio.isConnected) {
    document.body.appendChild(audio)
  }
  voiceBroadcastAudioElement = audio
  return audio
}

async function unlockVoiceBroadcastPlayback(reason: string): Promise<void> {
  if (!isVoiceBroadcastSupported() || voiceBroadcastPlaybackUnlocked) return
  if (voiceBroadcastUnlockPromise) return voiceBroadcastUnlockPromise
  const audio = ensureVoiceBroadcastAudioElement()
  if (!audio) return

  voiceBroadcastUnlockPromise = (async () => {
    revokeVoiceBroadcastUnlockObjectUrl()
    voiceBroadcastUnlockObjectUrl = createSilentWavObjectUrl()
    try {
      audio.pause()
      audio.src = voiceBroadcastUnlockObjectUrl
      audio.muted = false
      audio.volume = 0
      audio.load()
      await audio.play()
      audio.pause()
      audio.currentTime = 0
      voiceBroadcastPlaybackUnlocked = true
      console.info(VOICE_BROADCAST_LOG_PREFIX, 'iOS 音频播放已解锁', { reason })
    } catch (err) {
      voiceBroadcastPlaybackUnlocked = false
      console.warn(VOICE_BROADCAST_LOG_PREFIX, 'iOS 音频播放解锁失败', { reason, error: err })
    } finally {
      audio.removeAttribute('src')
      audio.load()
      audio.volume = 1
      revokeVoiceBroadcastUnlockObjectUrl()
      voiceBroadcastUnlockPromise = null
    }
  })()

  return voiceBroadcastUnlockPromise
}

function clearVoiceBroadcastStreamState() {
  voiceBroadcastStreamActive = false
  voiceBroadcastStreamMessageId = ''
  voiceBroadcastStreamBuffer = ''
  voiceBroadcastStreamHadSegments = false
  voiceBroadcastStreamSequence = 0
}

function clearLiveKitVoiceBroadcastState() {
  liveKitVoiceBroadcastMessageId = ''
  liveKitVoiceBroadcastHadDelta = false
}

function canUseLiveKitVoiceBroadcast(): boolean {
  return voiceEnabled.value && sessionStore.status === 'connected'
}

function sendLiveKitVoiceBroadcastPayload(payload: Record<string, unknown>): boolean {
  if (!canUseLiveKitVoiceBroadcast()) return false
  const sent = sendRealtimeEvent(payload)
  if (!sent) {
    console.warn(VOICE_BROADCAST_LOG_PREFIX, 'LiveKit 播报消息发送失败', {
      type: payload.type,
      message_id: payload.message_id || null,
    })
  }
  return sent
}

function cancelLiveKitVoiceBroadcast(reason = 'cancel') {
  if (liveKitVoiceBroadcastMessageId && canUseLiveKitVoiceBroadcast()) {
    sendRealtimeEvent({
      type: 'voice_broadcast_cancel',
      message_id: liveKitVoiceBroadcastMessageId,
      reason,
    })
  }
  clearLiveKitVoiceBroadcastState()
}

function beginLiveKitVoiceBroadcast(messageId?: string): boolean {
  if (!canUseLiveKitVoiceBroadcast()) return false
  const nextMessageId = messageId || liveKitVoiceBroadcastMessageId || createClientSessionId()
  if (nextMessageId && completedVoiceBroadcastMessageIds.has(nextMessageId)) return true
  if (liveKitVoiceBroadcastMessageId === nextMessageId) return true
  if (liveKitVoiceBroadcastMessageId) {
    cancelLiveKitVoiceBroadcast('new_message')
  }
  const sent = sendLiveKitVoiceBroadcastPayload({
    type: 'voice_broadcast_start',
    message_id: nextMessageId,
  })
  if (!sent) return false
  liveKitVoiceBroadcastMessageId = nextMessageId
  liveKitVoiceBroadcastHadDelta = false
  console.info(VOICE_BROADCAST_LOG_PREFIX, 'LiveKit 播报开始', { message_id: nextMessageId })
  return true
}

function appendLiveKitVoiceBroadcastDelta(delta: string, messageId?: string): boolean {
  if (!voiceEnabled.value || !delta) return false
  const nextMessageId = messageId || liveKitVoiceBroadcastMessageId || createClientSessionId()
  if (nextMessageId && completedVoiceBroadcastMessageIds.has(nextMessageId)) return true
  if (!beginLiveKitVoiceBroadcast(nextMessageId)) return false
  const sent = sendLiveKitVoiceBroadcastPayload({
    type: 'voice_broadcast_delta',
    message_id: nextMessageId,
    delta,
    text: delta,
  })
  if (sent) {
    liveKitVoiceBroadcastHadDelta = true
  }
  return sent || liveKitVoiceBroadcastMessageId === nextMessageId
}

function finishLiveKitVoiceBroadcast(messageId: string | undefined, finalText: string): boolean {
  if (!voiceEnabled.value) return false
  const nextMessageId = messageId || liveKitVoiceBroadcastMessageId || createClientSessionId()
  if (nextMessageId && completedVoiceBroadcastMessageIds.has(nextMessageId)) return true
  const hadActiveStream = Boolean(liveKitVoiceBroadcastMessageId)
  if (!hadActiveStream && !finalText.trim()) return false
  if (!hadActiveStream && !beginLiveKitVoiceBroadcast(nextMessageId)) return false
  if (!liveKitVoiceBroadcastHadDelta && finalText.trim()) {
    appendLiveKitVoiceBroadcastDelta(finalText, nextMessageId)
  }
  const sent = sendLiveKitVoiceBroadcastPayload({
    type: 'voice_broadcast_finish',
    message_id: nextMessageId,
    text: finalText,
  })
  clearLiveKitVoiceBroadcastState()
  rememberCompletedVoiceBroadcastMessage(nextMessageId)
  return sent || hadActiveStream
}

async function ensureLiveKitVoiceBroadcastChannel(reason: string): Promise<boolean> {
  if (!voiceEnabled.value) return false
  if (sessionStore.status === 'connected') return true
  if (liveKitVoiceBroadcastConnectPromise) return liveKitVoiceBroadcastConnectPromise

  liveKitVoiceBroadcastConnectPromise = (async () => {
    try {
      setMicMuted(true)
      const conversationId = authStore.isLoggedIn ? await ensureLoggedConversation() : activeConversationId.value
      const sessionId = sessionStore.sessionInfo?.sessionId || textChatSessionId.value || undefined
      const connected = await connect(sessionStore.selectedAudience, {
        sessionId,
        conversationId,
      })
      if (!connected) {
        console.warn(VOICE_BROADCAST_LOG_PREFIX, 'LiveKit 播报通道连接失败', { reason })
        return false
      }
      if (connected.conversationId) {
        activeConversationId.value = connected.conversationId
      }
      isVoiceChannelOpen.value = true
      isRealtimeChatOn.value = false
      setMicMuted(true)
      console.info(VOICE_BROADCAST_LOG_PREFIX, 'LiveKit 播报通道已连接', {
        reason,
        session_id: connected.sessionId,
      })
      return true
    } catch (err) {
      console.warn(VOICE_BROADCAST_LOG_PREFIX, 'LiveKit 播报通道连接异常', { reason, error: err })
      return false
    } finally {
      liveKitVoiceBroadcastConnectPromise = null
    }
  })()

  const connectPromise = liveKitVoiceBroadcastConnectPromise
  return connectPromise ?? false
}

function rememberCompletedVoiceBroadcastMessage(messageId?: string) {
  if (!messageId) return
  completedVoiceBroadcastMessageIds.add(messageId)
  if (completedVoiceBroadcastMessageIds.size > 40) {
    const oldest = completedVoiceBroadcastMessageIds.values().next().value
    if (oldest) completedVoiceBroadcastMessageIds.delete(oldest)
  }
}

function cancelVoiceBroadcast(reason = 'cancel') {
  cancelLiveKitVoiceBroadcast(reason)
  if (!isVoiceBroadcastSupported()) return
  voiceBroadcastGeneration += 1
  voiceBroadcastQueue = []
  voiceBroadcastQueueRunning = false
  clearVoiceBroadcastStreamState()
  voiceBroadcastAbortController?.abort()
  voiceBroadcastAbortController = null
  activeVoiceBroadcastKey = ''
  if (shouldUseNativeVoiceBroadcast()) {
    void NativeVoiceBroadcast.stop().catch((err) => {
      console.warn(VOICE_BROADCAST_LOG_PREFIX, '停止 iOS 原生播报失败', { reason, error: err })
    })
  }
  const audio = currentVoiceBroadcastAudio || voiceBroadcastAudioElement
  if (audio) {
    audio.pause()
    audio.removeAttribute('src')
    audio.load()
  }
  currentVoiceBroadcastAudio = null
  revokeVoiceBroadcastObjectUrl()
  console.info(VOICE_BROADCAST_LOG_PREFIX, '停止播报', { reason })
}

function disposeVoiceBroadcastAudioElement() {
  const audio = voiceBroadcastAudioElement
  if (audio) {
    audio.pause()
    audio.removeAttribute('src')
    audio.load()
    audio.remove()
  }
  voiceBroadcastAudioElement = null
  currentVoiceBroadcastAudio = null
  voiceBroadcastPlaybackUnlocked = false
  revokeVoiceBroadcastObjectUrl()
  revokeVoiceBroadcastUnlockObjectUrl()
}

function prepareVoiceBroadcast() {
  if (!isVoiceBroadcastSupported()) {
    showSendError('当前系统暂不支持语音播报')
    console.warn(VOICE_BROADCAST_LOG_PREFIX, 'audio playback 不可用')
    return
  }
  ensureVoiceBroadcastAudioElement()
  void unlockVoiceBroadcastPlayback('voice_toggle')
  void ensureLiveKitVoiceBroadcastChannel('voice_toggle')
}

function resetVoiceBroadcastDedup() {
  lastVoiceBroadcastKey = ''
  completedVoiceBroadcastMessageIds.clear()
  clearVoiceBroadcastStreamState()
  clearLiveKitVoiceBroadcastState()
}

function estimateVoiceBroadcastDurationMs(text: string): number {
  const cleanLength = normalizeVoiceBroadcastText(text).length
  return Math.max(700, Math.min(20_000, cleanLength * 260))
}

function waitForVoiceBroadcastDelay(durationMs: number, signal: AbortSignal): Promise<void> {
  if (signal.aborted) {
    return Promise.reject(new DOMException('Voice broadcast aborted', 'AbortError'))
  }
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => {
      signal.removeEventListener('abort', handleAbort)
      resolve()
    }, durationMs)
    const handleAbort = () => {
      window.clearTimeout(timer)
      signal.removeEventListener('abort', handleAbort)
      reject(new DOMException('Voice broadcast aborted', 'AbortError'))
    }
    signal.addEventListener('abort', handleAbort, { once: true })
  })
}

function waitForVoiceBroadcastAudio(audio: HTMLAudioElement, signal: AbortSignal): Promise<void> {
  if (signal.aborted) {
    return Promise.reject(new DOMException('Voice broadcast aborted', 'AbortError'))
  }
  return new Promise((resolve, reject) => {
    const cleanup = () => {
      audio.removeEventListener('ended', handleEnded)
      audio.removeEventListener('error', handleError)
      signal.removeEventListener('abort', handleAbort)
    }
    const handleEnded = () => {
      cleanup()
      resolve()
    }
    const handleError = () => {
      cleanup()
      reject(new Error('audio playback failed'))
    }
    const handleAbort = () => {
      cleanup()
      reject(new DOMException('Voice broadcast aborted', 'AbortError'))
    }
    audio.addEventListener('ended', handleEnded, { once: true })
    audio.addEventListener('error', handleError, { once: true })
    signal.addEventListener('abort', handleAbort, { once: true })
  })
}

async function playVoiceBroadcastQueueItem(item: VoiceBroadcastQueueItem, generation: number) {
  if (!voiceEnabled.value) return
  if (!isVoiceBroadcastSupported()) {
    console.warn(VOICE_BROADCAST_LOG_PREFIX, '跳过播报：audio playback 不可用', { message_id: item.messageId || null })
    return
  }

  const speechText = normalizeVoiceBroadcastText(item.text)
  if (!speechText) return

  const key = item.key || voiceBroadcastKey(item.messageId, speechText)
  if (key === lastVoiceBroadcastKey || key === activeVoiceBroadcastKey) {
    console.info(VOICE_BROADCAST_LOG_PREFIX, '跳过重复播报', { message_id: item.messageId || null })
    return
  }

  console.info(VOICE_BROADCAST_LOG_PREFIX, '开始播报', {
    message_id: item.messageId || null,
    segment_index: item.segmentIndex ?? null,
    text_len: speechText.length,
  })
  activeVoiceBroadcastKey = key
  const controller = new AbortController()
  voiceBroadcastAbortController = controller

  try {
    if (shouldUseNativeVoiceBroadcast()) {
      const result = await NativeVoiceBroadcast.speak({
        url: apiUrl('/api/speech/synthesize'),
        text: speechText,
      })
      if (controller.signal.aborted || generation !== voiceBroadcastGeneration || activeVoiceBroadcastKey !== key || !voiceEnabled.value) {
        await NativeVoiceBroadcast.stop().catch(() => undefined)
        return
      }
      voiceBroadcastPlaybackUnlocked = true
      lastVoiceBroadcastKey = key
      console.info(VOICE_BROADCAST_LOG_PREFIX, 'iOS 原生播报已开始', {
        message_id: item.messageId || null,
        segment_index: item.segmentIndex ?? null,
        bytes: result.bytes ?? null,
        duration: result.duration ?? null,
      })
      const durationMs = Number.isFinite(result.duration)
        ? Math.max(300, Math.ceil(Number(result.duration) * 1000) + 80)
        : estimateVoiceBroadcastDurationMs(speechText)
      await waitForVoiceBroadcastDelay(durationMs, controller.signal)
      return
    }

    const response = await fetch(apiUrl('/api/speech/synthesize'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
      body: JSON.stringify({ text: speechText }),
    })
    if (!response.ok) {
      throw new Error(`TTS request failed: ${response.status}`)
    }
    const audioBlob = await response.blob()
    if (controller.signal.aborted || generation !== voiceBroadcastGeneration || activeVoiceBroadcastKey !== key || !voiceEnabled.value) {
      return
    }
    revokeVoiceBroadcastObjectUrl()
    currentVoiceBroadcastObjectUrl = URL.createObjectURL(audioBlob)
    const audio = ensureVoiceBroadcastAudioElement()
    if (!audio) {
      throw new Error('audio playback unavailable')
    }
    audio.pause()
    audio.src = currentVoiceBroadcastObjectUrl
    audio.preload = 'auto'
    audio.muted = false
    audio.volume = 1
    audio.onended = () => {
      if (currentVoiceBroadcastAudio === audio) {
        currentVoiceBroadcastAudio = null
        revokeVoiceBroadcastObjectUrl()
      }
    }
    audio.onerror = () => {
      if (currentVoiceBroadcastAudio === audio) {
        currentVoiceBroadcastAudio = null
        revokeVoiceBroadcastObjectUrl()
      }
      console.warn(VOICE_BROADCAST_LOG_PREFIX, '阿里语音音频播放失败', { message_id: item.messageId || null })
    }
    currentVoiceBroadcastAudio = audio
    audio.load()
    await audio.play()
    voiceBroadcastPlaybackUnlocked = true
    lastVoiceBroadcastKey = key
    await waitForVoiceBroadcastAudio(audio, controller.signal)
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      return
    }
    if (err instanceof DOMException && err.name === 'NotAllowedError') {
      voiceBroadcastPlaybackUnlocked = false
      showSendError('请先点右上角声音按钮开启播报')
    }
    cancelVoiceBroadcast('broadcast_failed')
    console.warn(VOICE_BROADCAST_LOG_PREFIX, '阿里语音播报失败', {
      message_id: item.messageId || null,
      segment_index: item.segmentIndex ?? null,
      error: err,
    })
  } finally {
    if (voiceBroadcastAbortController === controller) {
      voiceBroadcastAbortController = null
    }
    if (activeVoiceBroadcastKey === key) {
      activeVoiceBroadcastKey = ''
    }
  }
}

function startVoiceBroadcastQueue() {
  if (voiceBroadcastQueueRunning) return
  voiceBroadcastQueueRunning = true
  const generation = voiceBroadcastGeneration
  void (async () => {
    try {
      while (
        generation === voiceBroadcastGeneration
        && voiceEnabled.value
        && voiceBroadcastQueue.length > 0
      ) {
        const item = voiceBroadcastQueue.shift()
        if (!item) continue
        await playVoiceBroadcastQueueItem(item, generation)
      }
    } finally {
      if (generation === voiceBroadcastGeneration) {
        voiceBroadcastQueueRunning = false
        if (voiceEnabled.value && voiceBroadcastQueue.length > 0) {
          startVoiceBroadcastQueue()
        }
      }
    }
  })()
}

function enqueueVoiceBroadcastText(
  text: string,
  options: {
    messageId?: string
    reset?: boolean
    key?: string
    segmentIndex?: number
  } = {},
) {
  if (!voiceEnabled.value) return
  const speechText = normalizeVoiceBroadcastText(text)
  if (!speechText) return
  if (options.messageId && completedVoiceBroadcastMessageIds.has(options.messageId)) return
  if (options.reset) {
    cancelVoiceBroadcast('new_broadcast')
  }
  const key = options.key || (
    options.messageId && options.segmentIndex != null
      ? `id:${options.messageId}:segment:${options.segmentIndex}`
      : voiceBroadcastKey(options.messageId, speechText)
  )
  if (key === lastVoiceBroadcastKey || key === activeVoiceBroadcastKey) return
  if (voiceBroadcastQueue.some(item => item.key === key)) return
  voiceBroadcastQueue.push({
    key,
    messageId: options.messageId,
    text: speechText,
    segmentIndex: options.segmentIndex,
  })
  startVoiceBroadcastQueue()
}

function speakAssistantReply(text: string, messageId?: string) {
  if (messageId && completedVoiceBroadcastMessageIds.has(messageId)) return
  enqueueVoiceBroadcastText(text, {
    messageId,
    reset: true,
    key: voiceBroadcastKey(messageId, text),
  })
  rememberCompletedVoiceBroadcastMessage(messageId)
}

function beginVoiceBroadcastStream(messageId?: string) {
  if (!voiceEnabled.value) return
  const nextMessageId = messageId || ''
  if (nextMessageId && completedVoiceBroadcastMessageIds.has(nextMessageId)) return
  if (voiceBroadcastStreamActive && !nextMessageId && !voiceBroadcastStreamMessageId) return
  if (voiceBroadcastStreamMessageId === nextMessageId && nextMessageId) return
  cancelVoiceBroadcast('new_stream_message')
  voiceBroadcastStreamActive = true
  voiceBroadcastStreamMessageId = nextMessageId
}

function findVoiceBroadcastSegmentBoundary(buffer: string, force: boolean): number {
  const hardLimit = Math.min(buffer.length, VOICE_BROADCAST_STREAM_MAX_CHARS)
  for (let index = 0; index < hardLimit; index += 1) {
    if (
      index + 1 >= VOICE_BROADCAST_STREAM_MIN_CHARS
      && VOICE_BROADCAST_STREAM_BREAK_CHARS.includes(buffer[index] || '')
    ) {
      return index + 1
    }
  }
  if (buffer.length >= VOICE_BROADCAST_STREAM_MAX_CHARS) {
    for (let index = hardLimit - 1; index >= VOICE_BROADCAST_STREAM_MIN_CHARS; index -= 1) {
      if (VOICE_BROADCAST_STREAM_SOFT_BREAK_CHARS.includes(buffer[index] || '')) {
        return index + 1
      }
    }
    return hardLimit
  }
  return force && buffer.trim() ? buffer.length : -1
}

function flushVoiceBroadcastStreamSegments(force = false) {
  if (!voiceEnabled.value || !voiceBroadcastStreamBuffer.trim()) return
  let buffer = voiceBroadcastStreamBuffer
  while (buffer.trim()) {
    const boundary = findVoiceBroadcastSegmentBoundary(buffer, force)
    if (boundary <= 0) break
    const segment = buffer.slice(0, boundary).trim()
    buffer = buffer.slice(boundary)
    if (!segment) continue
    voiceBroadcastStreamSequence += 1
    voiceBroadcastStreamHadSegments = true
    enqueueVoiceBroadcastText(segment, {
      messageId: voiceBroadcastStreamMessageId || undefined,
      segmentIndex: voiceBroadcastStreamSequence,
    })
    if (!force && buffer.length < VOICE_BROADCAST_STREAM_MIN_CHARS) break
  }
  voiceBroadcastStreamBuffer = buffer
}

function appendVoiceBroadcastStreamDelta(delta: string, messageId?: string) {
  if (!voiceEnabled.value || !delta) return
  if (messageId && completedVoiceBroadcastMessageIds.has(messageId)) return
  if (!voiceBroadcastStreamMessageId || (messageId && voiceBroadcastStreamMessageId !== messageId)) {
    beginVoiceBroadcastStream(messageId)
  }
  voiceBroadcastStreamBuffer += delta
  flushVoiceBroadcastStreamSegments(false)
}

function finishVoiceBroadcastStream(messageId: string | undefined, finalText: string) {
  if (!voiceEnabled.value) return
  if (messageId && completedVoiceBroadcastMessageIds.has(messageId)) return
  const isCurrentStream = voiceBroadcastStreamActive
    && (!voiceBroadcastStreamMessageId || !messageId || voiceBroadcastStreamMessageId === messageId)
  if (isCurrentStream && (voiceBroadcastStreamHadSegments || voiceBroadcastStreamBuffer.trim())) {
    flushVoiceBroadcastStreamSegments(true)
    rememberCompletedVoiceBroadcastMessage(messageId || voiceBroadcastStreamMessageId)
    clearVoiceBroadcastStreamState()
    return
  }
  speakAssistantReply(finalText, messageId)
}

function latestAssistantTextForVoiceBroadcast(messageId?: string): string {
  const candidates = [...messages.value].reverse()
  if (messageId) {
    const matched = candidates.find(message => message.role === 'assistant' && message.id === messageId)
    return matched ? getChatMessageText(matched) : ''
  }
  const latest = candidates.find(message => message.role === 'assistant' && !message.pending)
  return latest ? getChatMessageText(latest) : ''
}

function maybeSendLiveKitVoiceBroadcast(msg: ServerMessage): boolean {
  if (!voiceEnabled.value && !liveKitVoiceBroadcastMessageId) return false
  const messageId = 'message_id' in msg ? msg.message_id : undefined
  if (messageId && completedVoiceBroadcastMessageIds.has(messageId)) return true

  if (msg.type === 'assistant_message_start') {
    return beginLiveKitVoiceBroadcast(msg.message_id)
  }

  if (msg.type === 'content_block_delta') {
    return appendLiveKitVoiceBroadcastDelta(msg.delta, msg.message_id)
  }

  if (msg.type === 'assistant_text_stream') {
    return appendLiveKitVoiceBroadcastDelta(msg.text, liveKitVoiceBroadcastMessageId || undefined)
  }

  if (msg.type === 'assistant_text_interrupted') {
    cancelLiveKitVoiceBroadcast('assistant_interrupted')
    return true
  }

  if (msg.type === 'assistant_text') {
    if (msg.source === 'interrupted' || !msg.text.trim()) return Boolean(liveKitVoiceBroadcastMessageId)
    return finishLiveKitVoiceBroadcast(msg.message_id, msg.text)
  }

  if (msg.type === 'assistant_message_finish') {
    const text = msg.text?.trim() ? msg.text : latestAssistantTextForVoiceBroadcast(msg.message_id)
    return finishLiveKitVoiceBroadcast(msg.message_id, text)
  }

  return false
}

function maybeSpeakTextRuntimeReply(msg: ServerMessage) {
  if (canUseLiveKitVoiceBroadcast() || liveKitVoiceBroadcastMessageId) {
    const handledByLiveKit = maybeSendLiveKitVoiceBroadcast(msg)
    if (handledByLiveKit) return
  }

  if (msg.type === 'assistant_message_start') {
    beginVoiceBroadcastStream(msg.message_id)
    return
  }

  if (msg.type === 'content_block_delta') {
    appendVoiceBroadcastStreamDelta(msg.delta, msg.message_id)
    return
  }

  if (msg.type === 'assistant_text_stream') {
    appendVoiceBroadcastStreamDelta(msg.text)
    return
  }

  if (msg.type === 'assistant_text_interrupted') {
    cancelVoiceBroadcast('assistant_interrupted')
    return
  }

  if (msg.type === 'assistant_text') {
    if (msg.source === 'interrupted' || !msg.text.trim()) return
    finishVoiceBroadcastStream(msg.message_id, msg.text)
    return
  }

  if (msg.type === 'assistant_message_finish') {
    const text = msg.text?.trim() ? msg.text : latestAssistantTextForVoiceBroadcast(msg.message_id)
    finishVoiceBroadcastStream(msg.message_id, text)
  }
}

function handleTextRuntimeServerMessage(msg: ServerMessage) {
  handleServerMessage(msg)
  const artifact = 'artifact' in msg && msg.artifact && typeof msg.artifact === 'object' && !Array.isArray(msg.artifact)
    ? msg.artifact as Record<string, unknown>
    : undefined
  if (artifact) {
    const source = 'source' in msg && typeof msg.source === 'string' ? msg.source : undefined
    syncClientReminderFromArtifact(artifact, source)
  }
  maybeSpeakTextRuntimeReply(msg)
}

function setVoiceBroadcastEnabled(enabled: boolean, reason: string) {
  if (voiceEnabled.value !== enabled) {
    toggleVoice()
  }
  if (enabled) {
    prepareVoiceBroadcast()
  } else {
    cancelVoiceBroadcast(reason)
  }
}

function handleToggleVoiceBroadcast() {
  setVoiceBroadcastEnabled(!voiceEnabled.value, 'toolbar_toggle')
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

function isMessagesScrolledNearBottom(): boolean {
  const container = messagesContainer.value
  if (!container) return true
  const distanceToBottom = container.scrollHeight - container.clientHeight - container.scrollTop
  return distanceToBottom <= MESSAGE_AUTO_SCROLL_BOTTOM_THRESHOLD_PX
}

function handleMessagesContainerScroll() {
  const nearBottom = isMessagesScrolledNearBottom()
  messagesAutoFollow.value = nearBottom
  if (nearBottom) {
    hasNewMessagesBelow.value = false
  }
}

function scheduleMessagesScrollToBottom(options: { force?: boolean; notify?: boolean } = {}) {
  const shouldFollow = options.force || messagesAutoFollow.value || isMessagesScrolledNearBottom()
  if (!shouldFollow) {
    if (options.notify !== false) {
      hasNewMessagesBelow.value = true
    }
    return
  }
  if (options.force) {
    messagesAutoFollow.value = true
  }
  hasNewMessagesBelow.value = false
  if (messagesScrollFrameId !== null) return
  messagesScrollFrameId = window.requestAnimationFrame(() => {
    messagesScrollFrameId = null
    void nextTick(() => {
      const container = messagesContainer.value
      if (!container) return
      container.scrollTop = container.scrollHeight
      messagesAutoFollow.value = true
      hasNewMessagesBelow.value = false
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

interface TextRuntimeStateMessage {
  role: 'user' | 'assistant'
  content: string
}

interface TextRuntimeStateResponse {
  session_id: string
  conversation_id: string
  audience: string
  active: boolean
  message_count: number
  latest_event_seq?: number
  messages: TextRuntimeStateMessage[]
}

interface ClientReminderRecord {
  id: string
  message: string
  dueAt: string
  audience: string
  sessionId: string
  conversationId: string
  sourceText?: string
}

interface ConversationArchiveOptions {
  preserveOrder?: boolean
}

const CONVERSATION_TITLE_OVERRIDES_KEY = 'soulmeet.chat.conversationTitleOverrides.v1'
const GUEST_RUNTIME_SESSION_KEY = 'soulmeet.chat.guestRuntimeSessionId.v1'
const CLIENT_REMINDERS_STORAGE_KEY = 'soulmeet.chat.clientReminders.v1'
const CLIENT_REMINDER_TIMER_MAX_MS = 2_147_000_000

const ARCHIVE_PREVIEW_MESSAGE_LIMIT = 8
const clientReminderCleanupTimers = new Map<string, ReturnType<typeof setTimeout>>()

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
      firstTokenAt: message.firstTokenAt ? new Date(message.firstTokenAt) : undefined,
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

function clientReminderObject(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

function clientReminderText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function clientReminderDelayMsFromText(text: string): number | null {
  const match = text.trim().toLowerCase().match(
    /(\d+(?:\.\d+)?)\s*(s|sec|secs|second|seconds|秒|秒钟|m|min|mins|minute|minutes|分钟|h|hr|hrs|hour|hours|小时|d|day|days|天|日)\s*后?/,
  )
  if (!match) return null
  const amount = Number.parseFloat(match[1])
  if (!Number.isFinite(amount) || amount <= 0) return null
  const unit = match[2]
  if (unit.startsWith('s') || unit === '秒' || unit === '秒钟') return amount * 1000
  if (unit.startsWith('m') || unit === '分钟') return amount * 60_000
  if (unit.startsWith('h') || unit === '小时') return amount * 3_600_000
  return amount * 86_400_000
}

function latestUserMessageTimeForReminder(sourceText: string): number | null {
  const normalized = sourceText.trim()
  if (!normalized) return null
  const matched = [...messages.value].reverse().find(message => (
    message.role === 'user'
    && getChatMessageText(message).trim() === normalized
  ))
  return matched ? matched.timestamp.getTime() : null
}

function resolveClientReminderDueAtMs(dueAtRaw: string, sourceText: string): number {
  const explicitDelayMs = clientReminderDelayMsFromText(sourceText)
  if (explicitDelayMs !== null) {
    const userMessageAt = latestUserMessageTimeForReminder(sourceText) ?? Date.now()
    return userMessageAt + explicitDelayMs
  }
  return Date.parse(dueAtRaw)
}

function clientReminderLooksLikeJob(record: Record<string, unknown>): boolean {
  const id = clientReminderText(record.id)
  const message = clientReminderText(record.message)
  const dueAt = clientReminderText(record.due_at) || clientReminderText(record.dueAt)
  return Boolean(id && message && dueAt && Number.isFinite(Date.parse(dueAt)))
}

function findClientReminderJob(value: unknown): Record<string, unknown> | null {
  const seen = new Set<unknown>()
  const visit = (node: unknown, depth: number): Record<string, unknown> | null => {
    if (!node || depth > 8) return null
    if (Array.isArray(node)) {
      for (const item of node) {
        const found = visit(item, depth + 1)
        if (found) return found
      }
      return null
    }

    const record = clientReminderObject(node)
    if (!record || seen.has(record)) return null
    seen.add(record)

    const directReminder = clientReminderObject(record.reminder)
    if (directReminder && clientReminderLooksLikeJob(directReminder)) {
      return directReminder
    }
    if (clientReminderLooksLikeJob(record)) {
      return record
    }
    for (const item of Object.values(record)) {
      const found = visit(item, depth + 1)
      if (found) return found
    }
    return null
  }
  return visit(value, 0)
}

function clientReminderFromArtifact(
  artifact: Record<string, unknown> | undefined,
): { reminder: ClientReminderRecord; status: string } | null {
  const job = findClientReminderJob(artifact)
  if (!job) return null

  const id = clientReminderText(job.id)
  const message = clientReminderText(job.message)
  const dueAtRaw = clientReminderText(job.due_at) || clientReminderText(job.dueAt)
  const sourceText = clientReminderText(job.source_text)
  const dueAtMs = resolveClientReminderDueAtMs(dueAtRaw, sourceText)
  if (!id || !message || !Number.isFinite(dueAtMs)) return null

  const reminder: ClientReminderRecord = {
    id,
    message,
    dueAt: new Date(dueAtMs).toISOString(),
    audience: clientReminderText(job.audience) || sessionStore.selectedAudience,
    sessionId: clientReminderText(job.session_id) || textChatSessionId.value || sessionStore.sessionInfo?.sessionId || '',
    conversationId: clientReminderText(job.conversation_id) || activeConversationId.value || '',
    sourceText: sourceText || undefined,
  }
  return {
    reminder,
    status: clientReminderText(job.status),
  }
}

function normalizeStoredClientReminder(value: unknown): ClientReminderRecord | null {
  const record = clientReminderObject(value)
  if (!record) return null
  const id = clientReminderText(record.id)
  const message = clientReminderText(record.message)
  const dueAt = clientReminderText(record.dueAt)
  if (!id || !message || !dueAt || !Number.isFinite(Date.parse(dueAt))) return null
  return {
    id,
    message,
    dueAt,
    audience: clientReminderText(record.audience) || sessionStore.selectedAudience,
    sessionId: clientReminderText(record.sessionId),
    conversationId: clientReminderText(record.conversationId),
    sourceText: clientReminderText(record.sourceText) || undefined,
  }
}

function readClientReminders(): ClientReminderRecord[] {
  if (typeof window === 'undefined') return []
  try {
    const raw = window.localStorage.getItem(CLIENT_REMINDERS_STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed
      .map(normalizeStoredClientReminder)
      .filter((item): item is ClientReminderRecord => Boolean(item))
  } catch (err) {
    console.warn('[ClientReminder] 读取本地提醒失败:', err)
    return []
  }
}

function writeClientReminders(reminders: ClientReminderRecord[]) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(CLIENT_REMINDERS_STORAGE_KEY, JSON.stringify(reminders))
  } catch (err) {
    console.warn('[ClientReminder] 保存本地提醒失败:', err)
  }
}

function shouldUseNativeLocalReminder(): boolean {
  return Capacitor.isNativePlatform() && Capacitor.getPlatform() === 'ios'
}

async function scheduleNativeClientReminder(reminder: ClientReminderRecord) {
  if (!shouldUseNativeLocalReminder()) return
  try {
    const result = await LocalReminder.schedule({
      id: reminder.id,
      title: 'Aini 提醒',
      body: `提醒时间到了：${reminder.message}`,
      dueAt: reminder.dueAt,
    })
    if (result.permission === 'denied') {
      console.warn('[ClientReminder] iOS 通知权限未开启，无法创建系统提醒:', reminder.id)
    }
  } catch (err) {
    console.warn('[ClientReminder] iOS 本地提醒排程失败:', reminder.id, err)
  }
}

async function cancelNativeClientReminder(id: string) {
  if (!shouldUseNativeLocalReminder()) return
  try {
    await LocalReminder.cancel({ id })
  } catch (err) {
    console.warn('[ClientReminder] iOS 本地提醒取消失败:', id, err)
  }
}

function scheduleClientReminderCleanup(reminder: ClientReminderRecord) {
  const oldTimer = clientReminderCleanupTimers.get(reminder.id)
  if (oldTimer) clearTimeout(oldTimer)

  const delayMs = Date.parse(reminder.dueAt) - Date.now()
  if (!Number.isFinite(delayMs) || delayMs <= 0) {
    removeClientReminder(reminder.id)
    return
  }
  const delay = delayMs > CLIENT_REMINDER_TIMER_MAX_MS
    ? CLIENT_REMINDER_TIMER_MAX_MS
    : delayMs + 3000
  const timer = setTimeout(() => {
    clientReminderCleanupTimers.delete(reminder.id)
    if (delayMs > CLIENT_REMINDER_TIMER_MAX_MS) {
      scheduleClientReminderCleanup(reminder)
    } else {
      removeClientReminder(reminder.id)
    }
  }, delay)
  clientReminderCleanupTimers.set(reminder.id, timer)
}

function removeClientReminder(id: string, options: { cancelNative?: boolean } = {}) {
  const timer = clientReminderCleanupTimers.get(id)
  if (timer) {
    clearTimeout(timer)
    clientReminderCleanupTimers.delete(id)
  }
  const next = readClientReminders().filter(item => item.id !== id)
  writeClientReminders(next)
  if (options.cancelNative) {
    void cancelNativeClientReminder(id)
  }
}

function upsertClientReminder(reminder: ClientReminderRecord) {
  const dueAtMs = Date.parse(reminder.dueAt)
  if (!Number.isFinite(dueAtMs) || dueAtMs <= Date.now()) {
    removeClientReminder(reminder.id)
    return
  }
  const next = [
    ...readClientReminders().filter(item => item.id !== reminder.id && Date.parse(item.dueAt) > Date.now()),
    reminder,
  ]
  writeClientReminders(next)
  scheduleClientReminderCleanup(reminder)
  void scheduleNativeClientReminder(reminder)
}

function syncClientReminderFromArtifact(artifact: Record<string, unknown> | undefined, source?: string) {
  const extracted = clientReminderFromArtifact(artifact)
  if (!extracted) return

  const dueAtMs = Date.parse(extracted.reminder.dueAt)
  if (
    extracted.status === 'delivered'
    || source === 'soul_companion:reminder'
    || !Number.isFinite(dueAtMs)
    || dueAtMs <= Date.now()
  ) {
    removeClientReminder(extracted.reminder.id, { cancelNative: source === 'soul_companion:reminder' })
    return
  }
  upsertClientReminder(extracted.reminder)
}

function restoreClientReminders() {
  const now = Date.now()
  const pending = readClientReminders().filter(item => Date.parse(item.dueAt) > now)
  writeClientReminders(pending)
  for (const reminder of pending) {
    scheduleClientReminderCleanup(reminder)
    void scheduleNativeClientReminder(reminder)
  }
}

function clearClientReminderCleanupTimers() {
  for (const timer of clientReminderCleanupTimers.values()) {
    clearTimeout(timer)
  }
  clientReminderCleanupTimers.clear()
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

function messageDisplayTimestamp(message: ChatMessage): Date {
  return message.role === 'assistant'
    ? message.firstTokenAt || message.timestamp
    : message.timestamp
}

function upsertConversationArchive(sessionId: string, sourceMessages: ChatMessage[], options: ConversationArchiveOptions = {}) {
  if (!authStore.isLoggedIn) return
  const archivedMessages = cloneMessagesForArchive(sourceMessages)
  if (!sessionId || archivedMessages.length === 0) return

  const latestMessage = [...sourceMessages].reverse().find(message => getChatMessageText(message).trim())
  const updatedAt = latestMessage ? messageDisplayTimestamp(latestMessage).getTime() : Date.now()
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

function runtimeStateMessageToChatMessage(item: TextRuntimeStateMessage, index: number): ChatMessage {
  const text = item.content
  return {
    id: `runtime-${index}-${item.role}-${text.length}`,
    role: item.role,
    text,
    contentBlocks: item.role === 'assistant' && text.trim()
      ? [{
          id: 'main',
          type: 'markdown',
          text,
        }]
      : undefined,
    timestamp: new Date(),
  }
}

function committedMessagesForRecovery() {
  return messages.value.filter(message => (
    getChatMessageText(message).trim()
    && !message.pending
  ))
}

function shouldApplyRecoveredMessages(restoredMessages: ChatMessage[]): boolean {
  const restoredContentMessages = restoredMessages.filter(message => getChatMessageText(message).trim())
  if (!restoredContentMessages.length) return false

  const committedLocalMessages = committedMessagesForRecovery()
  const localLast = committedLocalMessages[committedLocalMessages.length - 1]
  const restoredLast = restoredContentMessages[restoredContentMessages.length - 1]
  const localLastText = localLast ? getChatMessageText(localLast).trim() : ''
  const restoredLastText = getChatMessageText(restoredLast).trim()

  if (restoredContentMessages.length > committedLocalMessages.length) return true
  if (streamingMessage.value?.pending && restoredLast.role === 'assistant') return true
  if (streamingMessage.value?.streaming && restoredLast.role === 'assistant' && restoredLastText) return true
  return Boolean(restoredLastText && restoredLastText !== localLastText && restoredContentMessages.length >= committedLocalMessages.length)
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
    scheduleMessagesScrollToBottom({ force: true })
    const archive = conversationRecordToArchive(data.conversation, restoredMessages)
    conversationArchives.value = [archive, ...conversationArchives.value.filter(item => item.sessionId !== archive.sessionId)]
      .map((item, index) => ({ ...item, id: index + 1, active: false }))
  } finally {
    isConversationHydrating.value = false
  }
}

async function syncActiveConversationFromServer(reason: string): Promise<boolean> {
  if (!authStore.isLoggedIn || !activeConversationId.value || activeConversationId.value === 'guest') return false
  try {
    const response = await fetch(apiUrl(`/api/conversations/${encodeURIComponent(activeConversationId.value)}`), {
      headers: authJsonHeaders(),
      cache: 'no-store',
    })
    if (!response.ok) return false
    const data = await response.json() as { conversation: ConversationRecord; messages: ConversationMessageRecord[] }
    const restoredMessages = data.messages.map(apiMessageToChatMessage)
    if (!shouldApplyRecoveredMessages(restoredMessages)) return false
    replaceMessages(restoredMessages)
    scheduleMessagesScrollToBottom({ force: true })
    const archive = conversationRecordToArchive(data.conversation, restoredMessages)
    conversationArchives.value = [archive, ...conversationArchives.value.filter(item => item.sessionId !== archive.sessionId)]
      .map((item, index) => ({ ...item, id: index + 1, active: false }))
    console.info('[TextRuntime] 已从对话历史恢复消息', {
      reason,
      conversation_id: activeConversationId.value,
      restored_count: restoredMessages.length,
    })
    return true
  } catch (err) {
    console.warn('[TextRuntime] 对话历史恢复失败:', err)
    return false
  }
}

async function syncRuntimeSessionState(reason: string): Promise<TextRuntimeStateResponse | null> {
  const sessionId = textChatSessionId.value || sessionStore.sessionInfo?.sessionId || ''
  if (!sessionId) return null
  const params = new URLSearchParams({
    audience: sessionStore.selectedAudience,
  })
  if (authStore.token) {
    params.set('token', authStore.token)
  }
  if (activeConversationId.value) {
    params.set('conversation_id', activeConversationId.value)
  }
  try {
    const response = await fetch(apiUrl(`/api/text-runtime/session/${encodeURIComponent(sessionId)}/state?${params.toString()}`), {
      cache: 'no-store',
    })
    if (!response.ok) return null
    const state = await response.json() as TextRuntimeStateResponse
    const restoredMessages = state.messages.map(runtimeStateMessageToChatMessage)
    if (shouldApplyRecoveredMessages(restoredMessages)) {
      replaceMessages(restoredMessages)
      scheduleMessagesScrollToBottom({ force: true })
      console.info('[TextRuntime] 已从运行时状态恢复消息', {
        reason,
        session_id: sessionId,
        active: state.active,
        restored_count: restoredMessages.length,
      })
    }
    return state
  } catch (err) {
    console.warn('[TextRuntime] 运行时状态恢复失败:', err)
    return null
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
    time: formatTime(messageDisplayTimestamp(message)),
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
  if (messagesScrollElement) {
    messagesScrollElement.removeEventListener('scroll', handleMessagesContainerScroll)
    messagesScrollElement = null
  }

  messagesContainer.value = el instanceof HTMLElement ? el : null
  if (messagesContainer.value) {
    messagesScrollElement = messagesContainer.value
    messagesScrollElement.addEventListener('scroll', handleMessagesContainerScroll, { passive: true })
    messagesAutoFollow.value = isMessagesScrolledNearBottom()
    hasNewMessagesBelow.value = false
    scheduleMessagesScrollToBottom({ force: true })
  }
}

function scrollMessagesToBottom() {
  scheduleMessagesScrollToBottom({ force: true })
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

class TextRequestTimeoutError extends Error {
  constructor() {
    super('回复等待超时，请检查网络后再试。')
  }
}

function textSendErrorMessage(err: unknown): string {
  if (err instanceof TextRequestTimeoutError) return err.message
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

function shouldUseNativeTextProgress(): boolean {
  return Capacitor.isNativePlatform() && Capacitor.getPlatform() === 'ios'
}

function buildTextProgressEventsUrl(sessionId: string, options: { replayMissed?: boolean } = {}): string {
  const params = new URLSearchParams({
    audience: sessionStore.selectedAudience,
  })
  if (authStore.token) {
    params.set('token', authStore.token)
  }
  if (activeConversationId.value) {
    params.set('conversation_id', activeConversationId.value)
  }
  if (options.replayMissed) {
    params.set('replay', '1')
    if (lastTextProgressEventSeq > 0) {
      params.set('since', String(lastTextProgressEventSeq))
    }
  }
  return apiUrl(`/api/text-runtime/events/${encodeURIComponent(sessionId)}?${params.toString()}`)
}

function isTextProgressMessageType(type: string | undefined): boolean {
  return type === 'assistant_process'
    || type === 'task_progress'
    || type === 'assistant_text'
    || type === 'assistant_text_stream'
    || type === 'assistant_message_start'
    || type === 'assistant_sources'
    || type === 'content_block_start'
    || type === 'content_block_delta'
    || type === 'content_block_finish'
    || type === 'assistant_message_finish'
    || type === 'assistant_text_interrupted'
}

function shouldAcceptPassiveTextProgressMessage(message: { message_id?: string; source?: string }): boolean {
  const source = typeof message.source === 'string' ? message.source : ''
  const messageId = typeof message.message_id === 'string' ? message.message_id : ''
  if (source && PASSIVE_TEXT_PROGRESS_SOURCES.has(source)) {
    if (messageId) passiveTextProgressMessageIds.add(messageId)
    return true
  }
  return Boolean(messageId && passiveTextProgressMessageIds.has(messageId))
}

function finalizePassiveTextProgressMessage(message: { type?: string; message_id?: string }) {
  const messageId = typeof message.message_id === 'string' ? message.message_id : ''
  if (!messageId) return
  if (
    message.type === 'assistant_text'
    || message.type === 'assistant_message_finish'
    || message.type === 'assistant_text_interrupted'
  ) {
    passiveTextProgressMessageIds.delete(messageId)
  }
}

function beginTextProgressRequest(sessionId: string, reason: string): number {
  const requestSeq = ++textProgressRequestSeq
  activeTextProgressRequestSeq = requestSeq
  textProgressAcceptingMessages = true
  textProgressReplayAcceptingMessages = false
  textProgressActiveSessionId = sessionId
  console.info('[TextProgress] 请求开始', {
    request_seq: requestSeq,
    session_id: sessionId,
    reason,
  })
  return requestSeq
}

function finishTextProgressRequest(requestSeq: number, reason: string) {
  if (!requestSeq || requestSeq !== activeTextProgressRequestSeq) return
  console.info('[TextProgress] 请求结束', {
    request_seq: requestSeq,
    session_id: textProgressActiveSessionId,
    reason,
  })
  textProgressAcceptingMessages = false
  textProgressActiveSessionId = textProgressEventSessionId || textProgressNativeSessionId || ''
  activeTextProgressRequestSeq = 0
}

function handleTextProgressEventData(data: string, settleReady?: () => void) {
  if (!data) return
  try {
    const msg = JSON.parse(data) as { type?: string; _seq?: number }
    if (typeof msg._seq === 'number' && Number.isFinite(msg._seq)) {
      lastTextProgressEventSeq = Math.max(lastTextProgressEventSeq, msg._seq)
    }
    if (msg.type === 'text_progress_connected') {
      settleReady?.()
      return
    }
    if (isTextProgressMessageType(msg.type)) {
      const message = msg as { type?: string; message_id?: string; role?: string; source?: string }
      const passiveAccepted = shouldAcceptPassiveTextProgressMessage(message)
      if (!textProgressAcceptingMessages && !textProgressReplayAcceptingMessages && !passiveAccepted) {
        console.info('[TextProgress] 丢弃非活跃进度消息', {
          type: message.type,
          message_id: message.message_id || null,
          active_request_seq: activeTextProgressRequestSeq,
          active_session_id: textProgressActiveSessionId || null,
        })
        return
      }
      console.info('[TextProgress] 进度消息进入生命周期', {
        type: message.type,
        message_id: message.message_id || null,
        role: message.role || null,
        request_seq: activeTextProgressRequestSeq,
        session_id: textProgressActiveSessionId || null,
        replay_recovery: textProgressReplayAcceptingMessages,
        passive_accepted: passiveAccepted,
      })
      handleTextRuntimeServerMessage(msg as ServerMessage)
      finalizePassiveTextProgressMessage(message)
    }
  } catch (err) {
    console.warn('[TextProgress] 进度消息解析失败:', err, '原始数据:', data)
  }
}

async function closeNativeTextProgressEvents(): Promise<void> {
  const handles = textProgressNativeListenerHandles
  const hadNativeStream = Boolean(textProgressNativeSessionId) || handles.length > 0
  textProgressNativeListenerHandles = []
  textProgressNativeSessionId = ''

  for (const handle of handles) {
    void handle.remove()
  }
  if (hadNativeStream) {
    await NativeTextProgress.stop().catch((err) => {
      console.warn('[TextProgress] 原生进度通道关闭失败:', err)
    })
  }
}

function closeTextProgressEvents() {
  textProgressAcceptingMessages = false
  textProgressReplayAcceptingMessages = false
  textProgressActiveSessionId = ''
  activeTextProgressRequestSeq = 0
  passiveTextProgressMessageIds.clear()
  if (textProgressEventSource) {
    textProgressEventSource.close()
    textProgressEventSource = null
  }
  void closeNativeTextProgressEvents()
  textProgressEventSessionId = ''
  textProgressReadyPromise = null
}

async function ensurePassiveTextProgressEvents(reason: string) {
  const sessionId = textChatSessionId.value || sessionStore.sessionInfo?.sessionId || ''
  if (!sessionId) return
  try {
    await openTextProgressEvents(sessionId)
  } catch (err) {
    console.warn('[TextProgress] 被动监听启动失败:', reason, err)
  }
}

function openTextProgressEvents(
  sessionId: string,
  options: { replayMissed?: boolean; allowInactiveReplay?: boolean } = {},
): Promise<void> {
  textProgressReplayAcceptingMessages = Boolean(options.allowInactiveReplay)
  if (shouldUseNativeTextProgress()) {
    return openNativeTextProgressEvents(sessionId, options)
  }

  if (typeof EventSource === 'undefined') return Promise.resolve()
  if (
    !options.replayMissed
    &&
    textProgressEventSource
    && textProgressEventSessionId === sessionId
    && textProgressEventSource.readyState !== EventSource.CLOSED
  ) {
    return textProgressEventSource.readyState === EventSource.OPEN
      ? Promise.resolve()
      : textProgressReadyPromise || Promise.resolve()
  }

  closeTextProgressEvents()
  textProgressReplayAcceptingMessages = Boolean(options.allowInactiveReplay)
  const source = new EventSource(buildTextProgressEventsUrl(sessionId, options))
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
      handleTextProgressEventData(event.data, settleReady)
    }
  })
  textProgressReadyPromise = readyPromise
  return readyPromise
}

async function openNativeTextProgressEvents(
  sessionId: string,
  options: { replayMissed?: boolean; allowInactiveReplay?: boolean } = {},
): Promise<void> {
  if (!options.replayMissed && textProgressNativeSessionId === sessionId && textProgressNativeListenerHandles.length > 0) {
    return textProgressReadyPromise || Promise.resolve()
  }

  if (textProgressEventSource) {
    textProgressEventSource.close()
    textProgressEventSource = null
  }
  await closeNativeTextProgressEvents()
  textProgressEventSessionId = ''
  textProgressReadyPromise = null

  textProgressNativeSessionId = sessionId
  const url = buildTextProgressEventsUrl(sessionId, options)

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

    readyTimer = setTimeout(settleReady, 2000)
    Promise.all([
      NativeTextProgress.addListener('open', (event) => {
        if (typeof event.status === 'number' && event.status >= 400) {
          console.warn('[TextProgress] 原生进度通道响应异常:', event.status)
        }
        settleReady()
      }),
      NativeTextProgress.addListener('message', (event) => {
        handleTextProgressEventData(event.data || '', settleReady)
      }),
      NativeTextProgress.addListener('error', (event) => {
        console.warn('[TextProgress] 原生进度通道错误:', event.message || event)
        if (textProgressNativeSessionId === sessionId) {
          textProgressNativeSessionId = ''
        }
        settleReady()
      }),
      NativeTextProgress.addListener('closed', () => {
        if (textProgressNativeSessionId === sessionId) {
          textProgressNativeSessionId = ''
        }
        settleReady()
      }),
    ])
      .then((handles) => {
        textProgressNativeListenerHandles = handles
        return NativeTextProgress.start({ url })
      })
      .catch((err) => {
        console.warn('[TextProgress] 原生进度通道启动失败:', err)
        closeNativeTextProgressEvents()
        settleReady()
      })
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

function hasUnfinishedTextResponse(): boolean {
  return textRuntimeRecoveryNeeded
    || isSendingText.value
    || Boolean(streamingMessage.value?.pending)
    || Boolean(streamingMessage.value?.streaming)
}

function isRecoverableTextRuntimeError(err: unknown): boolean {
  if (err instanceof TextRequestTimeoutError) return true
  if (err instanceof TypeError) return true
  if (err instanceof DOMException) {
    return ['NetworkError', 'AbortError', 'TimeoutError'].includes(err.name)
  }
  return err instanceof Error && /network|abort|cancel|断开|连接/i.test(err.message)
}

function clearTextRuntimeRecoveryTimer() {
  if (textRuntimeRecoveryTimer !== null) {
    clearTimeout(textRuntimeRecoveryTimer)
    textRuntimeRecoveryTimer = null
  }
}

function scheduleTextRuntimeRecovery(reason: string, delayMs = 0) {
  if (!textChatSessionId.value && !sessionStore.sessionInfo?.sessionId) return
  clearTextRuntimeRecoveryTimer()
  textRuntimeRecoveryTimer = setTimeout(() => {
    textRuntimeRecoveryTimer = null
    void recoverTextRuntimeSession(reason)
  }, delayMs)
}

async function recoverTextRuntimeSession(reason: string) {
  const sessionId = textChatSessionId.value || sessionStore.sessionInfo?.sessionId || ''
  if (!sessionId) return
  const requestSeq = ++textRuntimeRecoverySeq
  console.info('[TextRuntime] 开始恢复文本运行时', {
    reason,
    session_id: sessionId,
    conversation_id: activeConversationId.value || null,
    last_event_seq: lastTextProgressEventSeq,
  })

  try {
    await openTextProgressEvents(sessionId, {
      replayMissed: true,
      allowInactiveReplay: true,
    })
    const runtimeState = await syncRuntimeSessionState(reason)
    await syncActiveConversationFromServer(reason)

    const stillActive = Boolean(runtimeState?.active)
    const uiStillWaiting = isSendingText.value
      || Boolean(streamingMessage.value?.pending)
      || Boolean(streamingMessage.value?.streaming)
    if (requestSeq !== textRuntimeRecoverySeq) return
    if (stillActive || uiStillWaiting) {
      scheduleTextRuntimeRecovery('runtime_still_active', stillActive ? 2200 : 4200)
      return
    }
    textRuntimeRecoveryNeeded = false
  } catch (err) {
    console.warn('[TextRuntime] 文本运行时恢复失败:', err)
    if (hasUnfinishedTextResponse()) {
      scheduleTextRuntimeRecovery('recover_retry', 3500)
    }
  }
}

async function sendChatMessage(text: string) {
  if (authStore.isLoggedIn) {
    await ensureLoggedConversation()
  }
  const sessionId = ensureTextRuntimeSession()
  await openTextProgressEvents(sessionId)
  const progressRequestSeq = beginTextProgressRequest(sessionId, 'send_message')
  const controller = new AbortController()
  textMessageAbortController = controller
  let requestTimedOut = false
  const requestTimeoutTimer = setTimeout(() => {
    requestTimedOut = true
    controller.abort()
  }, TEXT_RUNTIME_HTTP_REQUEST_TIMEOUT_MS)

  try {
    let response: Response
    try {
      response = await fetch(apiUrl('/api/text-runtime/message'), {
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
    } catch (err) {
      if (requestTimedOut && isAbortError(err)) {
        throw new TextRequestTimeoutError()
      }
      throw err
    }
    if (!response.ok) {
      throw new TextChannelError(response.status)
    }
    const data = await response.json() as {
      session_id: string
      conversation_id: string
      audience: string
      message_id?: string
      id?: string
      text: string
      source: string
      first_token_at?: string
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
      finishTextProgressRequest(progressRequestSeq, 'http_final_response')
      handleTextRuntimeServerMessage({
        type: 'assistant_text',
        message_id: data.message_id || data.id,
        text: data.text,
        source: data.source,
        first_token_at: data.first_token_at,
        artifact: data.artifact || undefined,
      })
    }
    textRuntimeRecoveryNeeded = false
    upsertConversationArchive(activeConversationId.value, messages.value)
  } finally {
    clearTimeout(requestTimeoutTimer)
    finishTextProgressRequest(progressRequestSeq, 'request_finally')
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

  await openTextProgressEvents(sessionId)
  const progressRequestSeq = beginTextProgressRequest(sessionId, 'task_retry')
  isRetryingTask.value = true
  const controller = new AbortController()
  let requestTimedOut = false
  const requestTimeoutTimer = setTimeout(() => {
    requestTimedOut = true
    controller.abort()
  }, TEXT_RUNTIME_HTTP_REQUEST_TIMEOUT_MS)
  try {
    let response: Response
    try {
      response = await fetch(apiUrl(`/api/text-runtime/session/${encodeURIComponent(sessionId)}/task-retry`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({
          audience: sessionStore.selectedAudience,
          conversation_id: activeConversationId.value || undefined,
          token: authStore.token ?? '',
          retry_token: retryToken,
          timeout_seconds: textRuntimeTimeoutSeconds,
        }),
      })
    } catch (err) {
      if (requestTimedOut && isAbortError(err)) {
        throw new TextRequestTimeoutError()
      }
      throw err
    }
    if (!response.ok) {
      throw new TextChannelError(response.status)
    }
    const data = await response.json() as {
      session_id: string
      conversation_id: string
      audience: string
      message_id?: string
      id?: string
      text: string
      source: string
      first_token_at?: string
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
      finishTextProgressRequest(progressRequestSeq, 'task_retry_http_final_response')
      handleTextRuntimeServerMessage({
        type: 'assistant_text',
        message_id: data.message_id || data.id,
        text: data.text,
        source: data.source || 'task_retry',
        first_token_at: data.first_token_at,
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
    clearTimeout(requestTimeoutTimer)
    finishTextProgressRequest(progressRequestSeq, 'task_retry_finally')
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
  finishTextProgressRequest(activeTextProgressRequestSeq, 'stop_response')
  textRuntimeRecoveryNeeded = false
  clearTextRuntimeRecoveryTimer()
  isSendingText.value = false
  interruptResponse()
  cancelVoiceBroadcast('stop_response')

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
  resetVoiceBroadcastDedup()
  startAssistantPending('typing')
  scheduleMessagesScrollToBottom({ force: true })
  inputText.value = ''

  textRuntimeRecoveryNeeded = true
  isSendingText.value = true
  try {
    if (voiceEnabled.value) {
      await ensureLiveKitVoiceBroadcastChannel('send_message')
    }
    await sendChatMessage(text)
    textRuntimeRecoveryNeeded = false
  } catch (err) {
    if (err instanceof TextRequestTimeoutError) {
      textRuntimeRecoveryNeeded = false
      clearAssistantPending()
      showSendError(textSendErrorMessage(err))
      scheduleTextRuntimeRecovery('send_request_timeout', 300)
      return
    }
    if (isAbortError(err)) {
      return
    }
    if (isRecoverableTextRuntimeError(err)) {
      console.warn('[TextRuntime] 文本请求断开，进入后台恢复流程:', err)
      textRuntimeRecoveryNeeded = false
      clearAssistantPending()
      showSendError('网络连接不稳定，正在尝试同步回复')
      scheduleTextRuntimeRecovery('send_request_disconnected', 300)
      return
    }
    textRuntimeRecoveryNeeded = false
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
  if (typeof document !== 'undefined') {
    const activeElement = document.activeElement as HTMLElement | null
    activeElement?.blur?.()
  }
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

async function setRealtimeInteractionActive(active: boolean) {
  const requestSeq = ++realtimeInteractionRequestSeq
  console.info('[ChatPage] 实时互动模式切换', {
    active,
    requestSeq,
    sessionStatus: sessionStore.status,
    voiceEnabled: voiceEnabled.value,
    voiceChannelOpen: isVoiceChannelOpen.value,
    realtimeOn: isRealtimeChatOn.value,
  })

  if (!active) {
    isRealtimeChatOn.value = false
    isHoldingToTalk.value = false
    setMicMuted(true)
    if (!voiceEnabled.value && (sessionStore.status === 'connected' || sessionStore.status === 'connecting')) {
      disconnect()
      isVoiceChannelOpen.value = false
    } else {
      isVoiceChannelOpen.value = sessionStore.status === 'connected'
    }
    return
  }

  isVoiceChannelOpen.value = true
  setMicMuted(false)

  if (sessionStore.status !== 'connected') {
    const conversationId = authStore.isLoggedIn ? await ensureLoggedConversation() : activeConversationId.value
    if (requestSeq !== realtimeInteractionRequestSeq) return

    const connected = await connect(sessionStore.selectedAudience, {
      sessionId: sessionStore.sessionInfo?.sessionId,
      conversationId,
    })
    if (requestSeq !== realtimeInteractionRequestSeq) {
      disconnect()
      return
    }
    if (!connected) {
      isVoiceChannelOpen.value = false
      isRealtimeChatOn.value = false
      setMicMuted(true)
      showSendError(sessionStore.errorMessage || '实时语音连接失败，请稍后再试')
      return
    }
    if (connected.conversationId) {
      activeConversationId.value = connected.conversationId
    }
  }

  isVoiceChannelOpen.value = true
  isRealtimeChatOn.value = true
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
    nativeKeyboardInset = 0
    keyboardInset.value = 0
    return
  }
  const vv = window.visualViewport
  const layoutHeight = Math.max(window.innerHeight, document.documentElement.clientHeight || 0)
  const layoutWidth = window.innerWidth
  const visualInset = vv
    ? Math.max(0, Math.round(layoutHeight - vv.height - vv.offsetTop))
    : 0

  if (nativeKeyboardInset < KEYBOARD_INSET_MIN_PX && visualInset < KEYBOARD_INSET_MIN_PX) {
    if (Math.abs(layoutWidth - layoutViewportBaselineWidth) > 24) {
      layoutViewportBaselineWidth = layoutWidth
      layoutViewportMaxHeight = layoutHeight
    }
    layoutViewportMaxHeight = Math.max(layoutViewportMaxHeight, layoutHeight)
  }

  const sameViewportWidth = Math.abs(layoutWidth - layoutViewportBaselineWidth) <= 24
  const viewportResizedForKeyboard = nativeKeyboardInset >= KEYBOARD_INSET_MIN_PX
    && sameViewportWidth
    && layoutViewportMaxHeight > 0
    && layoutHeight <= layoutViewportMaxHeight - KEYBOARD_INSET_MIN_PX
  const inset = viewportResizedForKeyboard ? visualInset : Math.max(nativeKeyboardInset, visualInset)
  const nextInset = inset >= KEYBOARD_INSET_MIN_PX ? inset : 0
  if (keyboardInset.value !== nextInset) {
    keyboardInset.value = nextInset
    scheduleMessagesScrollToBottom({ notify: false })
  }
}

function handleNativeKeyboardInset(event: Event) {
  const detail = (event as CustomEvent<NativeKeyboardInsetEventDetail>).detail
  const height = Number(detail?.height ?? 0)
  nativeKeyboardInset = Number.isFinite(height) ? Math.max(0, Math.round(height)) : 0
  updateKeyboardInset()
}

function clearKeyboardInsetRefreshTimers() {
  for (const timer of keyboardInsetRefreshTimers) {
    clearTimeout(timer)
  }
  keyboardInsetRefreshTimers = []
}

function scheduleKeyboardInsetRefresh() {
  clearKeyboardInsetRefreshTimers()
  keyboardInsetRefreshTimers = KEYBOARD_INSET_REFRESH_DELAYS_MS.map(delay =>
    setTimeout(updateKeyboardInset, delay),
  )
}

function handleAppForeground(reason = 'foreground') {
  updateMobileFlags()
  updateKeyboardInset()
  if (typeof document !== 'undefined' && document.hidden) return
  restoreClientReminders()
  void ensurePassiveTextProgressEvents(reason)
  if (hasUnfinishedTextResponse()) {
    scheduleTextRuntimeRecovery(reason, 120)
  }
}

function handleVisibilityChange() {
  if (document.hidden) {
    closeTextProgressEvents()
    return
  }
  handleAppForeground('visibilitychange')
}

function handleWindowFocus() {
  handleAppForeground('focus')
}

function handleWindowOnline() {
  handleAppForeground('online')
}

function handleWindowPageShow() {
  handleAppForeground('pageshow')
}

onMessage.value = handleServerMessage

onMounted(() => {
  scheduleQuickActionRefresh(0)
  void (async () => {
    if (authStore.token && !authStore.user) {
      await authStore.fetchMe()
    }
    await initializeConversationRoute()
    restoreClientReminders()
    await ensurePassiveTextProgressEvents('mounted')
    scheduleQuickActionRefresh(0)
  })()
  updateMobileFlags()
  updateKeyboardInset()
  refreshWeather()
  weatherRefreshTimer = setInterval(refreshWeather, WEATHER_REFRESH_MS)
  window.addEventListener('resize', updateMobileFlags)
  window.addEventListener('resize', updateKeyboardInset)
  window.addEventListener('focusin', scheduleKeyboardInsetRefresh, true)
  window.addEventListener('focusout', scheduleKeyboardInsetRefresh, true)
  window.addEventListener('focus', handleWindowFocus)
  window.addEventListener('online', handleWindowOnline)
  window.addEventListener('pageshow', handleWindowPageShow)
  document.addEventListener('visibilitychange', handleVisibilityChange)
  window.addEventListener('soulmeet:keyboard-inset', handleNativeKeyboardInset)
  window.visualViewport?.addEventListener('resize', updateKeyboardInset)
  window.visualViewport?.addEventListener('scroll', updateKeyboardInset)
})

onUnmounted(() => {
  cancelVoiceBroadcast('page_unmounted')
  disposeVoiceBroadcastAudioElement()
  disconnect()
  closeTextProgressEvents()
  stopQuickActionRequest()
  clearClientReminderCleanupTimers()
  void cleanupSpeechRecording()
  window.removeEventListener('resize', updateMobileFlags)
  window.removeEventListener('resize', updateKeyboardInset)
  window.removeEventListener('focusin', scheduleKeyboardInsetRefresh, true)
  window.removeEventListener('focusout', scheduleKeyboardInsetRefresh, true)
  window.removeEventListener('focus', handleWindowFocus)
  window.removeEventListener('online', handleWindowOnline)
  window.removeEventListener('pageshow', handleWindowPageShow)
  document.removeEventListener('visibilitychange', handleVisibilityChange)
  window.removeEventListener('soulmeet:keyboard-inset', handleNativeKeyboardInset)
  window.visualViewport?.removeEventListener('resize', updateKeyboardInset)
  window.visualViewport?.removeEventListener('scroll', updateKeyboardInset)
  clearKeyboardInsetRefreshTimers()
  clearTextRuntimeRecoveryTimer()
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
  if (messagesScrollElement) {
    messagesScrollElement.removeEventListener('scroll', handleMessagesContainerScroll)
    messagesScrollElement = null
  }
})

watch([isRealtimeChatOn, isVoiceChannelOpen], ([realtimeOn, voiceOpen]) => {
  setMicMuted(!(voiceOpen && realtimeOn))
}, { immediate: true })

watch(voiceEnabled, (enabled) => {
  if (!enabled) {
    cancelVoiceBroadcast('voice_disabled')
  }
})

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

watch(() => messages.value.length, () => {
  scheduleMessagesScrollToBottom()
})

watch(() => streamingMessage.value?.streamVersion, () => {
  scheduleMessagesScrollToBottom()
})

watch(assistantProcessText, () => {
  scheduleMessagesScrollToBottom()
})

watch(taskProgress, () => {
  scheduleMessagesScrollToBottom()
}, { deep: true })

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
    :input-mode="inputMode"
    :input-text="inputText"
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
    :set-messages-container="setMessagesContainer"
    :show-scroll-to-bottom-button="hasNewMessagesBelow"
    :task-progress="taskProgress"
    :can-reconnect="canReconnect"
    @update:input-text="inputText = $event"
    @update:show-all-dialog="showAllDialog = $event"
    @update:side-drawer-open="sideDrawerOpen = $event"
    @update:private-space-open="privateSpaceOpen = $event"
    @toggle-voice="handleToggleVoiceBroadcast"
    @toggle-vad-interrupt="toggleVadInterrupt"
    @toggle-webrtc-connection="handleToggleWebrtcConnection"
    @toggle-realtime-chat="toggleRealtimeChat"
    @set-realtime-interaction-active="setRealtimeInteractionActive"
    @toggle-input-mode="toggleInputMode"
    @send="handleSend"
    @stop-response="handleStopBotResponse"
    @keydown-enter="handleKeydown"
    @start-hold-to-talk="startHoldToTalk"
    @end-hold-to-talk="endHoldToTalk"
    @reconnect="handleReconnect"
    @retry-task="retryTextRuntimeTask"
    @open-skill-center="openSkillCenter"
    @scroll-messages-to-bottom="scrollMessagesToBottom"
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
    @toggle-voice="handleToggleVoiceBroadcast"
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
    v-if="!isMobileLayout && !isDesktopStageCollapsed"
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
