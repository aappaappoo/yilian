<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import type { Component, ComponentPublicInstance, PropType } from 'vue'
import type { EmotionState } from '@soulmeet/shared'
import type { ChatMessage, TaskProgressItem, TaskProgressSnapshot } from '../../composables/useChat'
import AgentProcessPreview from './AgentProcessPreview.vue'
import StatusDrawer from '../StatusDrawer.vue'
import BotReplyContent from './BotReplyContent.vue'
import QuickActionBubbles from './QuickActionBubbles.vue'
import TaskProgressCard from './TaskProgressCard.vue'
import { isTaskReplyPresentation } from './botReplyPresentation'
import { useEscapeKey } from '../../composables/useEscapeKey'
import type { ConversationAssistantMessage, ConversationRound } from '../../utils/conversationRounds'

interface SessionItem {
  id: number
  sessionId: string
  icon: string
  title: string
  displayTitle?: string
  time: string
  preview?: string
  active?: boolean
}

interface ConnectionIndicator {
  color: string
  ring: string
  label: string
  pulse: boolean
}

interface WeatherInfo {
  city: string
  temp: string
  condition: string
  icon: string
}

const props = defineProps({
  avatarCanvas: { type: [Object, Function] as PropType<Component>, required: true },
  stageBackgroundUrl: { type: String, required: true },
  modelUrl: { type: String, required: true },
  vrmDisabled: { type: Boolean, default: false },
  botAvatarUrl: { type: String, required: true },
  botDisplayName: { type: String, required: true },
  connectionIndicator: { type: Object as PropType<ConnectionIndicator>, required: true },
  weather: { type: Object as PropType<WeatherInfo>, required: true },
  voiceEnabled: { type: Boolean, required: true },
  voiceChannelOpen: { type: Boolean, required: true },
  vadInterruptEnabled: { type: Boolean, required: true },
  isRealtimeChatOn: { type: Boolean, required: true },
  quickActions: { type: Array as PropType<string[]>, required: true },
  inputMode: { type: String as PropType<'text' | 'ptt'>, required: true },
  inputText: { type: String, required: true },
  quickActionsDisabled: { type: Boolean, default: false },
  isBotResponding: { type: Boolean, default: false },
  isSpeechRecording: { type: Boolean, default: false },
  isSpeechTranscribing: { type: Boolean, default: false },
  sendError: { type: String, default: '' },
  inputPlaceholder: { type: String, required: true },
  displayedSessions: { type: Array as PropType<SessionItem[]>, required: true },
  hasMoreSessions: { type: Boolean, required: true },
  conversationRounds: { type: Array as PropType<ConversationRound[]>, required: true },
  showAllDialog: { type: Boolean, required: true },
  statusPanelOpen: { type: Boolean, required: true },
  privateSpaceOpen: { type: Boolean, required: true },
  sessionStatus: { type: String, required: true },
  emotionState: { type: Object as PropType<EmotionState>, required: true },
  streamingMessage: { type: Object as PropType<ChatMessage | null>, default: null },
  assistantProcessText: { type: String, default: '' },
  renderMarkdown: { type: Function as PropType<(text: string) => string>, required: true },
  userAvatarUrl: { type: String, required: true },
  userDisplayName: { type: String, required: true },
  userAccountName: { type: String, required: true },
  userSubscriptionLabel: { type: String, required: true },
  isUserLoggedIn: { type: Boolean, required: true },
  setMessagesContainer: { type: Function as PropType<(el: Element | ComponentPublicInstance | null) => void>, required: true },
  taskProgress: { type: Object as PropType<TaskProgressSnapshot | null>, default: null },
  canReconnect: { type: Boolean, default: false },
})

const emit = defineEmits<{
  (e: 'update:inputText', value: string): void
  (e: 'update:showAllDialog', value: boolean): void
  (e: 'update:statusPanelOpen', value: boolean): void
  (e: 'update:privateSpaceOpen', value: boolean): void
  (e: 'toggleVoice'): void
  (e: 'toggleVadInterrupt'): void
  (e: 'toggleWebrtcConnection'): void
  (e: 'toggleRealtimeChat'): void
  (e: 'toggleInputMode'): void
  (e: 'send'): void
  (e: 'stopResponse'): void
  (e: 'quickAction', value: string): void
  (e: 'keydownEnter', event: KeyboardEvent): void
  (e: 'startHoldToTalk'): void
  (e: 'endHoldToTalk'): void
  (e: 'reconnect'): void
  (e: 'openSkillCenter'): void
  (e: 'newConversation'): void
  (e: 'continueSession', payload: { sessionId: string; title: string; preview?: string }): void
  (e: 'renameSession', payload: { sessionId: string; title: string }): void
  (e: 'deleteSession', payload: { sessionId: string; title: string }): void
  (e: 'logout'): void
  (e: 'openLogin'): void
  (e: 'openRegister'): void
  (e: 'openSubscription'): void
  (e: 'updateUserAvatar', value: string): void
  (e: 'updateUserDisplayName', value: string): void
  (e: 'updateStagePanelCollapsed', value: boolean): void
  (e: 'retryTask', item: TaskProgressItem): void
}>()

const statusPanelOpenProxy = computed({
  get: () => props.statusPanelOpen,
  set: (value: boolean) => emit('update:statusPanelOpen', value),
})

const isLeftCollapsed = ref(false)
const isRightCollapsed = ref(false)
const isStageCollapsed = ref(false)
const personalInfoOpen = ref(false)
const selectedSessionKey = ref<string | null>(null)
const activeSessionId = computed(() => props.displayedSessions.find(item => item.active)?.sessionId ?? null)
const openSessionActionMenuId = ref<string | null>(null)
const desktopLayoutContent = ref<HTMLElement | null>(null)
const chatResizableContent = ref<HTMLElement | null>(null)
const profileAvatarInput = ref<HTMLInputElement | null>(null)
const profileNameInput = ref<HTMLInputElement | null>(null)
const isEditingDisplayName = ref(false)
const displayNameDraft = ref('')
const isResizingLeftPanel = ref(false)
const isResizingRightPanel = ref(false)
const isStageOnRight = ref(false)
const isPanelSwapDragging = ref(false)
type PanelSwapSource = 'stage' | 'conversation'
const panelSwapDragSource = ref<PanelSwapSource | null>(null)
const panelSwapDragOffsetX = ref(0)
const MAIN_AREA_MIN_WIDTH = 720
const LEFT_PANEL_MIN_WIDTH = 220
const LEFT_PANEL_MAX_WIDTH = 380
const RIGHT_PANEL_MIN_WIDTH = 280
const RIGHT_PANEL_MAX_WIDTH = 520
const RESIZE_LAYOUT_ALLOWANCE = 32
const PANEL_SWAP_TRIGGER_DISTANCE = 88
const PANEL_SWAP_MAX_OFFSET = 128
const leftPanelWidth = ref(280)
const rightPanelWidth = ref(320)
let resizeStartX = 0
let resizeStartWidth = 0
let panelSwapStartX = 0
let panelSwapPointerTarget: HTMLElement | null = null
let panelSwapPointerId: number | null = null
const isImmersiveCall = computed(() => props.isRealtimeChatOn)
const isWebrtcConnected = computed(() => props.sessionStatus === 'connected')
const isWebrtcConnecting = computed(() => props.sessionStatus === 'connecting')
const isVoiceRuntimeOpen = computed(() => isWebrtcConnected.value && props.voiceChannelOpen)
const webrtcControlLabel = computed(() => {
  if (isWebrtcConnecting.value) return '连接中'
  if (isVoiceRuntimeOpen.value) return '语音通道开'
  return '语音通道关'
})
const webrtcControlIcon = computed(() => {
  if (isWebrtcConnecting.value) return 'i-carbon-circle-dash'
  if (isVoiceRuntimeOpen.value) return 'i-carbon-data-connected'
  return 'i-carbon-data-disconnected'
})

watch(activeSessionId, (sessionId, previousSessionId) => {
  if (!sessionId || sessionId === previousSessionId) return
  selectedSessionKey.value = sessionId
})

watch(() => props.userDisplayName, (displayName) => {
  if (!isEditingDisplayName.value) {
    displayNameDraft.value = displayName
  }
}, { immediate: true })

watch(() => props.isUserLoggedIn, (isLoggedIn) => {
  if (isLoggedIn) return
  isEditingDisplayName.value = false
  displayNameDraft.value = props.userDisplayName
})

useEscapeKey(() => {
  if (openSessionActionMenuId.value) {
    openSessionActionMenuId.value = null
    return
  }

  if (personalInfoOpen.value) {
    personalInfoOpen.value = false
    return
  }

  if (props.privateSpaceOpen) {
    emit('update:privateSpaceOpen', false)
  }
}, {
  enabled: () => !!openSessionActionMenuId.value || personalInfoOpen.value || props.privateSpaceOpen,
  priority: 58,
})

const hasTaskState = computed(() => {
  const status = props.taskProgress?.status
  return !!props.taskProgress?.tasks.length
    || ['running', 'success', 'failed', 'partial_success'].includes(status ?? '')
})
const hasAssistantMessage = computed(() => props.conversationRounds.some(
  round => round.assistantMessages.some(message => message.hasContent),
))
const shouldShowNarrationBubble = computed(() => {
  return !hasTaskState.value
    && !hasAssistantMessage.value
    && props.conversationRounds.length === 0
    && !props.streamingMessage?.text
})
const narrationBubbleText = computed(() => shouldShowNarrationBubble.value ? '今天想和我聊些什么呢？' : '')
const holdToTalkLabel = computed(() => {
  if (props.isSpeechTranscribing) return '正在识别...'
  if (props.isSpeechRecording) return '松开发送'
  return '按住说话'
})
const selectedSession = computed(() => {
  return props.displayedSessions.find(item => item.sessionId === selectedSessionKey.value)
    ?? props.displayedSessions.find(item => item.active)
    ?? props.displayedSessions[0]
    ?? null
})
const selectedSessionIsCurrent = computed(() => {
  if (selectedSession.value?.active) return true
  return !selectedSession.value && props.conversationRounds.length > 0
})
const selectedSessionSummary = computed(() => {
  const item = selectedSession.value
  if (!item) return '还没有选中的对话。'
  if (item.active) {
    return props.conversationRounds.length > 0
      ? '这是正在进行的对话，Aini 会把新的回复同步整理在这里。'
      : '这段对话刚刚开始，发送消息后会在这里沉淀成完整记录。'
  }
  return item.preview
    ? `围绕「${item.title}」的对话，Aini 已经整理出重点内容：${item.preview}`
    : `这是一段关于「${item.title}」的历史对话，可以从这里快速回看重点。`
})
const selectedSessionMockMessages = computed(() => {
  const item = selectedSession.value
  if (!item) return []
  return [
    { role: 'user', text: item.preview || item.title, time: item.time },
    { role: 'assistant', text: selectedSessionSummary.value, time: item.time },
  ]
})
const rightPanelWidthPx = computed(() => `${rightPanelWidth.value}px`)
const leftPanelWidthPx = computed(() => `${leftPanelWidth.value}px`)
const isConversationFocus = computed(() => isStageCollapsed.value && !isImmersiveCall.value)
const isStageFocus = computed(() => isRightCollapsed.value && !isImmersiveCall.value)
const desktopQuickActionLimit = computed(() => isConversationFocus.value ? 4 : 2)
const stagePanelStyle = computed(() => ({ order: isStageOnRight.value ? 3 : 1 }))
const rightPanelOrderStyle = computed(() => ({ order: isStageOnRight.value ? 1 : 3 }))
const dividerPanelStyle = { order: 2 }
const PANEL_SWAP_BLOCKED_SELECTOR = [
  'button',
  'a',
  'input',
  'textarea',
  'select',
  '[role="button"]',
  '[contenteditable="true"]',
  '.chat-top-controls',
  '.chat-control-pill',
  '.chat-panel-icon-button',
  '.chat-panel-reopen-button',
  '.chat-resize-divider',
  '.chat-right-weather-line',
  '.chat-right-compose-dock',
  '.chat-right-narration-bubble',
  '.chat-thread-round',
  '.chat-history-message-card',
  '.conversation-continue-button',
  '.user-detail-reply-shell',
  '.assistant-chat-reply-shell',
  '.assistant-task-reply-shell',
  '.chat-pending-indicator',
].join(',')

watch(isImmersiveCall, (enabled) => {
  if (!enabled) return
  isStageCollapsed.value = false
})

watch(isConversationFocus, (collapsed) => {
  emit('updateStagePanelCollapsed', collapsed)
}, { immediate: true })

function collapseStagePanel() {
  isStageCollapsed.value = true
  isRightCollapsed.value = false
}

function expandStagePanel() {
  isStageCollapsed.value = false
}

function collapseRightPanel() {
  isRightCollapsed.value = true
  isStageCollapsed.value = false
}

function expandRightPanel() {
  isRightCollapsed.value = false
}

function clampLeftPanelWidth(width: number): number {
  const contentWidth = desktopLayoutContent.value?.getBoundingClientRect().width
  const rightPanelReserved = !isRightCollapsed.value && !isStageCollapsed.value && !isImmersiveCall.value
    ? rightPanelWidth.value + RESIZE_LAYOUT_ALLOWANCE
    : 0
  const mainAreaReserved = isStageCollapsed.value ? RIGHT_PANEL_MIN_WIDTH : MAIN_AREA_MIN_WIDTH
  const maxWidthByMain = contentWidth
    ? contentWidth - mainAreaReserved - rightPanelReserved - RESIZE_LAYOUT_ALLOWANCE
    : LEFT_PANEL_MAX_WIDTH
  const upperBound = Math.max(
    LEFT_PANEL_MIN_WIDTH,
    Math.min(LEFT_PANEL_MAX_WIDTH, maxWidthByMain),
  )
  return Math.min(Math.max(width, LEFT_PANEL_MIN_WIDTH), upperBound)
}

function clampRightPanelWidth(width: number): number {
  const contentWidth = chatResizableContent.value?.getBoundingClientRect().width
  const maxWidthByMain = contentWidth
    ? contentWidth - MAIN_AREA_MIN_WIDTH - RESIZE_LAYOUT_ALLOWANCE
    : RIGHT_PANEL_MAX_WIDTH
  const upperBound = Math.max(
    RIGHT_PANEL_MIN_WIDTH,
    Math.min(RIGHT_PANEL_MAX_WIDTH, maxWidthByMain),
  )
  return Math.min(Math.max(width, RIGHT_PANEL_MIN_WIDTH), upperBound)
}

function applyResizeCursor() {
  document.body.classList.add('chat-resizing-panel')
}

function clearResizeCursor() {
  document.body.classList.remove('chat-resizing-panel')
}

function applyPanelSwapCursor() {
  document.body.classList.add('chat-swapping-panels')
}

function clearPanelSwapCursor() {
  document.body.classList.remove('chat-swapping-panels')
}

function panelSwapSurfaceStyle(source: PanelSwapSource) {
  if (!isPanelSwapDragging.value || panelSwapDragSource.value !== source) {
    return undefined
  }
  return { transform: `translateX(${panelSwapDragOffsetX.value}px)` }
}

function clampPanelSwapOffset(offset: number): number {
  return Math.min(Math.max(offset, -PANEL_SWAP_MAX_OFFSET), PANEL_SWAP_MAX_OFFSET)
}

function canStartPanelSwapDrag(event: PointerEvent): boolean {
  if (event.pointerType === 'mouse' && event.button !== 0) return false
  if (isRightCollapsed.value || isStageCollapsed.value || isImmersiveCall.value) return false
  if (event.target instanceof Element && event.target.closest(PANEL_SWAP_BLOCKED_SELECTOR)) {
    return false
  }
  return true
}

function startPanelSwapDrag(event: PointerEvent, source: PanelSwapSource) {
  if (!canStartPanelSwapDrag(event)) return

  event.preventDefault()
  event.stopPropagation()
  panelSwapStartX = event.clientX
  panelSwapDragOffsetX.value = 0
  panelSwapDragSource.value = source
  isPanelSwapDragging.value = true
  panelSwapPointerTarget = event.currentTarget instanceof HTMLElement ? event.currentTarget : null
  panelSwapPointerId = event.pointerId
  panelSwapPointerTarget?.setPointerCapture?.(event.pointerId)
  applyPanelSwapCursor()
  window.addEventListener('pointermove', handlePanelSwapDragMove)
  window.addEventListener('pointerup', stopPanelSwapDrag)
  window.addEventListener('pointercancel', cancelPanelSwapDrag)
}

function handlePanelSwapDragMove(event: PointerEvent) {
  const source = panelSwapDragSource.value
  if (!isPanelSwapDragging.value || !source) return

  const offset = event.clientX - panelSwapStartX
  panelSwapDragOffsetX.value = clampPanelSwapOffset(offset)
  if (Math.abs(offset) < PANEL_SWAP_TRIGGER_DISTANCE) return

  const nextStageOnRight = source === 'stage' ? offset > 0 : offset < 0
  if (nextStageOnRight !== isStageOnRight.value) {
    isStageOnRight.value = nextStageOnRight
    panelSwapStartX = event.clientX
    panelSwapDragOffsetX.value = 0
  }
}

function cleanupPanelSwapDrag() {
  if (!isPanelSwapDragging.value) return
  if (panelSwapPointerTarget && panelSwapPointerId !== null && panelSwapPointerTarget.hasPointerCapture?.(panelSwapPointerId)) {
    panelSwapPointerTarget.releasePointerCapture(panelSwapPointerId)
  }
  isPanelSwapDragging.value = false
  panelSwapDragSource.value = null
  panelSwapDragOffsetX.value = 0
  panelSwapPointerTarget = null
  panelSwapPointerId = null
  clearPanelSwapCursor()
  window.removeEventListener('pointermove', handlePanelSwapDragMove)
  window.removeEventListener('pointerup', stopPanelSwapDrag)
  window.removeEventListener('pointercancel', cancelPanelSwapDrag)
}

function stopPanelSwapDrag() {
  cleanupPanelSwapDrag()
}

function cancelPanelSwapDrag() {
  cleanupPanelSwapDrag()
}

function handleLeftPanelResizeMove(event: MouseEvent) {
  if (!isResizingLeftPanel.value) return
  const nextWidth = resizeStartWidth + event.clientX - resizeStartX
  leftPanelWidth.value = clampLeftPanelWidth(nextWidth)
}

function stopLeftPanelResize() {
  if (!isResizingLeftPanel.value) return
  isResizingLeftPanel.value = false
  clearResizeCursor()
  window.removeEventListener('mousemove', handleLeftPanelResizeMove)
  window.removeEventListener('mouseup', stopLeftPanelResize)
}

function startLeftPanelResize(event: MouseEvent) {
  event.preventDefault()
  resizeStartX = event.clientX
  resizeStartWidth = leftPanelWidth.value
  isResizingLeftPanel.value = true
  applyResizeCursor()
  window.addEventListener('mousemove', handleLeftPanelResizeMove)
  window.addEventListener('mouseup', stopLeftPanelResize)
}

function handleLeftPanelResizeKeydown(event: KeyboardEvent) {
  if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
  event.preventDefault()
  const step = event.shiftKey ? 40 : 16
  const direction = event.key === 'ArrowRight' ? 1 : -1
  leftPanelWidth.value = clampLeftPanelWidth(leftPanelWidth.value + direction * step)
}

function handleRightPanelResizeMove(event: MouseEvent) {
  if (!isResizingRightPanel.value) return
  const widthDelta = isStageOnRight.value
    ? event.clientX - resizeStartX
    : resizeStartX - event.clientX
  const nextWidth = resizeStartWidth + widthDelta
  rightPanelWidth.value = clampRightPanelWidth(nextWidth)
}

function stopRightPanelResize() {
  if (!isResizingRightPanel.value) return
  isResizingRightPanel.value = false
  clearResizeCursor()
  window.removeEventListener('mousemove', handleRightPanelResizeMove)
  window.removeEventListener('mouseup', stopRightPanelResize)
}

function startRightPanelResize(event: MouseEvent) {
  event.preventDefault()
  resizeStartX = event.clientX
  resizeStartWidth = rightPanelWidth.value
  isResizingRightPanel.value = true
  applyResizeCursor()
  window.addEventListener('mousemove', handleRightPanelResizeMove)
  window.addEventListener('mouseup', stopRightPanelResize)
}

function handleRightPanelResizeKeydown(event: KeyboardEvent) {
  if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
  event.preventDefault()
  const step = event.shiftKey ? 40 : 16
  const direction = event.key === 'ArrowLeft' ? 1 : -1
  rightPanelWidth.value = clampRightPanelWidth(rightPanelWidth.value + direction * step)
}

function handleRealtimeToggle() {
  emit('toggleRealtimeChat')
}

function openPrivateSpace() {
  if (!props.isUserLoggedIn) return
  emit('update:privateSpaceOpen', true)
}

function createNewConversation() {
  if (!props.isUserLoggedIn) return
  emit('newConversation')
}

function openSkillCenter() {
  if (!props.isUserLoggedIn) return
  emit('openSkillCenter')
}

function selectSession(item: SessionItem) {
  if (!props.isUserLoggedIn) return
  openSessionActionMenuId.value = null
  selectedSessionKey.value = item.sessionId
  expandRightPanel()
  if (!item.active) {
    emit('continueSession', {
      sessionId: item.sessionId,
      title: item.title,
      preview: item.preview,
    })
  }
}

function continueSelectedSession() {
  if (!props.isUserLoggedIn) return
  const item = selectedSession.value
  if (!item) return
  emit('continueSession', {
    sessionId: item.sessionId,
    title: item.title,
    preview: item.preview,
  })
}

function deleteSession(item: SessionItem) {
  if (!props.isUserLoggedIn) return
  emit('deleteSession', {
    sessionId: item.sessionId,
    title: item.title,
  })
}

function renameSession(item: SessionItem) {
  if (!props.isUserLoggedIn) return
  emit('renameSession', {
    sessionId: item.sessionId,
    title: item.title,
  })
}

function toggleSessionActionMenu(item: SessionItem) {
  if (!props.isUserLoggedIn) return
  openSessionActionMenuId.value = openSessionActionMenuId.value === item.sessionId ? null : item.sessionId
}

function openProfileAvatarUpload() {
  if (!props.isUserLoggedIn) {
    emit('openLogin')
    return
  }
  profileAvatarInput.value?.click()
}

function openUserFooterAction() {
  if (!props.isUserLoggedIn) {
    emit('openLogin')
    return
  }
  personalInfoOpen.value = true
}

function handleProfileAvatarChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  const reader = new FileReader()
  reader.onload = () => {
    if (typeof reader.result === 'string') {
      emit('updateUserAvatar', reader.result)
    }
    input.value = ''
  }
  reader.onerror = () => {
    input.value = ''
  }
  reader.readAsDataURL(file)
}

function beginDisplayNameEdit() {
  if (!props.isUserLoggedIn) {
    emit('openLogin')
    return
  }
  displayNameDraft.value = props.userDisplayName
  isEditingDisplayName.value = true
  void nextTick(() => profileNameInput.value?.focus())
}

function cancelDisplayNameEdit() {
  displayNameDraft.value = props.userDisplayName
  isEditingDisplayName.value = false
}

function submitDisplayNameEdit() {
  const nextName = displayNameDraft.value.trim()
  if (!nextName) {
    cancelDisplayNameEdit()
    return
  }
  emit('updateUserDisplayName', nextName)
  isEditingDisplayName.value = false
}

function renameSessionFromMenu(item: SessionItem) {
  openSessionActionMenuId.value = null
  renameSession(item)
}

function deleteSessionFromMenu(item: SessionItem) {
  openSessionActionMenuId.value = null
  deleteSession(item)
}

function pendingLabel(kind?: ChatMessage['pending']): string {
  return kind === 'task_creation' ? '正在创建任务' : '正在准备'
}

function shouldShowAssistantProcess(message: ConversationAssistantMessage): boolean {
  return Boolean(message.pending || (message.streaming && props.assistantProcessText.trim()))
}

function shouldShowAssistantBody(message: ConversationAssistantMessage): boolean {
  return !message.pending && message.hasContent
}

function isTaskReplyMessage(message: ConversationAssistantMessage): boolean {
  return isTaskReplyPresentation({
    text: message.text,
    source: message.source,
    pending: message.pending,
    artifact: message.artifact,
  })
}

function assistantReplyShellClass(message: ConversationAssistantMessage): string {
  return isTaskReplyMessage(message)
    ? 'assistant-task-reply-shell'
    : 'assistant-chat-reply-shell'
}

onBeforeUnmount(() => {
  stopLeftPanelResize()
  stopRightPanelResize()
  stopPanelSwapDrag()
})
</script>

<template>
  <div class="chat-desktop-shell h-screen overflow-hidden text-[#4a4a6a]">
    <div class="chat-desktop-frame h-full w-full overflow-hidden">
      <div
        ref="desktopLayoutContent"
        class="flex h-full min-h-0 gap-3 overflow-hidden"
        :class="{ 'is-resizing-left-panel': isResizingLeftPanel }"
      >
        <aside
          v-if="!isImmersiveCall"
          class="chat-side-panel relative flex min-h-0 shrink-0 flex-col overflow-hidden rounded-[28px] border border-white/65 bg-[#fbfaff]/78 shadow-[0_12px_36px_rgba(110,94,160,0.12)] backdrop-blur-xl transition-all duration-300 ease-out"
          :class="isLeftCollapsed ? 'w-[60px]' : 'min-w-[220px] max-w-[380px]'"
          :style="isLeftCollapsed ? undefined : { width: leftPanelWidthPx }"
        >
          <template v-if="isLeftCollapsed">
            <div class="flex h-full flex-col items-center gap-3 px-2 py-4">
              <button
                class="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-[#ded8f5] bg-white/70 text-[#6f67a5] shadow-sm transition hover:bg-[#f1ecff] active:scale-95"
                aria-label="展开左侧栏"
                title="展开左侧栏"
                @click="isLeftCollapsed = false"
              >
                <span class="i-carbon-chevron-right text-xl"></span>
              </button>
              <img :src="botAvatarUrl" :alt="`${botDisplayName} avatar`" class="h-10 w-10 rounded-full shadow-sm">
              <button
                class="inline-flex h-10 w-10 items-center justify-center rounded-2xl bg-white/70 text-[#b59ce8] shadow-sm transition hover:bg-[#f7f1ff] active:scale-95"
                :class="{ 'cursor-not-allowed opacity-45 hover:bg-white/70 active:scale-100': !isUserLoggedIn }"
                aria-label="打开私人空间"
                :title="isUserLoggedIn ? '私人空间' : '登录后可使用私人空间'"
                :disabled="!isUserLoggedIn"
                @click="openPrivateSpace"
              >
                <span class="i-carbon-flower-2 text-xl"></span>
              </button>
              <button
                class="inline-flex h-10 w-10 items-center justify-center rounded-2xl bg-[#efeaff] text-[#7b6ed0] shadow-sm transition hover:brightness-105 active:scale-95"
                :class="{ 'cursor-not-allowed opacity-45 hover:brightness-100 active:scale-100': !isUserLoggedIn }"
                aria-label="新建对话"
                :title="isUserLoggedIn ? '新建对话' : '登录后可新建对话'"
                :disabled="!isUserLoggedIn"
                @click="createNewConversation"
              >
                <span class="i-carbon-add text-xl"></span>
              </button>
              <button
                class="inline-flex h-10 w-10 items-center justify-center rounded-2xl bg-white/70 text-[#8b89b0]"
                :class="{ 'cursor-not-allowed opacity-45': !isUserLoggedIn }"
                :disabled="!isUserLoggedIn"
                :title="isUserLoggedIn ? '对话列表' : '登录后显示对话列表'"
              >
                <span class="i-carbon-chat text-xl"></span>
              </button>
              <RouterLink
                to="/"
                class="mt-auto inline-flex h-10 w-10 items-center justify-center rounded-2xl border border-[#ded8f5] bg-white/70 text-[#7b61d9] shadow-sm transition hover:bg-[#f1ecff] active:scale-95"
                aria-label="返回首页"
                title="返回首页"
              >
                <span class="i-carbon-home text-xl"></span>
              </RouterLink>
            </div>
          </template>

          <template v-else>
            <div class="flex items-center justify-between px-5 py-4 border-b border-[#e8e5f0]">
              <div class="flex min-w-0 flex-1 items-center gap-3">
                <img :src="botAvatarUrl" :alt="`${botDisplayName} avatar`" class="h-10 w-10 rounded-full shadow-sm">
                <button
                  type="button"
                  class="chat-private-space-link"
                  :class="{ 'cursor-not-allowed opacity-50': !isUserLoggedIn }"
                  aria-label="打开私人空间"
                  :title="isUserLoggedIn ? '私人空间' : '登录后可使用私人空间'"
                  :disabled="!isUserLoggedIn"
                  @click="openPrivateSpace"
                >
                  <span class="i-carbon-flower-2 shrink-0 text-base"></span>
                  <span class="truncate">私人空间</span>
                </button>
              </div>
              <button
                class="ml-3 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-[#ded8f5] bg-white/70 text-[#6f67a5] shadow-sm transition hover:bg-[#f1ecff] active:scale-95"
                aria-label="折叠左侧栏"
                title="折叠左侧栏"
                @click="isLeftCollapsed = true"
              >
                <span class="i-carbon-chevron-left text-xl"></span>
              </button>
            </div>

            <div class="px-4 py-3">
              <button
                type="button"
                class="w-full h-12 rounded-xl border border-[#d8cdf6] bg-gradient-to-r from-[#f7f2ff] to-[#e9e0ff] text-[#5f4e9f] font-semibold shadow-sm hover:brightness-105 active:scale-[0.99] transition-all"
                :class="{ 'cursor-not-allowed opacity-50 hover:brightness-100 active:scale-100': !isUserLoggedIn }"
                :disabled="!isUserLoggedIn"
                :title="isUserLoggedIn ? '新建对话' : '登录后可新建对话'"
                @click="createNewConversation"
              >
                {{ isUserLoggedIn ? '+ 新建对话' : '登录后可新建对话' }}
              </button>
            </div>

            <div class="flex-1 min-h-0 overflow-y-auto px-4 pb-4">
              <div>
                <p class="px-2 py-2 text-xs font-medium text-[#9997b5]">对话列表</p>
                <div v-if="!isUserLoggedIn" class="rounded-2xl border border-[#ebe8f6] bg-white/58 px-4 py-5 text-center shadow-sm">
                  <span class="i-carbon-locked mx-auto block text-2xl text-[#b9a9df]"></span>
                  <p class="mt-2 text-sm font-medium text-[#6c638f]">登录后保存对话</p>
                  <p class="mt-1 text-xs leading-5 text-[#9b91b7]">访客刷新会重置当前聊天，左侧记录暂时冻结。</p>
                </div>
                <div class="space-y-2">
                  <div
                    v-for="item in displayedSessions"
                    :key="item.sessionId"
                    role="button"
                    tabindex="0"
                    class="group relative rounded-xl p-3 cursor-pointer transition-all border bg-white/75 outline-none"
                    :class="(selectedSession?.sessionId === item.sessionId)
                      ? 'border-[#c5c3e8] bg-white shadow-[0_8px_22px_rgba(140,120,200,0.16)]'
                      : 'border-[#ebe8f6] hover:bg-white'"
                    @click="selectSession(item)"
                    @keydown.enter.prevent="selectSession(item)"
                    @keydown.space.prevent="selectSession(item)"
                  >
                    <div class="flex items-start gap-2">
                      <div class="flex-1 min-w-0">
                        <span class="block truncate text-sm font-medium text-[#4a4a6a]" :title="item.displayTitle || item.title">{{ item.displayTitle || item.title }}</span>
                        <p v-if="item.preview" class="mt-1 text-xs text-[#9997b5] truncate">{{ item.preview }}</p>
                      </div>
                      <div class="session-card-meta">
                        <span class="session-card-time">{{ item.time }}</span>
                        <div
                          class="session-action-menu-wrap"
                          @keydown.enter.stop
                          @keydown.space.stop
                        >
                          <button
                            type="button"
                            class="session-more-button"
                            :class="{ 'is-open': openSessionActionMenuId === item.sessionId }"
                            aria-label="更多对话操作"
                            title="更多操作"
                            :aria-expanded="openSessionActionMenuId === item.sessionId"
                            @click.stop="toggleSessionActionMenu(item)"
                          >
                            <span class="i-carbon-overflow-menu-horizontal text-base"></span>
                          </button>
                          <Transition name="session-action-menu">
                            <div
                              v-if="openSessionActionMenuId === item.sessionId"
                              class="session-action-menu"
                              @click.stop
                            >
                              <button type="button" class="session-action-menu-item" @click.stop="renameSessionFromMenu(item)">
                                <span class="i-carbon-edit text-sm"></span>
                                <span>重命名</span>
                              </button>
                              <button type="button" class="session-action-menu-item session-action-menu-item--danger" @click.stop="deleteSessionFromMenu(item)">
                                <span class="i-carbon-trash-can text-sm"></span>
                                <span>删除</span>
                              </button>
                            </div>
                          </Transition>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
                <button
                  v-if="isUserLoggedIn && hasMoreSessions"
                  class="mt-3 w-full rounded-xl border border-[#b7aae8] bg-gradient-to-r from-[#efe9ff] to-[#ddd3ff] py-2 text-sm font-medium text-[#6e5ec4] hover:brightness-105 transition"
                  @click="emit('update:showAllDialog', true)"
                >
                  查看全部对话
                </button>
              </div>
            </div>

            <div
              class="mx-4 mb-4 min-h-[148px] overflow-hidden rounded-2xl bg-cover bg-center px-5 py-5 shadow-[0_10px_28px_rgba(132,112,190,0.16)]"
              style="background-image: linear-gradient(90deg, rgba(255,255,255,0.72), rgba(255,255,255,0.30)), url('/explore_skills_pastel_bg.png');"
            >
              <div class="flex h-full items-center">
                <div class="flex-1 pr-4">
                  <p class="text-[17px] leading-[1.35] font-semibold text-[#575076]">Aini 技能中心</p>
                  <p class="mt-3 max-w-[165px] text-[13px] leading-[1.65] text-[#756f99]">为 Aini 学习新的能力，让陪伴持续成长</p>
                  <button
                    type="button"
                    class="mt-4 inline-flex h-8 items-center rounded-full border border-[#d8cdf6] bg-white/72 px-4 text-xs font-semibold text-[#5f4e9f] shadow-sm transition-colors hover:bg-[#f1ecff]"
                    :class="{ 'cursor-not-allowed opacity-55 hover:bg-white/72': !isUserLoggedIn }"
                    :disabled="!isUserLoggedIn"
                    :title="isUserLoggedIn ? '技能中心' : '登录后可使用技能中心'"
                    @click="openSkillCenter"
                  >
                    {{ isUserLoggedIn ? '去学习新技能' : '登录后开启' }}
                  </button>
                </div>
              </div>
            </div>

            <div class="border-t border-[#e8e5f0]">
              <RouterLink
                to="/"
                class="flex w-full items-center gap-3 px-5 py-3 text-[#766f98] transition-colors hover:bg-white/55"
                aria-label="返回首页"
                title="返回首页"
              >
                <span class="i-carbon-home text-lg text-[#7b61d9]"></span>
                <span class="text-sm">返回首页</span>
                <span class="i-carbon-chevron-right ml-auto text-[#b8b1d2]"></span>
              </RouterLink>
              <div class="flex items-center gap-3 px-5 py-3 border-t border-[#e8e5f0]">
                <img :src="userAvatarUrl" :alt="`${userDisplayName} avatar`" class="h-10 w-10 rounded-full border border-white/70 bg-white/70 shadow-sm">
                <div class="user-footer-info min-w-0 flex-1">
                  <button
                    type="button"
                    class="user-profile-link"
                    :aria-label="isUserLoggedIn ? '查看个人信息' : '去登入'"
                    :title="isUserLoggedIn ? '个人信息' : '去登入'"
                    @click="openUserFooterAction"
                  >
                    <span class="truncate">{{ isUserLoggedIn ? '个人信息' : '去登入' }}</span>
                    <span class="i-carbon-chevron-right shrink-0 text-sm"></span>
                  </button>
                  <div v-if="isUserLoggedIn" class="user-subscription-line">
                    <span class="h-2 w-2 rounded-full bg-green-400"></span>
                    <span class="truncate">订阅等级: {{ userSubscriptionLabel }}</span>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </aside>

        <div
          v-if="!isLeftCollapsed && !isImmersiveCall"
          class="chat-resize-divider chat-resize-divider--left"
          :class="{ 'is-active': isResizingLeftPanel }"
          role="separator"
          aria-label="调整对话列表宽度"
          aria-orientation="vertical"
          :aria-valuemin="LEFT_PANEL_MIN_WIDTH"
          :aria-valuemax="LEFT_PANEL_MAX_WIDTH"
          :aria-valuenow="leftPanelWidth"
          tabindex="0"
          @mousedown="startLeftPanelResize"
          @keydown="handleLeftPanelResizeKeydown"
        ></div>

        <div
          ref="chatResizableContent"
          class="chat-resizable-content flex h-full min-w-0 flex-1 gap-3 overflow-hidden"
          :class="{
            'is-resizing-right-panel': isResizingRightPanel,
            'is-panels-swapping': isPanelSwapDragging,
            'is-stage-on-right': isStageOnRight,
            'is-conversation-focus': isConversationFocus,
            'is-stage-focus': isStageFocus,
          }"
        >
        <Transition name="stage-panel">
        <main
          v-if="!isConversationFocus"
          data-emotion-boundary="interaction-stage"
          class="chat-stage relative min-h-0 min-w-[720px] flex-1 overflow-hidden rounded-[32px] border border-white/60 bg-transparent shadow-[0_18px_54px_rgba(94,80,142,0.14)] transition-all duration-300 ease-out"
          :class="{ 'chat-stage--focus': isStageFocus }"
          :style="[stagePanelStyle, panelSwapSurfaceStyle('stage')]"
          @pointerdown="event => startPanelSwapDrag(event, 'stage')"
        >
          <img :src="stageBackgroundUrl" class="absolute inset-0 h-full w-full object-cover">

          <div class="chat-top-controls absolute top-0 left-0 right-0 z-10 flex items-center justify-between px-8 py-4 bg-transparent">
            <div class="flex items-center gap-2 rounded-full bg-white/55 px-3 py-2 shadow-sm backdrop-blur-md border border-white/60" :title="connectionIndicator.label">
              <span class="w-2.5 h-2.5 rounded-full" :class="[connectionIndicator.color, connectionIndicator.pulse ? 'animate-pulse' : '']"></span>
              <span class="text-sm text-[#5a5880]">{{ connectionIndicator.label }}</span>
              <button
                v-if="canReconnect"
                type="button"
                class="ml-1 inline-flex h-7 items-center gap-1 rounded-full border border-[#d8cdf6] bg-white/72 px-2.5 text-xs font-semibold text-[#5f4e9f] shadow-sm transition hover:bg-[#f1ecff]"
                title="重新连接当前会话"
                @click.stop="emit('reconnect')"
              >
                <span class="i-carbon-renew"></span>
                <span>重连</span>
              </button>
            </div>

            <div class="chat-control-pill absolute left-1/2 -translate-x-1/2 flex items-center h-10 rounded-full border border-white/60 bg-white/55 px-2 shadow-sm backdrop-blur-md">
              <button
                class="flex items-center gap-2 rounded-full px-3 py-1.5 text-sm transition-colors hover:bg-white/60"
                :class="isVoiceRuntimeOpen ? 'bg-[#eee8ff]/72 text-[#5a4c9d]' : 'text-[#8f89b4]'"
                :aria-pressed="isVoiceRuntimeOpen"
                title="开启或关闭语音输入输出，保留文字聊天运行时"
                @click="emit('toggleWebrtcConnection')"
              >
                <span :class="[webrtcControlIcon, isWebrtcConnecting ? 'animate-spin' : '']"></span>
                <span>{{ webrtcControlLabel }}</span>
              </button>

              <span class="mx-1 h-5 w-px bg-white/70"></span>

              <button
                class="flex items-center gap-2 px-3 py-1.5 rounded-full text-sm transition-colors hover:bg-white/60"
                :class="voiceEnabled ? 'text-[#4f4c75]' : 'text-[#a7a3c3]'"
                @click="emit('toggleVoice')"
              >
                <span :class="voiceEnabled ? 'i-carbon-volume-up' : 'i-carbon-volume-mute'"></span>
                <span>{{ voiceEnabled ? '声音已开' : '声音关闭' }}</span>
              </button>

              <button
                class="flex items-center gap-2 px-3 py-1.5 rounded-full text-sm transition-colors hover:bg-white/60"
                :class="vadInterruptEnabled ? 'text-[#4f4c75]' : 'text-[#a7a3c3]'"
                @click="emit('toggleVadInterrupt')"
              >
                <span :class="vadInterruptEnabled ? 'i-carbon-microphone' : 'i-carbon-microphone-off'"></span>
                <span>{{ vadInterruptEnabled ? '智能打断' : '禁止打断' }}</span>
              </button>

              <span class="mx-1 h-5 w-px bg-white/70"></span>

              <button
                class="flex items-center gap-2 px-3 py-1.5 rounded-full text-sm transition-colors hover:bg-white/60"
                :class="isRealtimeChatOn ? 'text-[#4f4c75]' : 'text-[#7f7aa8]'"
                @click="handleRealtimeToggle"
              >
                <span :class="isRealtimeChatOn ? 'i-carbon-phone-voice-filled' : 'i-carbon-phone-voice'"></span>
                <span>{{ isRealtimeChatOn ? '陪伴中' : '语音陪伴' }}</span>
                <span class="text-xs">{{ isRealtimeChatOn ? '开启' : '关闭' }}</span>
                <span
                  class="relative inline-flex h-5 w-9 items-center rounded-full transition-colors"
                  :class="isRealtimeChatOn ? 'bg-[#8b7fd4]' : 'bg-[#d9d6ea]'"
                >
                  <span
                    class="inline-block h-4 w-4 rounded-full bg-white transition-transform"
                    :class="isRealtimeChatOn ? 'translate-x-4' : 'translate-x-0.5'"
                  ></span>
                </span>
              </button>
            </div>

          </div>

          <Transition name="panel-pill">
            <button
              v-if="isRightCollapsed && !isImmersiveCall"
              type="button"
              class="chat-panel-reopen-button absolute right-8 top-4 z-20"
              aria-label="展开对话内容"
              title="展开对话内容"
              @click="expandRightPanel"
            >
              <span class="chat-panel-toggle-logo" aria-hidden="true"></span>
              <span>对话内容</span>
            </button>
          </Transition>

          <Transition name="panel-pill">
            <button
              v-if="!isRightCollapsed && !isImmersiveCall"
              type="button"
              class="chat-panel-icon-button chat-stage-collapse-button absolute right-8 top-4 z-20"
              aria-label="折叠互动空间"
              title="折叠互动空间"
              @click="collapseStagePanel"
            >
              <span class="chat-panel-toggle-logo" aria-hidden="true"></span>
            </button>
          </Transition>

          <div class="absolute inset-0 pt-16 -translate-y-[10px]">
            <component
              :is="avatarCanvas"
              :model-url="modelUrl"
              :emotion-state="emotionState"
              :connection-status="sessionStatus"
              :streaming-message="streamingMessage"
              :disabled="vrmDisabled"
              :model-scale="1.35"
            />
          </div>
        </main>
        </Transition>

        <div
          v-if="!isRightCollapsed && !isConversationFocus && !isImmersiveCall"
          class="chat-resize-divider"
          :class="{ 'is-active': isResizingRightPanel }"
          :style="dividerPanelStyle"
          role="separator"
          aria-label="调整对话面板宽度"
          aria-orientation="vertical"
          :aria-valuemin="RIGHT_PANEL_MIN_WIDTH"
          :aria-valuemax="RIGHT_PANEL_MAX_WIDTH"
          :aria-valuenow="rightPanelWidth"
          tabindex="0"
          @mousedown="startRightPanelResize"
          @keydown="handleRightPanelResizeKeydown"
        ></div>

        <Transition name="right-panel">
          <aside
            v-if="!isRightCollapsed && !isImmersiveCall"
            class="chat-right-panel relative flex min-h-0 flex-col overflow-hidden rounded-[30px] border border-white/65 bg-[#fbfaff]/78 shadow-[0_12px_36px_rgba(110,94,160,0.12)] backdrop-blur-xl transition-all duration-300 ease-out"
            :class="isConversationFocus ? 'chat-right-panel--focus min-w-0 max-w-none flex-1' : 'min-w-[280px] max-w-[520px] shrink-0'"
            :style="[rightPanelOrderStyle, isConversationFocus ? undefined : { width: rightPanelWidthPx }, panelSwapSurfaceStyle('conversation')]"
            @pointerdown="event => startPanelSwapDrag(event, 'conversation')"
          >
          <div class="chat-right-panel__header px-5 py-4 border-b border-[#e8e5f0]">
            <div class="flex items-center justify-between gap-3">
              <div class="chat-right-heading min-w-0">
                <h3 class="truncate text-lg font-semibold text-[#4a4a6a]" :title="selectedSession?.title || '对话内容'">
                  {{ selectedSession?.displayTitle || selectedSession?.title || '对话内容' }}
                </h3>
                <div class="chat-right-weather-line">
                  <span :class="[weather.icon, 'chat-right-weather-line__icon']"></span>
                  <span>{{ weather.city }} {{ weather.temp }}</span>
                  <span class="h-1 w-1 rounded-full bg-[#d8cfe9]"></span>
                  <span>{{ weather.condition }}</span>
                </div>
              </div>
              <div class="flex shrink-0 items-center gap-2">
                <button
                  v-if="isConversationFocus"
                  class="chat-panel-reopen-button"
                  aria-label="展开互动空间"
                  title="展开互动空间"
                  @click="expandStagePanel"
                >
                  <span class="chat-panel-toggle-logo" aria-hidden="true"></span>
                  <span>互动空间</span>
                </button>
                <button
                  class="chat-panel-icon-button"
                  aria-label="折叠对话内容"
                  title="折叠对话内容"
                  @click="collapseRightPanel"
                >
                  <span class="chat-panel-toggle-logo" aria-hidden="true"></span>
                </button>
              </div>
            </div>
          </div>

          <div
            :ref="setMessagesContainer"
            class="chat-right-thread flex-1 min-h-0 overflow-y-auto px-5 py-4 space-y-5"
            :class="{ 'chat-right-thread--focus': isConversationFocus }"
            v-memo="[conversationRounds, assistantProcessText, selectedSession?.sessionId, selectedSession?.title, selectedSession?.preview, selectedSession?.time, selectedSession?.active, selectedSessionIsCurrent, botAvatarUrl, botDisplayName, userAvatarUrl, userDisplayName, isUserLoggedIn]"
          >
            <div v-if="shouldShowNarrationBubble" class="chat-right-narration-bubble">
              <img :src="botAvatarUrl" :alt="botDisplayName" class="h-9 w-9 rounded-full border border-white/80 shadow-sm">
              <div class="min-w-0 flex-1">
                <p class="text-sm font-semibold text-[#5b5480]">{{ botDisplayName }}</p>
                <p class="mt-1 text-sm leading-6 text-[#6d668f]">{{ narrationBubbleText }}</p>
              </div>
            </div>

            <template v-if="selectedSessionIsCurrent && conversationRounds.length > 0">
              <div v-for="round in conversationRounds" :key="round.id" class="chat-thread-round space-y-3">
                <div class="user-detail-reply-shell">
                  <div class="user-reply-header flex items-center justify-end gap-2">
                    <img :src="userAvatarUrl" alt="用户" class="h-8 w-8 rounded-full">
                    <span class="text-sm font-medium text-[#5a5880]">{{ isUserLoggedIn ? userDisplayName : '用户' }}</span>
                    <span class="text-xs text-[#b5b3c8]">{{ round.time }}</span>
                  </div>
                  <p class="user-detail-reply-text">{{ round.userMsg }}</p>
                </div>
                <template v-for="assistant in round.assistantMessages" :key="assistant.id">
                  <div v-if="assistant.hasContent || shouldShowAssistantProcess(assistant)" :class="assistantReplyShellClass(assistant)">
                    <div class="assistant-reply-header flex items-center gap-2 mb-2">
                      <img :src="botAvatarUrl" :alt="botDisplayName" class="h-8 w-8 rounded-full">
                      <span class="text-sm font-medium text-[#5a5880]">{{ botDisplayName }}</span>
                      <span class="text-xs text-[#b5b3c8]">{{ assistant.time }}</span>
                    </div>
                    <AgentProcessPreview
                      v-if="shouldShowAssistantProcess(assistant)"
                      :text="assistantProcessText"
                      :fallback-label="pendingLabel(assistant.pending)"
                    />
                    <BotReplyContent
                      v-if="shouldShowAssistantBody(assistant)"
                      :text="assistant.text"
                      :content-blocks="assistant.contentBlocks"
                      :source="assistant.source"
                      :artifact="assistant.artifact"
                      :render-markdown="renderMarkdown"
                    />
                  </div>
                </template>
              </div>
            </template>
            <template v-else-if="selectedSession && !selectedSessionIsCurrent">
              <section class="space-y-3">
                <p class="px-1 text-xs font-medium text-[#aaa1c7]">最近片段</p>
                <div
                  v-for="message in selectedSessionMockMessages"
                  :key="`${message.role}-${message.text}`"
                  class="chat-history-message-card rounded-[20px] border bg-white/62 p-4"
                  :class="message.role === 'user' ? 'border-[#dfe5f8]' : 'border-[#efe7f7]'"
                >
                  <div class="mb-2 flex items-center gap-2">
                    <img
                      :src="message.role === 'user' ? userAvatarUrl : botAvatarUrl"
                      :alt="message.role === 'user' ? '用户' : botDisplayName"
                      class="h-8 w-8 rounded-full"
                    >
                    <span class="text-sm font-medium text-[#5a5880]">{{ message.role === 'user' ? '你' : botDisplayName }}</span>
                    <span class="ml-auto text-xs text-[#b5b3c8]">{{ message.time }}</span>
                  </div>
                  <p class="text-sm leading-6 text-[#625b84]">{{ message.text }}</p>
                </div>
              </section>
              <button
                class="conversation-continue-button group"
                @click="continueSelectedSession"
              >
                <span class="conversation-continue-shine"></span>
                <span class="relative z-[1]">继续这段对话</span>
                <span class="i-carbon-arrow-right relative z-[1] text-base opacity-90 transition group-hover:translate-x-0.5"></span>
              </button>
            </template>
            <div v-else class="flex flex-col items-center justify-center h-full text-center">
              <span class="i-carbon-chat text-4xl text-[#d0cde0] mb-3"></span>
              <p class="text-sm text-[#9997b5]">等待开始对话...</p>
              <p class="text-xs text-[#b5b3c8] mt-1">发送消息后对话内容会显示在这里</p>
            </div>
          </div>

          <div
            v-show="!isRealtimeChatOn"
            class="chat-right-compose-dock"
            :class="{ 'chat-right-compose-dock--focus': isConversationFocus }"
          >
            <div class="chat-right-compose-inner">
              <QuickActionBubbles
                class="mb-3"
                :actions="quickActions"
                :disabled="quickActionsDisabled"
                :visible-limit="desktopQuickActionLimit"
                variant="desktop"
                @select="action => emit('quickAction', action)"
              />
              <div class="mb-3">
                <TaskProgressCard :data="taskProgress" @retry="item => emit('retryTask', item)" />
              </div>

              <div class="chat-composer chat-composer--right rounded-[28px] border border-white/70 bg-white/80 p-2 shadow-lg backdrop-blur-md">
                <p v-if="sendError" class="mb-2 px-4 text-sm text-red-500">
                  {{ sendError }}
                </p>
                <div class="flex items-center gap-3 rounded-[24px] border border-[#e0ddf5] bg-white px-2 py-1">
                  <button
                    class="h-11 w-11 shrink-0 rounded-full flex items-center justify-center transition-colors"
                    :class="inputMode === 'ptt' ? 'bg-[#8b7fd4] text-white' : 'bg-[#e8e5f5] text-[#8b89b0] hover:bg-[#ddd8f0]'"
                    :disabled="isSpeechRecording || isSpeechTranscribing"
                    @click="emit('toggleInputMode')"
                  >
                    <span :class="inputMode === 'ptt' ? 'i-carbon-keyboard text-xl' : 'i-carbon-microphone text-xl'"></span>
                  </button>

                  <template v-if="inputMode === 'text'">
                    <input
                      :value="inputText"
                      type="text"
                      :placeholder="inputPlaceholder"
                      class="min-w-0 flex-1 bg-transparent px-2 py-2 text-sm text-[#4a4a6a] placeholder:text-[#b5b3c8] outline-none"
                      @input="emit('update:inputText', ($event.target as HTMLInputElement).value)"
                      @keydown="emit('keydownEnter', $event as KeyboardEvent)"
                    >
                    <button
                      class="h-11 w-11 shrink-0 flex items-center justify-center text-white transition-all disabled:cursor-not-allowed disabled:opacity-40"
                      :class="isBotResponding ? 'rounded-full bg-[#8b7fd4] shadow-[0_8px_18px_rgba(139,127,212,0.24)] hover:bg-[#7a6ec8]' : 'rounded-full bg-[#8b7fd4] hover:bg-[#7a6ec8]'"
                      :disabled="isBotResponding ? false : !inputText.trim()"
                      :aria-label="isBotResponding ? '停止回复' : '发送消息'"
                      :title="isBotResponding ? '停止回复' : '发送消息'"
                      @click="isBotResponding ? emit('stopResponse') : emit('send')"
                    >
                      <span v-if="!isBotResponding" class="i-carbon-send text-lg"></span>
                      <span v-else class="h-3.5 w-3.5 rounded-[3px] bg-white shadow-[0_1px_4px_rgba(74,58,130,0.18)]" aria-hidden="true"></span>
                    </button>
                  </template>
                  <button
                    v-else
                    type="button"
                    class="min-w-0 flex-1 rounded-full px-4 py-2 text-sm transition-colors"
                    :class="isSpeechRecording ? 'bg-[#f0e8ff] text-[#7f5edc] shadow-inner' : 'bg-[#f3f1fb] text-[#6b6894] active:bg-[#e6e2f6]'"
                    :disabled="isSpeechTranscribing"
                    @mousedown="emit('startHoldToTalk')"
                    @mouseup="emit('endHoldToTalk')"
                    @mouseleave="emit('endHoldToTalk')"
                    @touchstart.prevent="emit('startHoldToTalk')"
                    @touchend.prevent="emit('endHoldToTalk')"
                    @touchcancel.prevent="emit('endHoldToTalk')"
                  >
                    <span class="inline-flex items-center gap-2">
                      <span
                        class="inline-block h-2 w-2 rounded-full"
                        :class="isSpeechRecording ? 'animate-pulse bg-[#f08bb8]' : 'bg-[#c9c3e6]'"
                      ></span>
                      {{ holdToTalkLabel }}
                    </span>
                  </button>
                </div>
              </div>
            </div>
          </div>
          </aside>
        </Transition>
        </div>
      </div>
    </div>
    <StatusDrawer v-model:open="statusPanelOpenProxy" />
  </div>

  <Teleport to="body">
    <Transition name="private-space">
      <aside
        v-if="privateSpaceOpen"
        class="chat-private-space-panel fixed left-4 top-4 z-50 h-[calc(100vh-32px)] w-[360px] overflow-hidden rounded-[28px] border border-white/65 bg-[#fff9ff]/72 text-[#4f4a72] shadow-[0_24px_80px_rgba(105,86,150,0.20)] backdrop-blur-2xl"
      >
        <div class="absolute inset-0 pointer-events-none bg-[radial-gradient(circle_at_18%_12%,rgba(255,220,238,0.85),transparent_32%),radial-gradient(circle_at_92%_0%,rgba(205,224,255,0.72),transparent_34%)]"></div>
        <div class="relative flex h-full flex-col">
          <header class="px-6 pb-4 pt-6">
            <div class="flex items-start justify-between gap-4">
              <div class="min-w-0">
                <p class="text-xs font-medium leading-5 text-[#9b91b7]">陪伴记忆</p>
                <h2 class="mt-1 text-lg font-semibold leading-7 text-[#4a4a6a]">私人空间</h2>
                <p class="mt-1.5 text-sm leading-6 text-[#7e779f]">这里保存你们慢慢形成的陪伴、记忆与房间氛围。</p>
              </div>
              <button
                type="button"
                class="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-white/70 bg-white/55 text-[#7b719f] shadow-sm transition hover:bg-white/80"
                aria-label="关闭私人空间"
                @click="emit('update:privateSpaceOpen', false)"
              >
                <span class="i-carbon-close text-xl"></span>
              </button>
            </div>
          </header>

          <div class="relative flex-1 overflow-y-auto px-5 pb-6">
            <section class="space-y-4">
              <div class="rounded-[22px] border border-white/60 bg-white/42 p-4">
                <div class="flex items-center gap-3">
                  <img :src="botAvatarUrl" :alt="botDisplayName" class="h-12 w-12 rounded-full border border-white/70 shadow-sm">
                  <div>
                    <p class="text-xs text-[#9e95bd]">我的角色</p>
                    <h3 class="text-base font-semibold text-[#514873]">{{ botDisplayName }}</h3>
                  </div>
                </div>
                <div class="mt-4 grid grid-cols-2 gap-2 text-sm text-[#716a92]">
                  <button class="rounded-full bg-white/45 px-3 py-2 text-left hover:bg-white/70"><span class="i-carbon-music mr-1 text-[#b796df]"></span>角色声音</button>
                  <button class="rounded-full bg-white/45 px-3 py-2 text-left hover:bg-white/70"><span class="i-carbon-person-favorite mr-1 text-[#b796df]"></span>角色服装</button>
                  <button class="rounded-full bg-white/45 px-3 py-2 text-left hover:bg-white/70"><span class="i-carbon-face-wink mr-1 text-[#b796df]"></span>角色人格</button>
                  <button class="rounded-full bg-white/45 px-3 py-2 text-left hover:bg-white/70"><span class="i-carbon-notebook-reference mr-1 text-[#b796df]"></span>角色设定</button>
                </div>
              </div>

              <div class="rounded-[22px] border border-white/60 bg-white/36 p-4">
                <p class="mb-3 text-sm font-semibold text-[#514873]">记忆中的你</p>
                <div class="space-y-2 text-sm text-[#716a92]">
                  <button class="flex w-full items-center gap-2 rounded-full bg-white/42 px-3 py-2 text-left hover:bg-white/70"><span class="i-carbon-bookmark-filled text-[#e3a0bf]"></span>长期偏好</button>
                  <button class="flex w-full items-center gap-2 rounded-full bg-white/42 px-3 py-2 text-left hover:bg-white/70"><span class="i-carbon-star text-[#d6a85f]"></span>兴趣</button>
                  <button class="flex w-full items-center gap-2 rounded-full bg-white/42 px-3 py-2 text-left hover:bg-white/70"><span class="i-carbon-events text-[#89a9d8]"></span>共同经历</button>
                  <button class="flex w-full items-center gap-2 rounded-full bg-white/42 px-3 py-2 text-left hover:bg-white/70"><span class="i-carbon-favorite text-[#c49ee2]"></span>长期关系</button>
                </div>
              </div>

              <div class="rounded-[22px] border border-white/60 bg-white/36 p-4">
                <p class="mb-3 text-sm font-semibold text-[#514873]">空间氛围</p>
                <div class="grid grid-cols-2 gap-2 text-sm text-[#716a92]">
                  <button class="rounded-full bg-white/42 px-3 py-2 text-left hover:bg-white/70"><span class="i-carbon-image mr-1 text-[#89a9d8]"></span>背景切换</button>
                  <button class="rounded-full bg-white/42 px-3 py-2 text-left hover:bg-white/70"><span class="i-carbon-partly-cloudy mr-1 text-[#d6a85f]"></span>天气联动</button>
                  <button class="rounded-full bg-white/42 px-3 py-2 text-left hover:bg-white/70"><span class="i-carbon-home mr-1 text-[#c49ee2]"></span>房间风格</button>
                  <button class="rounded-full bg-white/42 px-3 py-2 text-left hover:bg-white/70"><span class="i-carbon-moon mr-1 text-[#8ca2de]"></span>昼夜模式</button>
                </div>
              </div>

              <div class="rounded-[22px] border border-white/60 bg-white/32 p-4">
                <p class="mb-3 text-sm font-semibold text-[#514873]">对话管理</p>
                <div class="space-y-2 text-sm text-[#716a92]">
                  <button class="flex w-full items-center gap-2 rounded-full bg-white/42 px-3 py-2 text-left hover:bg-white/70" @click="emit('update:showAllDialog', true)"><span class="i-carbon-chat"></span>查看全部对话</button>
                  <button class="flex w-full items-center gap-2 rounded-full bg-white/42 px-3 py-2 text-left hover:bg-white/70"><span class="i-carbon-download"></span>导出聊天记录</button>
                  <button class="flex w-full items-center gap-2 rounded-full bg-white/42 px-3 py-2 text-left text-[#a86d83] hover:bg-white/70"><span class="i-carbon-trash-can"></span>清空历史记录</button>
                </div>
              </div>

            </section>
          </div>
        </div>
      </aside>
    </Transition>
  </Teleport>

  <Teleport to="body">
    <Transition name="profile-modal">
      <div
        v-if="personalInfoOpen"
        class="chat-profile-modal-layer fixed inset-0 z-50 flex items-center justify-center px-4 py-6"
        role="presentation"
        @click.self="personalInfoOpen = false"
      >
        <section
          class="chat-profile-modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="chat-profile-title"
        >
          <button
            type="button"
            class="chat-profile-modal__close"
            aria-label="关闭个人信息"
            @click="personalInfoOpen = false"
          >
            <span class="i-carbon-close text-xl"></span>
          </button>

          <div class="chat-profile-modal__header">
            <button
              type="button"
              class="chat-profile-avatar-button"
              aria-label="更换头像"
              @click="openProfileAvatarUpload"
            >
              <img :src="userAvatarUrl" :alt="`${userDisplayName} avatar`" class="chat-profile-modal__avatar">
              <span v-if="isUserLoggedIn" class="chat-profile-avatar-button__badge">
                <span class="i-carbon-camera"></span>
              </span>
            </button>
            <input
              ref="profileAvatarInput"
              class="hidden"
              type="file"
              accept="image/*"
              @change="handleProfileAvatarChange"
            >
            <div class="min-w-0">
              <p class="text-xs font-medium text-[#9b91b7]">个人信息</p>
              <h2 id="chat-profile-title" class="chat-profile-title">
                <span v-if="isEditingDisplayName" class="chat-profile-name-editor chat-profile-name-editor--title">
                  <input
                    ref="profileNameInput"
                    v-model="displayNameDraft"
                    type="text"
                    maxlength="24"
                    @keydown.enter.prevent="submitDisplayNameEdit"
                    @keydown.esc.prevent="cancelDisplayNameEdit"
                  >
                  <button type="button" aria-label="保存昵称" @click="submitDisplayNameEdit">
                    <span class="i-carbon-checkmark"></span>
                  </button>
                  <button type="button" aria-label="取消修改昵称" @click="cancelDisplayNameEdit">
                    <span class="i-carbon-close"></span>
                  </button>
                </span>
                <template v-else>
                  <span class="chat-profile-title-text">{{ userDisplayName }}</span>
                  <button
                    v-if="isUserLoggedIn"
                    type="button"
                    class="chat-profile-title-edit-button"
                    aria-label="修改昵称"
                    @click="beginDisplayNameEdit"
                  >
                    <span class="i-carbon-edit"></span>
                  </button>
                </template>
              </h2>
              <p class="mt-1 text-xs text-[#9b91b7]">{{ isUserLoggedIn ? '已登录 Soulmeet' : '还没有登录' }}</p>
            </div>
          </div>

          <div class="chat-profile-modal__body">
            <div class="chat-profile-info-row">
              <span class="i-carbon-user-avatar text-[#a986df]"></span>
              <span>昵称</span>
              <strong>{{ userDisplayName }}</strong>
            </div>
            <div class="chat-profile-info-row">
              <span class="i-carbon-user-identification text-[#8ca2de]"></span>
              <span>账号信息</span>
              <strong>{{ userAccountName }}</strong>
            </div>
            <div class="chat-profile-info-row">
              <span class="i-carbon-star text-[#d7a65f]"></span>
              <span>订阅等级</span>
              <strong>{{ userSubscriptionLabel }}</strong>
            </div>
            <div class="chat-profile-info-row">
              <span class="i-carbon-face-satisfied text-[#dd93bd]"></span>
              <span>当前陪伴</span>
              <strong>{{ botDisplayName }}</strong>
            </div>
          </div>

          <div v-if="isUserLoggedIn" class="chat-profile-quick-actions">
            <button type="button" class="chat-profile-account-button">
              <span class="i-carbon-devices"></span>
              <span>登录设备</span>
            </button>
            <button type="button" class="chat-profile-account-button">
              <span class="i-carbon-security"></span>
              <span>隐私管理</span>
            </button>
          </div>

          <section v-else class="chat-profile-account-section" aria-labelledby="chat-profile-account-title">
            <div class="chat-profile-section-heading">
              <span class="i-carbon-security text-[#a986df]"></span>
              <h3 id="chat-profile-account-title">账号与隐私</h3>
            </div>
            <div class="chat-profile-auth-panel">
              <p>登入后可以同步你的陪伴记忆</p>
              <div class="chat-profile-auth-inline">
                <button type="button" class="chat-auth-text-action" @click="emit('openLogin')">登入</button>
                <span>/</span>
                <button type="button" class="chat-auth-text-action" @click="emit('openRegister')">注册</button>
              </div>
            </div>
          </section>

          <div v-if="isUserLoggedIn" class="chat-profile-modal__actions">
            <button
              type="button"
              class="chat-profile-action-button"
              @click="personalInfoOpen = false; emit('openSubscription')"
            >
              <span class="i-carbon-star-filled"></span>
              <span>查看订阅</span>
            </button>
            <button
              type="button"
              class="chat-profile-text-button"
              @click="personalInfoOpen = false; emit('logout')"
            >
              退出登录
            </button>
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped lang="scss">
.chat-desktop-shell {
  position: relative;
  background:
    linear-gradient(rgba(255, 255, 255, 0.14) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.12) 1px, transparent 1px),
    radial-gradient(circle at 16% 8%, rgba(255, 215, 234, 0.78), transparent 30%),
    radial-gradient(circle at 82% 4%, rgba(221, 235, 255, 0.76), transparent 32%),
    radial-gradient(circle at 48% 102%, rgba(232, 218, 255, 0.74), transparent 32%),
    linear-gradient(135deg, #f8f3ff 0%, #fff7fb 48%, #f3f6ff 100%);
  background-size: 48px 48px, 48px 48px, auto, auto, auto, auto;
  font-family: var(--soulmeet-font-family);

  &::before,
  &::after {
    content: "";
    position: absolute;
    border-radius: 999px;
    pointer-events: none;
  }

  &::before {
    width: 360px;
    height: 360px;
    left: 240px;
    top: 60px;
    background: radial-gradient(circle, rgba(255, 215, 234, 0.48), transparent 68%);
  }

  &::after {
    width: 420px;
    height: 420px;
    right: 170px;
    bottom: -80px;
    background: radial-gradient(circle, rgba(213, 197, 255, 0.42), transparent 70%);
  }
}

.chat-private-space-panel {
  font-family: var(--soulmeet-font-family);
}

.user-footer-info {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 0.18rem;
}

.user-profile-link {
  appearance: none;
  display: inline-flex;
  max-width: 100%;
  width: fit-content;
  align-items: center;
  gap: 0.22rem;
  border: 0;
  background: transparent;
  padding: 0;
  color: #5f5782;
  font: inherit;
  font-size: 0.9rem;
  font-weight: 700;
  line-height: 1.35;
  text-align: left;
  transition: color 0.18s ease, transform 0.18s ease;
}

.user-profile-link:hover,
.user-profile-link:focus-visible {
  color: #7d62df;
  outline: none;
  transform: translateX(1px);
}

.user-subscription-line {
  display: inline-flex;
  max-width: 100%;
  align-items: center;
  gap: 0.38rem;
  color: #9997b5;
  font-size: 0.75rem;
  line-height: 1.3;
}

.chat-profile-modal-layer {
  background: rgba(61, 50, 88, 0.18);
  font-family: var(--soulmeet-font-family);
  backdrop-filter: blur(12px);
}

.chat-profile-modal {
  position: relative;
  width: min(390px, 100%);
  max-height: calc(100vh - 2rem);
  overflow-y: auto;
  border-radius: 28px;
  border: 1px solid rgba(255, 255, 255, 0.72);
  background:
    radial-gradient(circle at 12% 0%, rgba(255, 220, 238, 0.82), transparent 34%),
    radial-gradient(circle at 92% 8%, rgba(218, 229, 255, 0.78), transparent 34%),
    rgba(255, 250, 255, 0.82);
  padding: 1.25rem;
  color: #514b78;
  box-shadow: 0 28px 74px rgba(105, 86, 150, 0.24), inset 0 1px 0 rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(24px);
  scrollbar-width: thin;
}

.chat-profile-modal__close {
  position: absolute;
  top: 0.9rem;
  right: 0.9rem;
  display: inline-flex;
  width: 2.35rem;
  height: 2.35rem;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(255, 255, 255, 0.72);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.58);
  color: #7b719f;
  box-shadow: 0 8px 18px rgba(105, 86, 150, 0.12);
  transition: background 0.18s ease, transform 0.18s ease;
}

.chat-profile-modal__close:hover,
.chat-profile-modal__close:focus-visible {
  background: rgba(255, 255, 255, 0.82);
  outline: none;
  transform: scale(1.03);
}

.chat-profile-modal__header {
  display: flex;
  align-items: center;
  gap: 0.85rem;
  padding-right: 2.8rem;
}

.chat-profile-modal__avatar {
  width: 3.25rem;
  height: 3.25rem;
  flex: 0 0 auto;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.78);
  background: rgba(255, 255, 255, 0.72);
  box-shadow: 0 12px 24px rgba(115, 92, 165, 0.14);
}

.chat-profile-avatar-button {
  position: relative;
  display: inline-flex;
  flex: 0 0 auto;
  border: 0;
  border-radius: 999px;
  background: transparent;
  padding: 0;
  cursor: pointer;
}

.chat-profile-avatar-button:focus-visible {
  outline: none;
}

.chat-profile-avatar-button:focus-visible .chat-profile-modal__avatar,
.chat-profile-avatar-button:hover .chat-profile-modal__avatar {
  box-shadow: 0 14px 28px rgba(115, 92, 165, 0.2), 0 0 0 4px rgba(218, 198, 255, 0.28);
}

.chat-profile-avatar-button__badge {
  position: absolute;
  right: -0.15rem;
  bottom: -0.1rem;
  display: inline-flex;
  width: 1.45rem;
  height: 1.45rem;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(255, 255, 255, 0.78);
  border-radius: 999px;
  background: linear-gradient(135deg, #8b7ae6, #c59dff 58%, #ffbddd);
  color: #fff;
  font-size: 0.8rem;
  box-shadow: 0 8px 16px rgba(139, 122, 230, 0.2);
}

.chat-profile-title {
  display: flex;
  margin: 0.25rem 0 0;
  max-width: 100%;
  min-width: 0;
  align-items: center;
  gap: 0.35rem;
  color: #4a4a6a;
  font-size: 1.1rem;
  font-weight: 700;
  line-height: 1.35;
}

.chat-profile-title-text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-profile-title-edit-button {
  display: inline-flex;
  width: 1.55rem;
  height: 1.55rem;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(255, 255, 255, 0.62);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.44);
  color: #8d7abe;
  font-size: 0.82rem;
  box-shadow: 0 6px 14px rgba(105, 86, 150, 0.08);
  transition: background 0.18s ease, color 0.18s ease, transform 0.18s ease;
}

.chat-profile-title-edit-button:hover,
.chat-profile-title-edit-button:focus-visible {
  background: rgba(255, 255, 255, 0.78);
  color: #7d62df;
  outline: none;
  transform: translateY(-1px);
}

.chat-profile-title .chat-profile-name-editor {
  flex: 1 1 auto;
}

.chat-profile-title .chat-profile-name-editor input {
  min-height: 1.9rem;
}

.chat-profile-modal__body {
  display: grid;
  gap: 0.55rem;
  margin-top: 1.15rem;
}

.chat-profile-info-row {
  display: grid;
  grid-template-columns: auto minmax(4.5rem, auto) minmax(0, 1fr);
  align-items: center;
  gap: 0.55rem;
  border: 1px solid rgba(255, 255, 255, 0.62);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.42);
  padding: 0.7rem 0.8rem;
  color: #7b739c;
  font-size: 0.84rem;
}

.chat-profile-info-row strong {
  min-width: 0;
  overflow: hidden;
  color: #504971;
  font-weight: 700;
  text-align: right;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-profile-name-editor {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 0.35rem;
  min-width: 0;
}

.chat-profile-name-editor input {
  width: 100%;
  min-width: 0;
  border: 1px solid rgba(197, 157, 255, 0.52);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.72);
  padding: 0.42rem 0.65rem;
  color: #504971;
  font-size: 0.82rem;
  font-weight: 700;
  outline: none;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.82);
}

.chat-profile-name-editor input:focus {
  border-color: rgba(166, 137, 238, 0.82);
  box-shadow: 0 0 0 3px rgba(218, 198, 255, 0.28), inset 0 1px 0 rgba(255, 255, 255, 0.9);
}

.chat-profile-name-editor button {
  display: inline-flex;
  width: 1.65rem;
  height: 1.65rem;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(255, 255, 255, 0.64);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.54);
  color: #7b719f;
  transition: background 0.18s ease, color 0.18s ease, transform 0.18s ease;
}

.chat-profile-name-editor button:hover,
.chat-profile-name-editor button:focus-visible {
  background: rgba(255, 255, 255, 0.82);
  color: #7d62df;
  outline: none;
  transform: translateY(-1px);
}

.chat-profile-quick-actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.55rem;
  margin-top: 0.85rem;
}

.chat-profile-account-section {
  margin-top: 0.8rem;
  border: 1px solid rgba(255, 255, 255, 0.62);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.36);
  padding: 0.9rem;
}

.chat-profile-section-heading {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  color: #514873;
}

.chat-profile-section-heading h3 {
  margin: 0;
  font-size: 0.88rem;
  font-weight: 700;
  line-height: 1.35;
}

.chat-profile-account-actions {
  display: grid;
  gap: 0.5rem;
  margin-top: 0.7rem;
}

.chat-profile-account-button {
  display: flex;
  width: 100%;
  min-height: 2.35rem;
  align-items: center;
  gap: 0.48rem;
  border: 1px solid rgba(255, 255, 255, 0.54);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.46);
  padding: 0.55rem 0.72rem;
  color: #716a92;
  font-size: 0.84rem;
  font-weight: 600;
  text-align: left;
  transition: background 0.18s ease, color 0.18s ease, transform 0.18s ease;
}

.chat-profile-account-button:hover,
.chat-profile-account-button:focus-visible {
  background: rgba(255, 255, 255, 0.76);
  color: #62558d;
  outline: none;
  transform: translateY(-1px);
}

.chat-profile-auth-panel {
  margin-top: 0.65rem;
  color: #716a92;
  font-size: 0.84rem;
  line-height: 1.6;
}

.chat-profile-auth-panel p {
  margin: 0 0 0.25rem;
  color: #8d84aa;
  font-size: 0.78rem;
}

.chat-profile-auth-inline {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
}

.chat-profile-auth-inline span {
  color: #c8c1dd;
}

.chat-profile-modal__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-top: 1.15rem;
}

.chat-profile-action-button {
  display: inline-flex;
  min-height: 2.45rem;
  flex: 1;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  border: 1px solid rgba(255, 255, 255, 0.76);
  border-radius: 999px;
  background: linear-gradient(135deg, #8b7ae6, #c59dff 58%, #ffbddd);
  color: #fff;
  font-size: 0.86rem;
  font-weight: 700;
  box-shadow: 0 14px 30px rgba(139, 122, 230, 0.2);
  transition: transform 0.18s ease, filter 0.18s ease;
}

.chat-profile-action-button:hover,
.chat-profile-action-button:focus-visible {
  filter: brightness(1.03);
  outline: none;
  transform: translateY(-1px);
}

.chat-profile-text-button {
  border: 0;
  background: transparent;
  color: #7b719f;
  font-size: 0.84rem;
  font-weight: 700;
  transition: color 0.18s ease;
}

.chat-profile-text-button:hover,
.chat-profile-text-button:focus-visible {
  color: #7d62df;
  outline: none;
}

.chat-desktop-frame {
  position: relative;
  z-index: 1;
}

.chat-side-panel,
.chat-right-panel {
  --chat-conversation-track-width: 920px;
  background:
    radial-gradient(circle at 12% 0%, rgba(255, 215, 234, 0.42), transparent 34%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.78), rgba(255, 247, 253, 0.52));
  border-color: rgba(255, 255, 255, 0.78);
  box-shadow: 0 20px 50px rgba(139, 122, 230, 0.13), inset 0 1px 0 rgba(255, 255, 255, 0.76);
}

.chat-stage {
  border-radius: 38px;
  border-color: rgba(255, 255, 255, 0.72);
  box-shadow: 0 30px 78px rgba(94, 80, 142, 0.18), inset 0 1px 0 rgba(255, 255, 255, 0.54);

  &::before {
    content: "";
    position: absolute;
    inset: 0;
    z-index: 1;
    pointer-events: none;
    background:
      linear-gradient(180deg, rgba(255, 247, 253, 0.44), transparent 22%, transparent 68%, rgba(255, 247, 253, 0.5)),
      radial-gradient(circle at 22% 14%, rgba(255, 215, 234, 0.34), transparent 28%),
      radial-gradient(circle at 84% 18%, rgba(221, 235, 255, 0.32), transparent 30%);
  }

  &::after {
    content: "";
    position: absolute;
    inset: 14px;
    z-index: 2;
    border-radius: 30px;
    border: 1px solid rgba(255, 255, 255, 0.34);
    pointer-events: none;
  }
}

.chat-stage--focus {
  box-shadow:
    0 34px 86px rgba(94, 80, 142, 0.2),
    inset 0 1px 0 rgba(255, 255, 255, 0.58);
}

.chat-stage,
.chat-right-panel {
  cursor: grab;
  touch-action: pan-y;
}

.chat-right-compose-dock,
.chat-right-narration-bubble,
.chat-thread-round,
.chat-history-message-card,
.conversation-continue-button,
.user-detail-reply-shell,
.assistant-chat-reply-shell,
.assistant-task-reply-shell,
.chat-pending-indicator,
.chat-top-controls,
.chat-right-weather-line {
  cursor: auto;
}

.chat-thread-round {
  content-visibility: auto;
  contain-intrinsic-size: 280px;
}

.user-detail-reply-shell,
.assistant-chat-reply-shell,
.assistant-task-reply-shell {
  contain: layout paint;
}

.chat-panel-icon-button,
.chat-panel-reopen-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(255, 255, 255, 0.72);
  border-radius: 999px;
  background:
    radial-gradient(circle at 22% 18%, rgba(255, 255, 255, 0.92), transparent 38%),
    linear-gradient(135deg, rgba(255, 246, 252, 0.88), rgba(239, 232, 255, 0.82) 54%, rgba(224, 237, 255, 0.78)),
    rgba(255, 255, 255, 0.66);
  color: #7b61d9;
  box-shadow:
    0 14px 30px rgba(139, 122, 230, 0.16),
    0 4px 14px rgba(255, 185, 220, 0.12),
    inset 0 1px 0 rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(18px);
  transition: transform 0.18s ease, box-shadow 0.18s ease, filter 0.18s ease;
}

.chat-panel-icon-button:hover,
.chat-panel-reopen-button:hover,
.chat-panel-icon-button:focus-visible,
.chat-panel-reopen-button:focus-visible {
  filter: brightness(1.06);
  outline: none;
  transform: translateY(-1px);
  box-shadow:
    0 18px 36px rgba(139, 122, 230, 0.2),
    0 8px 22px rgba(255, 185, 220, 0.16),
    inset 0 1px 0 rgba(255, 255, 255, 0.9);
}

.chat-panel-icon-button:active,
.chat-panel-reopen-button:active {
  transform: translateY(0) scale(0.96);
}

.chat-panel-icon-button {
  width: 42px;
  height: 42px;
  padding: 0;
  cursor: pointer;
  touch-action: manipulation;
}

.chat-panel-reopen-button {
  min-height: 42px;
  gap: 0.6rem;
  padding: 0 1rem;
  font-size: 0.86rem;
  font-weight: 700;
  letter-spacing: 0;
  white-space: nowrap;
}

.chat-panel-toggle-logo {
  position: relative;
  display: inline-block;
  width: 22px;
  height: 22px;
  flex: 0 0 22px;
}

.chat-panel-toggle-logo::before,
.chat-panel-toggle-logo::after {
  content: "";
  position: absolute;
  border: 2.4px solid currentColor;
  border-radius: 4px;
  background: transparent;
  box-shadow: 0 1px 5px rgba(22, 22, 32, 0.12);
}

.chat-panel-toggle-logo::before {
  top: 1px;
  left: 0;
  width: 17px;
  height: 17px;
}

.chat-panel-toggle-logo::after {
  right: 0;
  bottom: 0;
  width: 11px;
  height: 11px;
}

.chat-resizable-content {
  min-width: 0;
}

.chat-resizable-content.is-panels-swapping .chat-stage,
.chat-resizable-content.is-panels-swapping .chat-right-panel {
  cursor: grabbing;
  box-shadow:
    0 28px 70px rgba(94, 80, 142, 0.2),
    inset 0 1px 0 rgba(255, 255, 255, 0.64);
}

.chat-resizable-content.is-conversation-focus {
  gap: 0;
}

.chat-right-panel--focus {
  border-radius: 36px;
  background:
    radial-gradient(circle at 8% 0%, rgba(255, 215, 234, 0.48), transparent 31%),
    radial-gradient(circle at 94% 6%, rgba(221, 235, 255, 0.48), transparent 29%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.82), rgba(255, 247, 253, 0.58));
  box-shadow:
    0 28px 72px rgba(139, 122, 230, 0.15),
    inset 0 1px 0 rgba(255, 255, 255, 0.82);
}

.chat-right-panel--focus .chat-right-panel__header {
  padding: 1.25rem clamp(1.5rem, 3vw, 3rem) 1rem;
}

.chat-right-heading {
  display: flex;
  align-items: center;
  gap: 0.9rem;
  flex: 1 1 auto;
  flex-wrap: wrap;
}

.chat-right-heading h3 {
  flex: 0 1 auto;
  min-width: 4.5rem;
}

.chat-right-thread--focus {
  padding: 1.35rem clamp(1.5rem, 4vw, 4.25rem) 2rem;
  scroll-padding-bottom: 2rem;
}

.chat-right-thread {
  padding-right: 1rem;
  padding-left: 1rem;
}

.chat-right-thread > .chat-right-narration-bubble,
.chat-right-thread > .chat-thread-round,
.chat-right-thread > section,
.chat-right-thread > .conversation-continue-button {
  width: min(100%, var(--chat-conversation-track-width));
  margin-right: auto;
  margin-left: auto;
}

.chat-right-narration-bubble {
  display: flex;
  width: 100%;
  max-width: var(--chat-conversation-track-width);
  align-items: flex-start;
  gap: 0.75rem;
  padding: 0.35rem 0 0.25rem;
}

.chat-right-thread--focus .chat-thread-round {
  max-width: var(--chat-conversation-track-width);
  margin-right: auto;
  margin-left: auto;
}

.chat-right-panel--focus .user-detail-reply-shell {
  max-width: min(72%, 720px);
  padding: 0.2rem 0.25rem;
}

.chat-right-panel--focus .assistant-chat-reply-shell {
  max-width: min(78%, 760px);
  padding: 0.2rem 0.25rem;
}

.chat-right-panel--focus .assistant-task-reply-shell {
  max-width: var(--chat-conversation-track-width, 920px);
}

.chat-right-panel--focus .chat-right-narration-bubble {
  max-width: var(--chat-conversation-track-width, 920px);
  margin-right: auto;
  margin-left: auto;
}

.chat-right-panel--focus .user-detail-reply-text,
.chat-right-panel--focus .assistant-chat-reply-shell {
  font-size: 0.93rem;
  line-height: 1.8;
}

.chat-right-compose-dock {
  flex: 0 0 auto;
  border-top: 0;
  background: transparent;
  padding: 0.8rem 1rem 1rem;
  box-shadow: none;
}

.chat-right-compose-inner {
  max-width: 100%;
}

.chat-right-compose-dock--focus {
  padding: 0.9rem clamp(1.5rem, 4vw, 4.25rem) 1.2rem;
}

.chat-right-compose-dock--focus .chat-right-compose-inner {
  max-width: var(--chat-conversation-track-width, 920px);
  margin-right: auto;
  margin-left: auto;
}

.chat-composer--right {
  width: 100%;
}

.chat-resize-divider {
  position: relative;
  z-index: 15;
  width: 8px;
  min-width: 8px;
  align-self: stretch;
  cursor: col-resize;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.62);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.72), rgba(232, 218, 255, 0.42)),
    rgba(218, 199, 255, 0.34);
  box-shadow:
    0 0 22px rgba(196, 158, 255, 0.18),
    inset 0 1px 0 rgba(255, 255, 255, 0.82),
    inset 0 -1px 0 rgba(192, 155, 236, 0.16);
  backdrop-filter: blur(16px);
  transition: background 160ms ease, box-shadow 160ms ease, border-color 160ms ease;
  touch-action: none;
}

.chat-resize-divider::before {
  content: "";
  position: absolute;
  inset: 18px 2px;
  border-radius: inherit;
  background: linear-gradient(180deg, rgba(198, 160, 244, 0.28), rgba(255, 185, 220, 0.32));
  opacity: 0.72;
}

.chat-resize-divider:hover,
.chat-resize-divider:focus-visible,
.chat-resize-divider.is-active {
  border-color: rgba(212, 178, 246, 0.72);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.78), rgba(226, 207, 255, 0.56)),
    rgba(207, 181, 255, 0.52);
  box-shadow:
    0 0 28px rgba(188, 140, 255, 0.28),
    0 8px 24px rgba(255, 176, 225, 0.16),
    inset 0 1px 0 rgba(255, 255, 255, 0.9);
  outline: none;
}

.is-resizing-left-panel .chat-side-panel,
.is-resizing-left-panel .chat-resizable-content,
.is-resizing-left-panel .chat-stage,
.is-resizing-left-panel .chat-right-panel,
.is-resizing-right-panel .chat-stage,
.is-resizing-right-panel .chat-right-panel {
  transition: none !important;
}

:global(body.chat-resizing-panel) {
  cursor: col-resize;
  user-select: none;
}

:global(body.chat-swapping-panels) {
  cursor: grabbing;
  user-select: none;
}

.conversation-continue-button {
  position: relative;
  display: inline-flex;
  min-height: 48px;
  width: fit-content;
  align-items: center;
  justify-content: center;
  gap: 0.45rem;
  overflow: hidden;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.72);
  background:
    linear-gradient(135deg, rgba(151, 120, 241, 0.96) 0%, rgba(198, 129, 240, 0.94) 52%, rgba(247, 176, 225, 0.96) 100%);
  padding: 0 1.55rem;
  color: #fff;
  font-size: 0.95rem;
  font-weight: 700;
  letter-spacing: 0;
  box-shadow:
    0 18px 34px rgba(167, 111, 226, 0.25),
    0 7px 18px rgba(255, 176, 225, 0.18),
    inset 0 1px 0 rgba(255, 255, 255, 0.72);
  text-shadow: 0 1px 8px rgba(80, 56, 130, 0.16);
  transition: transform 180ms ease, box-shadow 180ms ease, filter 180ms ease;
}

.conversation-continue-button:hover {
  transform: translateY(-1px);
  filter: saturate(1.04) brightness(1.02);
  box-shadow:
    0 22px 42px rgba(167, 111, 226, 0.3),
    0 10px 22px rgba(255, 176, 225, 0.22),
    inset 0 1px 0 rgba(255, 255, 255, 0.82);
}

.conversation-continue-button:active {
  transform: translateY(0) scale(0.98);
}

.conversation-continue-shine {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 24% 18%, rgba(255, 255, 255, 0.54), transparent 30%),
    linear-gradient(100deg, transparent 0%, rgba(255, 255, 255, 0.32) 44%, transparent 70%);
  opacity: 0.82;
  pointer-events: none;
}

.chat-top-controls {
  z-index: 12;
}

.chat-control-pill,
.chat-composer {
  border-color: rgba(255, 255, 255, 0.78);
  background: rgba(255, 255, 255, 0.62);
  box-shadow: 0 14px 34px rgba(139, 122, 230, 0.12), inset 0 1px 0 rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(18px);
}

.chat-right-weather-line {
  display: flex;
  width: fit-content;
  max-width: 100%;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.45rem;
  border: 1px solid rgba(255, 255, 255, 0.64);
  border-radius: 999px;
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.66), rgba(255, 247, 253, 0.48)),
    rgba(245, 240, 255, 0.46);
  box-shadow:
    0 8px 18px rgba(117, 96, 168, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.72);
  color: #746d96;
  font-size: 0.75rem;
  font-weight: 600;
  line-height: 1.2;
  padding: 0.42rem 0.62rem;
}

.chat-right-weather-line span {
  flex-shrink: 0;
}

.chat-right-weather-line__icon {
  color: #8f78df !important;
}

.chat-right-weather-line__icon.i-carbon-sun {
  color: #f59e0b !important;
}

.chat-right-weather-line__icon.i-carbon-rain,
.chat-right-weather-line__icon.i-carbon-rain-drizzle {
  color: #2563eb !important;
}

.chat-right-weather-line__icon.i-carbon-snow {
  color: #0891b2 !important;
}

.chat-right-weather-line__icon.i-carbon-fog {
  color: #6b7280 !important;
}

.chat-right-weather-line__icon.i-carbon-cloudy {
  color: #64748b !important;
}

.chat-right-weather-line__icon.i-carbon-partly-cloudy {
  color: #f59e0b !important;
}

.chat-right-weather-line span:last-child {
  min-width: 0;
}

.chat-composer {
  border-radius: 32px;
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.82), rgba(255, 247, 253, 0.66)),
    rgba(255, 255, 255, 0.74);
}

.chat-composer :deep(button[class*="bg-[#8b7fd4]"]),
.chat-control-pill :deep(button[class*="bg-[#8b7fd4]"]) {
  background: linear-gradient(135deg, #8b7ae6, #c59dff 58%, #ffbddd) !important;
  box-shadow: 0 12px 28px rgba(139, 122, 230, 0.24);
}

.chat-side-panel :deep(.border-b),
.chat-side-panel :deep(.border-t),
.chat-right-panel :deep(.border-b),
.chat-right-panel :deep(.border-t) {
  border-color: rgba(232, 225, 246, 0.72);
}

.chat-side-panel :deep(.rounded-xl),
.chat-right-panel :deep(.rounded-xl) {
  border-radius: 18px;
}

.chat-right-panel :deep(.prose) {
  color: #5d5782;
}

.chat-private-space-link {
  appearance: none;
  display: inline-flex;
  min-width: 0;
  align-items: center;
  gap: 0.35rem;
  border: 0;
  background: transparent;
  padding: 0.1rem 0;
  color: #706790;
  font: inherit;
  font-size: 0.95rem;
  font-weight: 600;
  line-height: 1.35;
  text-align: left;
  text-decoration: underline;
  text-decoration-color: transparent;
  text-underline-offset: 4px;
  transition: color 0.18s ease, text-decoration-color 0.18s ease;
}

.chat-private-space-link span:first-child {
  color: #b59ce8;
}

.chat-private-space-link:hover,
.chat-private-space-link:focus-visible {
  color: #7d62df;
  text-decoration-color: rgba(125, 98, 223, 0.34);
  outline: none;
}

.chat-auth-text-action {
  appearance: none;
  border: 0;
  background: transparent;
  padding: 0;
  color: #6f6594;
  font: inherit;
  font-weight: 600;
  line-height: 1.4;
  text-align: left;
  transition: color 0.18s ease, text-decoration-color 0.18s ease;
  text-decoration: underline;
  text-decoration-color: transparent;
  text-underline-offset: 3px;
}

.chat-auth-text-action:hover,
.chat-auth-text-action:focus-visible {
  color: #7d62df;
  text-decoration-color: rgba(125, 98, 223, 0.36);
  outline: none;
}

.user-detail-reply-shell,
.assistant-chat-reply-shell {
  max-width: 92%;
  border: 0;
  border-radius: 0;
  background: transparent;
  padding: 0.15rem 0.2rem;
  color: #514b78;
  box-shadow: none;
}

.user-detail-reply-shell {
  width: fit-content;
  margin-left: auto;
  text-align: right;
}

.user-detail-reply-shell .user-reply-header {
  margin-bottom: 0.45rem;
  padding: 0 0.15rem;
}

.user-detail-reply-shell .user-reply-header img {
  border: 1px solid rgba(255, 255, 255, 0.76);
  box-shadow: 0 4px 10px rgba(115, 92, 165, 0.08);
}

.user-detail-reply-text {
  margin: 0;
  font-family: var(--soulmeet-font-family);
  color: #5d5782;
  font-size: var(--soulmeet-chat-user-font-size);
  line-height: 1.76;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.assistant-task-reply-shell {
  padding: 0.15rem 0 0.35rem;
  color: #514b78;
}

.assistant-task-reply-shell .assistant-reply-header {
  margin-bottom: 0.45rem;
  padding: 0 0.15rem;
}

.assistant-task-reply-shell .assistant-reply-header img {
  border: 1px solid rgba(255, 255, 255, 0.76);
  box-shadow: 0 4px 10px rgba(115, 92, 165, 0.08);
}

.assistant-chat-reply-shell {
  width: min(100%, var(--chat-conversation-track-width));
}

.assistant-chat-reply-shell .assistant-reply-header {
  margin-bottom: 0.35rem;
}

.assistant-chat-reply-shell .assistant-reply-header img {
  border: 1px solid rgba(255, 255, 255, 0.74);
  box-shadow: 0 4px 10px rgba(115, 92, 165, 0.08);
}

.chat-pending-indicator {
  position: relative;
  display: inline-flex;
  max-width: 100%;
  align-items: center;
  gap: 0.5rem;
  overflow: hidden;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.76);
  background:
    linear-gradient(110deg, rgba(255, 255, 255, 0.78), rgba(246, 239, 255, 0.62), rgba(255, 244, 251, 0.72));
  padding: 0.5rem 0.75rem;
  color: #74659f;
  box-shadow: 0 10px 24px rgba(139, 122, 230, 0.12), inset 0 1px 0 rgba(255, 255, 255, 0.86);
}

.chat-pending-indicator::after {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(100deg, transparent 0%, rgba(255, 255, 255, 0.72) 44%, transparent 72%);
  transform: translateX(-120%);
  animation: pending-shimmer 1.8s ease-in-out infinite;
}

.chat-pending-indicator__spark {
  position: relative;
  z-index: 1;
  height: 0.55rem;
  width: 0.55rem;
  border-radius: 999px;
  background: #c9a7ff;
  box-shadow: 0 0 12px rgba(201, 167, 255, 0.74);
  animation: pending-pulse 1.25s ease-in-out infinite;
}

.chat-pending-indicator__label {
  position: relative;
  z-index: 1;
  font-size: 0.875rem;
  font-weight: 600;
}

.chat-pending-indicator__dots {
  position: relative;
  z-index: 1;
  display: inline-flex;
  gap: 0.22rem;
}

.chat-pending-indicator__dots span {
  height: 0.3rem;
  width: 0.3rem;
  border-radius: 999px;
  background: #b79af0;
  animation: pending-dot 1.1s ease-in-out infinite;
}

.chat-pending-indicator__dots span:nth-child(2) {
  animation-delay: 0.16s;
}

.chat-pending-indicator__dots span:nth-child(3) {
  animation-delay: 0.32s;
}

@keyframes pending-shimmer {
  0% {
    transform: translateX(-120%);
  }
  55%, 100% {
    transform: translateX(120%);
  }
}

@keyframes pending-pulse {
  0%, 100% {
    transform: scale(0.9);
    opacity: 0.62;
  }
  50% {
    transform: scale(1.18);
    opacity: 1;
  }
}

@keyframes pending-dot {
  0%, 80%, 100% {
    transform: translateY(0);
    opacity: 0.36;
  }
  40% {
    transform: translateY(-0.22rem);
    opacity: 1;
  }
}

::-webkit-scrollbar {
  width: 6px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: #d0cde0;
  border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
  background: #b5b3c8;
}

.prose {
  :deep(p) {
    margin: 0.5em 0;
  }

  :deep(ul), :deep(ol) {
    margin: 0.5em 0;
    padding-left: 1.5em;
  }

  :deep(code) {
    background: #f0eef5;
    padding: 0.125em 0.25em;
    border-radius: 0.25em;
    font-size: 0.875em;
  }
}

.session-card-meta {
  display: flex;
  min-width: 42px;
  flex: 0 0 auto;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.28rem;
}

.session-card-time {
  color: #b5b3c8;
  font-size: 0.75rem;
  line-height: 1.1rem;
  white-space: nowrap;
}

.session-action-menu-wrap {
  position: relative;
}

.session-more-button {
  display: inline-flex;
  width: 28px;
  height: 24px;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: #a59bc0;
  opacity: 0;
  transition: opacity 0.18s ease, color 0.18s ease, background 0.18s ease, transform 0.18s ease;
}

.group:hover .session-more-button,
.group:focus-within .session-more-button,
.session-more-button.is-open {
  opacity: 1;
}

.session-more-button:hover,
.session-more-button:focus-visible,
.session-more-button.is-open {
  background: rgba(245, 239, 255, 0.86);
  color: #7d62df;
  outline: none;
}

.session-action-menu {
  position: absolute;
  top: calc(100% + 0.35rem);
  right: 0;
  z-index: 24;
  width: 112px;
  overflow: hidden;
  border-radius: 14px;
  border: 1px solid rgba(232, 225, 246, 0.86);
  background: rgba(255, 253, 255, 0.94);
  padding: 0.35rem;
  box-shadow: 0 14px 30px rgba(105, 86, 150, 0.16);
  backdrop-filter: blur(16px);
}

.session-action-menu-item {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 0.4rem;
  border: 0;
  border-radius: 10px;
  background: transparent;
  padding: 0.45rem 0.55rem;
  color: #6f6594;
  font-size: 0.78rem;
  font-weight: 600;
  text-align: left;
  transition: background 0.16s ease, color 0.16s ease;
}

.session-action-menu-item:hover,
.session-action-menu-item:focus-visible {
  background: rgba(245, 239, 255, 0.92);
  color: #7d62df;
  outline: none;
}

.session-action-menu-item--danger {
  color: #b56d82;
}

.session-action-menu-item--danger:hover,
.session-action-menu-item--danger:focus-visible {
  background: rgba(255, 240, 246, 0.9);
  color: #d85d78;
}

.session-action-menu-enter-active,
.session-action-menu-leave-active {
  transition: opacity 0.16s ease, transform 0.16s ease;
}

.session-action-menu-enter-from,
.session-action-menu-leave-to {
  opacity: 0;
  transform: translateY(-4px) scale(0.98);
}

.private-space-enter-active,
.private-space-leave-active {
  transition: opacity 0.26s ease, transform 0.32s cubic-bezier(0.2, 0.8, 0.2, 1);
}

.private-space-enter-from,
.private-space-leave-to {
  opacity: 0;
  transform: translateX(-24px);
}

.profile-modal-enter-active,
.profile-modal-leave-active {
  transition: opacity 0.2s ease;
}

.profile-modal-enter-active .chat-profile-modal,
.profile-modal-leave-active .chat-profile-modal {
  transition: transform 0.24s cubic-bezier(0.2, 0.8, 0.2, 1), opacity 0.2s ease;
}

.profile-modal-enter-from,
.profile-modal-leave-to {
  opacity: 0;
}

.profile-modal-enter-from .chat-profile-modal,
.profile-modal-leave-to .chat-profile-modal {
  opacity: 0;
  transform: translateY(10px) scale(0.98);
}

.right-panel-enter-active,
.right-panel-leave-active {
  transition: opacity 0.24s ease, transform 0.3s ease, width 0.3s ease;
}

.right-panel-enter-from,
.right-panel-leave-to {
  width: 0;
  opacity: 0;
  transform: translateX(18px);
}

.stage-panel-enter-active,
.stage-panel-leave-active {
  transition: opacity 0.24s ease, transform 0.3s ease, flex-basis 0.3s ease;
}

.stage-panel-enter-from,
.stage-panel-leave-to {
  opacity: 0;
  transform: translateX(-18px) scale(0.985);
}

.panel-pill-enter-active,
.panel-pill-leave-active {
  transition: opacity 0.2s ease, transform 0.24s ease;
}

.panel-pill-enter-from,
.panel-pill-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

</style>
