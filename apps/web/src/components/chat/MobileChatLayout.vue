<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { Component, PropType } from 'vue'
import type { EmotionState } from '@soulmeet/shared'
import type { ChatMessage, TaskProgressItem, TaskProgressSnapshot } from '../../composables/useChat'
import AgentProcessPreview from './AgentProcessPreview.vue'
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
  recentConversationRounds: { type: Array as PropType<ConversationRound[]>, required: true },
  showAllDialog: { type: Boolean, required: true },
  sideDrawerOpen: { type: Boolean, required: true },
  privateSpaceOpen: { type: Boolean, required: true },
  keyboardInset: { type: Number, default: 0 },
  sessionStatus: { type: String, required: true },
  emotionState: { type: Object as PropType<EmotionState>, required: true },
  streamingMessage: { type: Object as PropType<ChatMessage | null>, default: null },
  assistantProcessText: { type: String, default: '' },
  renderMarkdown: { type: Function as PropType<(text: string) => string>, required: true },
  userAvatarUrl: { type: String, required: true },
  userDisplayName: { type: String, required: true },
  userSubscriptionLabel: { type: String, required: true },
  isUserLoggedIn: { type: Boolean, required: true },
  taskProgress: { type: Object as PropType<TaskProgressSnapshot | null>, default: null },
  canReconnect: { type: Boolean, default: false },
})

const emit = defineEmits<{
  (e: 'update:inputText', value: string): void
  (e: 'update:showAllDialog', value: boolean): void
  (e: 'update:sideDrawerOpen', value: boolean): void
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
  (e: 'retryTask', item: TaskProgressItem): void
}>()

const composerStyle = computed(() => ({
  bottom: `calc(env(safe-area-inset-bottom, 0px) + 14px + ${props.keyboardInset}px)`,
}))
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

const conversationDrawerOpen = ref(false)
const taskDetailsOpen = ref(false)
const selectedSessionKey = ref<string | null>(null)
const activeSessionId = computed(() => props.displayedSessions.find(item => item.active)?.sessionId ?? null)
const openSessionActionMenuId = ref<string | null>(null)
const visibleConversationRounds = computed(() => props.conversationRounds.slice(-4))
const hasConversation = computed(() => props.conversationRounds.length > 0 || !!props.streamingMessage?.text)
const holdToTalkLabel = computed(() => {
  if (props.isSpeechTranscribing) return '正在识别...'
  if (props.isSpeechRecording) return '松开发送'
  return '按住说话（松开发送）'
})

watch(activeSessionId, (sessionId, previousSessionId) => {
  if (!sessionId || sessionId === previousSessionId) return
  selectedSessionKey.value = sessionId
})

useEscapeKey(() => {
  if (openSessionActionMenuId.value) {
    openSessionActionMenuId.value = null
    return
  }

  if (taskDetailsOpen.value) {
    taskDetailsOpen.value = false
    return
  }

  if (conversationDrawerOpen.value) {
    conversationDrawerOpen.value = false
    return
  }

  if (props.privateSpaceOpen) {
    emit('update:privateSpaceOpen', false)
    return
  }

  if (props.sideDrawerOpen) {
    emit('update:sideDrawerOpen', false)
  }
}, {
  enabled: () => !!openSessionActionMenuId.value
    || taskDetailsOpen.value
    || conversationDrawerOpen.value
    || props.privateSpaceOpen
    || props.sideDrawerOpen,
  priority: 58,
})

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

const primaryTask = computed(() => props.taskProgress?.tasks[0] ?? null)
const taskStatus = computed(() => props.taskProgress?.status ?? primaryTask.value?.status ?? 'pending')
const taskKind = computed(() => primaryTask.value?.name || props.taskProgress?.title || '查询')
const taskResultCount = computed(() => {
  const summary = props.taskProgress?.summary || primaryTask.value?.description || ''
  const matched = summary.match(/(\d+)\s*(?:趟|个|条|家)/)
  return matched?.[1] || ''
})

const mobileTaskCopy = computed(() => {
  if (!props.taskProgress || !props.taskProgress.tasks.length) return null
  if (taskStatus.value === 'success') {
    return {
      tone: 'success',
      icon: 'i-carbon-checkmark-filled',
      title: `Aini 已完成${taskKind.value}`,
      detail: taskResultCount.value ? `已为你找到 ${taskResultCount.value} 条结果` : (props.taskProgress.summary || primaryTask.value?.description || '结果已整理好'),
    }
  }
  if (taskStatus.value === 'failed') {
    return {
      tone: 'failed',
      icon: 'i-carbon-warning-alt-filled',
      title: 'Aini 暂时没查到结果',
      detail: primaryTask.value?.errorReason || props.taskProgress.summary || '原因：服务响应超时，请稍后重试',
    }
  }
  if (taskStatus.value === 'partial_success') {
    return {
      tone: 'partial',
      icon: 'i-carbon-incomplete',
      title: 'Aini 已部分完成',
      detail: props.taskProgress.summary || primaryTask.value?.description || '部分结果已经返回',
    }
  }
  return {
    tone: 'running',
    icon: 'i-carbon-progress-bar',
    title: primaryTask.value?.actionLabel ? `Aini 正在${primaryTask.value.actionLabel}` : 'Aini 正在帮你处理...',
    detail: primaryTask.value?.actionLog || primaryTask.value?.description || '正在连接服务',
  }
})

const taskEntryLabel = computed(() => {
  if (taskStatus.value === 'success') return '任务已完成'
  if (taskStatus.value === 'failed') return '任务失败'
  if (taskStatus.value === 'partial_success') return '部分完成'
  return primaryTask.value?.actionLabel || '任务进行中'
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
      ? '这是正在进行的对话，新的内容会同步出现在这里。'
      : '这段对话刚刚开始，发送消息后会形成完整记录。'
  }
  return item.preview
    ? `这段对话围绕「${item.title}」展开，Aini 已经把重点整理好了：${item.preview}`
    : `这是一段关于「${item.title}」的历史对话。`
})
const selectedSessionTags = computed(() => {
  const title = selectedSession.value?.title ?? ''
  if (/(车票|出行|高铁|火车|动车|规划)/.test(title)) return ['出行', '车票', '可继续']
  if (/(天气|穿衣|气温)/.test(title)) return ['天气', '提醒', '生活']
  if (/(酒店|景点|旅行|游)/.test(title)) return ['旅行', '推荐', '收藏']
  return ['陪伴', '记录', '继续聊']
})

function createNewConversation() {
  if (!props.isUserLoggedIn) return
  emit('newConversation')
}

function openSkillCenter() {
  if (!props.isUserLoggedIn) return
  emit('openSkillCenter')
  emit('update:sideDrawerOpen', false)
}

function openSessionDetail(item: SessionItem) {
  if (!props.isUserLoggedIn) return
  openSessionActionMenuId.value = null
  selectedSessionKey.value = item.sessionId
  conversationDrawerOpen.value = true
  emit('update:sideDrawerOpen', false)
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
  conversationDrawerOpen.value = false
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

function renameSessionFromMenu(item: SessionItem) {
  openSessionActionMenuId.value = null
  renameSession(item)
}

function deleteSessionFromMenu(item: SessionItem) {
  openSessionActionMenuId.value = null
  deleteSession(item)
}

function taskCardClass(tone: string): string {
  if (tone === 'success') return 'border-[#bfead4] bg-[#f4fff9]/78 text-[#2e7d5b]'
  if (tone === 'failed') return 'border-[#ffd8d1] bg-[#fff7f4]/82 text-[#a85f4d]'
  if (tone === 'partial') return 'border-[#ffe3aa] bg-[#fffaf0]/82 text-[#9a6a1f]'
  return 'border-white/70 bg-white/70 text-[#5a5288]'
}
</script>

<template>
  <div class="chat-mobile-viewport relative overflow-hidden bg-[#e8e6f0] text-[#4a4a6a]">
    <img :src="stageBackgroundUrl" class="absolute inset-0 h-full w-full object-cover">
    <div class="absolute inset-0 bg-gradient-to-b from-[#f8f5ff]/75 via-transparent to-[#f3efff]/80"></div>

    <header class="absolute left-0 right-0 top-0 z-20 px-4 pb-2 pt-[calc(env(safe-area-inset-top,0px)+8px)]">
      <div class="overflow-hidden rounded-[26px] border border-white/60 bg-white/34 shadow-[0_12px_32px_rgba(110,88,160,0.14)] backdrop-blur-2xl">
        <div class="flex h-[68px] items-center gap-2.5 px-3.5">
          <img :src="botAvatarUrl" :alt="`${botDisplayName} avatar`" class="h-11 w-11 shrink-0 rounded-full border-2 border-white/70 shadow-sm">
          <div class="min-w-0 flex-1 bg-transparent">
            <button
              type="button"
              class="chat-private-space-link chat-private-space-link--mobile"
              aria-label="打开私人空间"
              title="私人空间"
              @click="emit('update:privateSpaceOpen', true)"
            >
              <span class="i-carbon-flower-2 shrink-0 text-base"></span>
              <span class="truncate">私人空间</span>
            </button>
            <div class="mt-1 flex items-center gap-1.5 text-[14px] text-[#696391]">
              <span class="h-2.5 w-2.5 rounded-full shadow-[0_0_0_3px_rgba(78,209,126,0.12)]" :class="[connectionIndicator.color, connectionIndicator.pulse ? 'animate-pulse' : '']"></span>
              <span class="truncate">{{ connectionIndicator.label }}</span>
              <button
                v-if="canReconnect"
                type="button"
                class="ml-1 inline-flex h-6 items-center gap-1 rounded-full border border-[#d8cdf6] bg-white/80 px-2 text-[10px] font-semibold text-[#5f4e9f] shadow-sm active:scale-95"
                aria-label="重新连接当前会话"
                @click.stop="emit('reconnect')"
              >
                <span class="i-carbon-renew"></span>
                <span>重连</span>
              </button>
            </div>
          </div>
          <button
            class="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-white/60 bg-white/58 text-[#4f4c75] shadow-sm backdrop-blur transition active:scale-95 active:bg-white"
            aria-label="打开菜单"
            @click="emit('update:sideDrawerOpen', true)"
          >
            <span class="i-carbon-menu text-[22px]"></span>
          </button>
          <button
            class="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-white/60 bg-white/58 text-[#4f4c75] shadow-sm backdrop-blur transition active:scale-95 active:bg-white"
            aria-label="查看对话内容"
            title="查看对话内容"
            @click="conversationDrawerOpen = true"
          >
            <span class="i-carbon-chat text-[22px]"></span>
          </button>
        </div>

        <div class="scrollbar-none flex h-[44px] items-center gap-2 overflow-x-auto border-t border-white/38 bg-transparent px-3.5 whitespace-nowrap">
          <button
            class="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full border border-white/60 px-3 text-[13px] font-medium shadow-sm backdrop-blur"
            :class="isVoiceRuntimeOpen ? 'bg-[#eee8ff]/70 text-[#5a4c9d]' : 'bg-white/50 text-[#7f78a8]'"
            :aria-pressed="isVoiceRuntimeOpen"
            title="开启或关闭语音输入输出，保留文字聊天运行时"
            @click="emit('toggleWebrtcConnection')"
          >
            <span :class="[webrtcControlIcon, isWebrtcConnecting ? 'animate-spin' : '']"></span>
            <span>{{ webrtcControlLabel }}</span>
          </button>
          <button class="mobile-weather-pill inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full border border-white/60 bg-white/54 px-3 text-[13px] font-medium text-[#615b91] shadow-sm backdrop-blur">
            <span :class="[weather.icon, 'mobile-weather-pill__icon']"></span>
            <span>{{ weather.city }} {{ weather.temp }} {{ weather.condition }}</span>
          </button>
          <button class="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full border border-white/60 px-3 text-[13px] font-medium shadow-sm backdrop-blur" :class="voiceEnabled ? 'bg-[#eee8ff]/68 text-[#5a4c9d]' : 'bg-white/50 text-[#7f78a8]'" @click="emit('toggleVoice')">
              <span :class="voiceEnabled ? 'i-carbon-volume-up' : 'i-carbon-volume-mute'"></span><span>{{ voiceEnabled ? '声音已开' : '声音关闭' }}</span>
            </button>
          <button class="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full border border-white/60 px-3 text-[13px] font-medium shadow-sm backdrop-blur" :class="vadInterruptEnabled ? 'bg-[#eee8ff]/68 text-[#5a4c9d]' : 'bg-white/50 text-[#7f78a8]'" @click="emit('toggleVadInterrupt')">
              <span :class="vadInterruptEnabled ? 'i-carbon-microphone' : 'i-carbon-microphone-off'"></span><span>{{ vadInterruptEnabled ? '智能打断' : '禁止打断' }}</span>
            </button>
          <button class="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full border border-white/60 px-3 text-[13px] font-medium shadow-sm backdrop-blur" :class="isRealtimeChatOn ? 'bg-[#8b7fd4] text-white' : 'bg-white/50 text-[#7f78a8]'" @click="emit('toggleRealtimeChat')">
            <span :class="isRealtimeChatOn ? 'i-carbon-phone-voice-filled' : 'i-carbon-phone-voice'"></span>
            <span>{{ isRealtimeChatOn ? '陪伴中' : '语音陪伴' }}</span>
          </button>
        </div>
      </div>
    </header>

    <main class="absolute inset-x-0 bottom-0 top-0 z-10 overflow-hidden pt-[130px] pb-[174px]">
      <div class="relative h-full">
        <div class="absolute inset-x-0 top-0 h-[68%] min-h-[340px]">
          <component
            :is="avatarCanvas"
            :model-url="modelUrl"
            :emotion-state="emotionState"
            :connection-status="sessionStatus"
            :streaming-message="streamingMessage"
            :disabled="vrmDisabled"
            :model-scale="hasConversation ? 1.12 : 1.28"
          />
        </div>

        <div class="absolute inset-x-4 bottom-0 max-h-[46%] overflow-y-auto overscroll-contain px-0 py-1">
          <div v-if="!hasConversation" class="rounded-[22px] border border-white/55 bg-white/34 px-4 py-4 text-center shadow-[0_10px_24px_rgba(106,88,154,0.10)] backdrop-blur-xl">
            <p class="text-base font-semibold text-[#544b84]">今天想和我聊些什么呢？</p>
            <p class="mt-1.5 text-xs leading-5 text-[#8179a6]">我在这里陪你，也可以帮你查天气、车次和旅行安排。</p>
          </div>

          <div v-else class="space-y-3">
            <section v-for="round in visibleConversationRounds" :key="round.id" class="mobile-chat-thread-round space-y-2.5">
              <div class="ml-auto max-w-[92%] px-1 py-1 text-[#514d78]">
                <div class="mb-2 flex items-center gap-2">
                  <img :src="userAvatarUrl" alt="用户" class="h-8 w-8 rounded-full">
                  <span class="text-sm font-medium text-[#5a5880]">{{ isUserLoggedIn ? userDisplayName : '用户' }}</span>
                  <span class="text-xs text-[#b5b3c8]">{{ round.time }}</span>
                </div>
                <p class="mobile-user-reply-text">{{ round.userMsg }}</p>
              </div>

              <template v-for="assistant in round.assistantMessages" :key="assistant.id">
                <div v-if="assistant.hasContent || shouldShowAssistantProcess(assistant)" :class="assistantReplyShellClass(assistant)">
                  <div class="assistant-reply-header mb-2 flex items-center gap-2 text-sm font-semibold">
                    <img :src="botAvatarUrl" :alt="botDisplayName" class="h-8 w-8 rounded-full border border-white">
                    <span>{{ botDisplayName }}</span>
                    <span class="text-xs font-normal text-[#9c94ba]">{{ assistant.time }}</span>
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
            </section>

            <button
              v-if="mobileTaskCopy"
              type="button"
              class="w-full rounded-[18px] border p-2.5 text-left shadow-[0_8px_20px_rgba(115,92,165,0.10)] transition active:scale-[0.99]"
              :class="taskCardClass(mobileTaskCopy.tone)"
              @click="taskDetailsOpen = true"
            >
              <div class="flex items-center gap-2.5">
                <span class="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl bg-white/64 text-lg" :class="mobileTaskCopy.icon"></span>
                <div class="min-w-0 flex-1">
                  <p class="truncate text-sm font-semibold">{{ taskEntryLabel }}</p>
                  <p class="mt-1 line-clamp-1 text-xs opacity-80">{{ mobileTaskCopy.detail }}</p>
                  <div v-if="mobileTaskCopy.tone === 'running'" class="mt-2 h-1.5 overflow-hidden rounded-full bg-white/70">
                    <div class="h-full rounded-full bg-gradient-to-r from-[#f4a7df] to-[#8b7fd4]" :style="{ width: `${taskProgress?.totalProgress || 28}%` }"></div>
                  </div>
                </div>
                <span class="i-carbon-chevron-up shrink-0 text-base opacity-70"></span>
              </div>
            </button>
          </div>
        </div>
      </div>
    </main>

    <footer class="absolute left-1/2 z-30 w-[94vw] max-w-[520px] -translate-x-1/2" :style="composerStyle">
      <div class="rounded-[30px] border border-white/65 bg-white/58 p-2.5 shadow-[0_14px_36px_rgba(82,67,132,0.18)] backdrop-blur-xl">
        <QuickActionBubbles
          class="mb-2"
          :actions="quickActions"
          :disabled="quickActionsDisabled"
          variant="mobile"
          @select="action => emit('quickAction', action)"
        />

        <p v-if="sendError" class="mb-2 px-1 text-xs text-red-500">{{ sendError }}</p>

        <div class="flex items-center gap-2 rounded-full border border-[#e0ddf5] bg-white/92 px-1.5 py-1.5 shadow-inner">
          <button
            class="h-10 w-10 shrink-0 inline-flex items-center justify-center rounded-full text-base transition active:scale-95"
            :class="inputMode === 'ptt' ? 'bg-[#8b7fd4] text-white shadow-sm' : 'bg-[#e8e5f5] text-[#5f5a87]'"
            :disabled="isSpeechRecording || isSpeechTranscribing"
            :title="inputMode === 'ptt' ? '切换回文本输入模式' : '切换到按住说话模式'"
            @click="emit('toggleInputMode')"
          >
            <span :class="inputMode === 'ptt' ? 'i-carbon-keyboard text-[22px]' : 'i-carbon-microphone text-[22px]'"></span>
          </button>

          <template v-if="inputMode === 'text'">
            <input
              :value="inputText"
              type="text"
              placeholder="输入消息..."
              class="min-w-0 flex-1 bg-transparent px-2 text-sm text-[#4a4a6a] placeholder:text-[#b5b3c8] outline-none"
              @input="emit('update:inputText', ($event.target as HTMLInputElement).value)"
              @keydown="emit('keydownEnter', $event as KeyboardEvent)"
            >
            <button
              class="h-10 w-10 shrink-0 inline-flex items-center justify-center text-white shadow-sm transition active:scale-95 disabled:opacity-40 disabled:active:scale-100"
              :class="isBotResponding ? 'rounded-full bg-[#8b7fd4] active:bg-[#7b6ec6]' : 'rounded-full bg-[#8b7fd4]'"
              :disabled="isBotResponding ? false : !inputText.trim()"
              :aria-label="isBotResponding ? '停止回复' : '发送消息'"
              :title="isBotResponding ? '停止回复' : '发送消息'"
              @click="isBotResponding ? emit('stopResponse') : emit('send')"
            >
              <span v-if="!isBotResponding" class="i-carbon-send text-[22px]"></span>
              <span v-else class="h-3.5 w-3.5 rounded-[3px] bg-white shadow-[0_1px_4px_rgba(74,58,130,0.18)]" aria-hidden="true"></span>
            </button>
          </template>

          <template v-else>
            <button
              type="button"
              class="flex-1 rounded-full px-4 py-2.5 text-sm transition"
              :class="isSpeechRecording ? 'bg-[#f0e8ff] text-[#7f5edc] shadow-inner' : 'bg-[#f3f1fb] text-[#6b6894] active:bg-[#e6e2f6]'"
              :disabled="isSpeechTranscribing"
              @mousedown="emit('startHoldToTalk')"
              @mouseup="emit('endHoldToTalk')"
              @mouseleave="emit('endHoldToTalk')"
              @touchstart.prevent="emit('startHoldToTalk')"
              @touchend.prevent="emit('endHoldToTalk')"
              @touchcancel.prevent="emit('endHoldToTalk')"
            >
              <span class="inline-flex items-center justify-center gap-2">
                <span
                  class="inline-block h-2 w-2 rounded-full"
                  :class="isSpeechRecording ? 'animate-pulse bg-[#f08bb8]' : 'bg-[#c9c3e6]'"
                ></span>
                {{ holdToTalkLabel }}
              </span>
            </button>
            <button
              type="button"
              class="h-10 w-10 shrink-0 inline-flex items-center justify-center rounded-full text-white shadow-sm transition active:scale-95"
              :class="isSpeechRecording ? 'bg-[#f08bb8]' : 'bg-[#8b7fd4] active:bg-[#7b6ec6]'"
              :disabled="isSpeechTranscribing"
              aria-label="按住说话"
              @mousedown="emit('startHoldToTalk')"
              @mouseup="emit('endHoldToTalk')"
              @mouseleave="emit('endHoldToTalk')"
              @touchstart.prevent="emit('startHoldToTalk')"
              @touchend.prevent="emit('endHoldToTalk')"
              @touchcancel.prevent="emit('endHoldToTalk')"
            >
              <span class="i-carbon-microphone-filled text-[22px]"></span>
            </button>
          </template>
        </div>
      </div>
    </footer>

    <Teleport to="body">
      <Transition name="overlay">
        <div
          v-if="taskDetailsOpen"
          class="fixed inset-0 z-40 bg-[#1e1a38]/35 backdrop-blur-[2px]"
          @click="taskDetailsOpen = false"
        ></div>
      </Transition>
      <Transition name="drawer-up">
        <aside
          v-if="taskDetailsOpen"
          class="fixed inset-x-3 bottom-3 z-50 max-h-[82vh] overflow-hidden rounded-[28px] border border-white/65 bg-[#fbf8ff]/84 text-[#4f4a72] shadow-[0_24px_70px_rgba(105,86,150,0.24)] backdrop-blur-2xl"
        >
          <header class="flex items-center justify-between gap-3 border-b border-white/55 px-4 py-3">
            <div>
              <div class="mx-auto mb-2 h-1 w-10 rounded-full bg-[#d8d0ef]"></div>
              <h2 class="text-base font-semibold text-[#4a4a6a]">任务详情</h2>
              <p class="mt-0.5 text-xs text-[#9997b5]">{{ taskEntryLabel }}</p>
            </div>
            <button
              type="button"
              class="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-white/70 bg-white/62 text-[#7b719f] shadow-sm transition active:scale-95 active:bg-white"
              aria-label="关闭任务详情"
              @click="taskDetailsOpen = false"
            >
              <span class="i-carbon-close text-lg"></span>
            </button>
          </header>
          <div class="max-h-[calc(82vh-78px)] overflow-y-auto p-4 pb-[calc(env(safe-area-inset-bottom,0px)+16px)]">
            <TaskProgressCard :data="taskProgress" @retry="item => emit('retryTask', item)" />
          </div>
        </aside>
      </Transition>
    </Teleport>

    <Teleport to="body">
      <Transition name="overlay">
        <div
          v-if="conversationDrawerOpen"
          class="fixed inset-0 z-40 bg-[#1e1a38]/35 backdrop-blur-[2px]"
          @click="conversationDrawerOpen = false"
        ></div>
      </Transition>
      <Transition name="drawer-right">
        <aside
          v-if="conversationDrawerOpen"
          class="fixed inset-y-3 right-3 z-50 flex w-[min(92vw,380px)] flex-col overflow-hidden rounded-l-[28px] rounded-r-[24px] border border-white/65 bg-[#fbf8ff]/82 text-[#4f4a72] shadow-[0_24px_70px_rgba(105,86,150,0.24)] backdrop-blur-2xl"
        >
          <header class="border-b border-white/55 px-5 pb-4 pt-[calc(env(safe-area-inset-top,0px)+18px)]">
            <div class="flex items-center justify-between gap-3">
              <div class="min-w-0">
                <h2 class="truncate text-lg font-semibold text-[#4a4a6a]" :title="selectedSession?.title || '对话内容'">
                  {{ selectedSession?.displayTitle || selectedSession?.title || '对话内容' }}
                </h2>
                <p class="mt-0.5 text-xs text-[#9997b5]">{{ selectedSessionIsCurrent ? '当前对话' : '历史摘要' }}</p>
              </div>
              <button
                type="button"
                class="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-white/70 bg-white/62 text-[#7b719f] shadow-sm transition active:scale-95 active:bg-white"
                aria-label="关闭对话内容"
                @click="conversationDrawerOpen = false"
              >
                <span class="i-carbon-close text-xl"></span>
              </button>
            </div>
          </header>

          <div class="min-h-0 flex-1 overflow-y-auto px-4 py-4">
            <section v-if="selectedSession" class="mb-4 rounded-[22px] border border-white/70 bg-white/55 p-4 shadow-sm">
              <div class="flex items-start gap-3">
                <div class="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-[#f0eaff] text-[#8a6fe8]">
                  <span :class="selectedSession.icon" class="text-lg"></span>
                </div>
                <div class="min-w-0 flex-1">
                  <p class="text-sm leading-6 text-[#625b84]">{{ selectedSessionSummary }}</p>
                  <div class="mt-3 flex flex-wrap gap-2">
                    <span
                      v-for="tag in selectedSessionTags"
                      :key="tag"
                      class="rounded-full border border-white/70 bg-white/62 px-2.5 py-1 text-[11px] font-medium text-[#8b7ab8]"
                    >
                      {{ tag }}
                    </span>
                  </div>
                </div>
              </div>
            </section>

            <template v-if="selectedSessionIsCurrent && conversationRounds.length > 0">
              <div class="space-y-5">
                <section v-for="round in conversationRounds" :key="round.id" class="mobile-chat-thread-round space-y-3">
                  <div class="flex justify-end">
                    <div class="max-w-[92%] px-1 py-1">
                      <div class="mb-2 flex items-center gap-2">
                        <img :src="userAvatarUrl" alt="用户" class="h-8 w-8 rounded-full">
                        <span class="text-sm font-medium text-[#5a5880]">{{ isUserLoggedIn ? userDisplayName : '用户' }}</span>
                        <span class="text-xs text-[#b5b3c8]">{{ round.time }}</span>
                      </div>
                      <p class="break-words text-sm leading-6 text-[#5a5880]">{{ round.userMsg }}</p>
                    </div>
                  </div>

                  <template v-for="assistant in round.assistantMessages" :key="assistant.id">
                    <div v-if="assistant.hasContent || shouldShowAssistantProcess(assistant)" :class="assistantReplyShellClass(assistant)">
                      <div class="assistant-reply-header mb-2 flex items-center gap-2">
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
                </section>
              </div>
            </template>

            <template v-else-if="selectedSession && !selectedSessionIsCurrent">
              <div class="space-y-3">
                <p class="px-1 text-xs font-medium text-[#aaa1c7]">最近片段</p>
                <section class="rounded-[20px] border border-[#dfe5f8] bg-[#f3f6ff]/78 p-3 shadow-sm">
                  <div class="mb-2 flex items-center gap-2">
                    <img :src="userAvatarUrl" alt="用户" class="h-8 w-8 rounded-full">
                    <span class="text-sm font-medium text-[#5a5880]">你</span>
                    <span class="ml-auto text-xs text-[#b5b3c8]">{{ selectedSession.time }}</span>
                  </div>
                  <p class="break-words text-sm leading-6 text-[#5a5880]">{{ selectedSession.preview || selectedSession.title }}</p>
                </section>
                <section class="rounded-[20px] border border-[#e8e5f0] bg-white/70 p-3 shadow-sm">
                  <div class="mb-2 flex items-center gap-2">
                    <img :src="botAvatarUrl" :alt="botDisplayName" class="h-8 w-8 rounded-full">
                    <span class="text-sm font-medium text-[#5a5880]">{{ botDisplayName }}</span>
                    <span class="ml-auto text-xs text-[#b5b3c8]">{{ selectedSession.time }}</span>
                  </div>
                  <p class="break-words text-sm leading-6 text-[#5a5880]">{{ selectedSessionSummary }}</p>
                </section>
              </div>
              <button
                class="conversation-continue-button group mt-4 w-full"
                @click="continueSelectedSession"
              >
                <span class="conversation-continue-shine"></span>
                <span class="relative z-[1]">继续这段对话</span>
                <span class="i-carbon-arrow-right relative z-[1] text-base opacity-90 transition group-active:translate-x-0.5"></span>
              </button>
            </template>

            <div v-else class="flex h-full min-h-[360px] flex-col items-center justify-center text-center">
              <span class="i-carbon-chat text-5xl text-[#d0cde0]"></span>
              <p class="mt-4 text-sm font-medium text-[#9997b5]">等待开始对话...</p>
              <p class="mt-1 text-xs text-[#b5b3c8]">发送消息后对话内容会显示在这里</p>
            </div>
          </div>
        </aside>
      </Transition>
    </Teleport>

    <Teleport to="body">
      <Transition name="overlay">
        <div v-if="sideDrawerOpen" class="fixed inset-0 z-40 bg-[#1e1a38]/35" @click="emit('update:sideDrawerOpen', false)"></div>
      </Transition>
      <Transition name="drawer-left">
        <aside v-if="sideDrawerOpen" class="fixed inset-y-0 left-0 z-50 w-[84%] max-w-[320px] overflow-y-auto bg-[#f7f5fc] p-4 shadow-2xl">
          <div class="mb-4 flex items-center justify-between">
            <div class="flex items-center gap-2">
              <img :src="userAvatarUrl" :alt="`${userDisplayName} avatar`" class="h-9 w-9 rounded-full border border-white/70 bg-white/70 shadow-sm">
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-2">
                  <p class="max-w-[160px] truncate text-sm font-semibold text-[#4a4a6a]">{{ userDisplayName }}</p>
                  <button
                    v-if="isUserLoggedIn"
                    type="button"
                    class="rounded bg-[#e8dff8] px-2 py-0.5 text-[11px] font-medium text-[#8b7fd4] transition active:scale-95"
                    @click="emit('openSubscription')"
                  >
                    {{ userSubscriptionLabel }}
                  </button>
                </div>
                <p v-if="isUserLoggedIn" class="text-xs text-[#9997b5]">订阅等级</p>
                <div v-else class="mt-1 flex items-center gap-2 text-xs text-[#9997b5]">
                  <span class="h-1.5 w-1.5 rounded-full bg-[#c8c1dd]"></span>
                  <button
                    type="button"
                    class="chat-auth-text-action"
                    @click="emit('openLogin')"
                  >
                    登入
                  </button>
                  <span class="text-[#c8c1dd]">/</span>
                  <button
                    type="button"
                    class="chat-auth-text-action"
                    @click="emit('openRegister')"
                  >
                    注册
                  </button>
                </div>
              </div>
            </div>
            <button
              type="button"
              class="inline-flex h-10 w-10 items-center justify-center rounded-full border border-[#e6e1f6] bg-white text-[#4f4c75] shadow-sm transition active:scale-95 active:bg-[#f2effb]"
              aria-label="关闭侧边抽屉"
              @click="emit('update:sideDrawerOpen', false)"
            >
              <span class="i-carbon-close text-xl leading-none"></span>
            </button>
          </div>

          <button
            type="button"
            class="mb-3 h-11 w-full rounded-xl border border-[#d8cdf6] bg-gradient-to-r from-[#f7f2ff] to-[#e9e0ff] font-semibold text-[#5f4e9f] active:scale-[0.99]"
            :class="{ 'cursor-not-allowed opacity-50 active:scale-100': !isUserLoggedIn }"
            :disabled="!isUserLoggedIn"
            :title="isUserLoggedIn ? '新建对话' : '登录后可新建对话'"
            @click="createNewConversation"
          >
            {{ isUserLoggedIn ? '+ 新建对话' : '登录后可新建对话' }}
          </button>
          <div v-if="!isUserLoggedIn" class="mb-3 rounded-2xl border border-[#ebe8f6] bg-white/68 px-4 py-5 text-center shadow-sm">
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
              class="group mobile-session-card w-full rounded-xl border p-3 text-left outline-none transition active:scale-[0.99]"
              :class="(selectedSession?.sessionId === item.sessionId) ? 'border-[#c5c3e8] bg-white shadow-sm' : 'border-[#ebe8f6] bg-white/75'"
              @click="openSessionDetail(item)"
              @keydown.enter.prevent="openSessionDetail(item)"
              @keydown.space.prevent="openSessionDetail(item)"
            >
              <div class="flex items-start gap-2">
                <div class="min-w-0 flex-1">
                  <span class="block truncate text-sm text-[#4a4a6a]" :title="item.displayTitle || item.title">{{ item.displayTitle || item.title }}</span>
                  <p v-if="item.preview" class="mt-1 truncate text-xs text-[#9997b5]">{{ item.preview }}</p>
                </div>
                <div class="mobile-session-card-meta">
                  <span class="mobile-session-card-time">{{ item.time }}</span>
                  <div
                    class="mobile-session-action-menu-wrap"
                    @keydown.enter.stop
                    @keydown.space.stop
                  >
                    <button
                      type="button"
                      class="mobile-session-more-button"
                      :class="{ 'is-open': openSessionActionMenuId === item.sessionId }"
                      aria-label="更多对话操作"
                      title="更多操作"
                      :aria-expanded="openSessionActionMenuId === item.sessionId"
                      @click.stop="toggleSessionActionMenu(item)"
                    >
                      <span class="i-carbon-overflow-menu-horizontal text-base"></span>
                    </button>
                    <Transition name="mobile-session-action-menu">
                      <div
                        v-if="openSessionActionMenuId === item.sessionId"
                        class="mobile-session-action-menu"
                        @click.stop
                      >
                        <button type="button" class="mobile-session-action-menu-item" @click.stop="renameSessionFromMenu(item)">
                          <span class="i-carbon-edit text-sm"></span>
                          <span>重命名</span>
                        </button>
                        <button type="button" class="mobile-session-action-menu-item mobile-session-action-menu-item--danger" @click.stop="deleteSessionFromMenu(item)">
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

          <button v-if="isUserLoggedIn && hasMoreSessions" class="mt-3 w-full rounded-xl border border-[#b7aae8] bg-[#efe9ff] py-2 text-sm text-[#6e5ec4]" @click="emit('update:showAllDialog', true)">
            查看全部对话
          </button>

          <button
            class="mt-4 w-full overflow-hidden rounded-2xl bg-cover bg-center px-4 py-4 text-left shadow-[0_10px_28px_rgba(132,112,190,0.16)]"
            :class="{ 'cursor-not-allowed opacity-55': !isUserLoggedIn }"
            style="background-image: linear-gradient(90deg, rgba(255,255,255,0.78), rgba(255,255,255,0.34)), url('/explore_skills_pastel_bg.png');"
            :disabled="!isUserLoggedIn"
            :title="isUserLoggedIn ? '技能中心' : '登录后可使用技能中心'"
            @click="openSkillCenter"
          >
            <span class="block text-base font-semibold text-[#575076]">Aini 技能中心</span>
            <span class="mt-2 block text-xs leading-5 text-[#756f99]">{{ isUserLoggedIn ? '去学习新技能，让陪伴持续成长' : '登录后再为 Aini 开启新的能力' }}</span>
            <span class="mt-3 inline-flex h-8 items-center rounded-full bg-[#bdaee8]/90 px-4 text-xs font-medium text-white">{{ isUserLoggedIn ? '去探索' : '已冻结' }}</span>
          </button>

          <RouterLink
            to="/"
            class="mt-4 flex w-full items-center gap-2 rounded-xl border border-[#e6e1f6] bg-white/80 px-3 py-2 text-sm text-[#4f4c75]"
            aria-label="返回首页"
            title="返回首页"
            @click="emit('update:sideDrawerOpen', false)"
          >
            <span class="i-carbon-home text-[#7b61d9]"></span>
            返回首页
          </RouterLink>
        </aside>
      </Transition>
    </Teleport>

    <Teleport to="body">
      <Transition name="private-space">
        <aside
          v-if="privateSpaceOpen"
          class="chat-private-space-panel fixed inset-y-3 left-3 z-[58] w-[min(340px,calc(100vw-28px))] overflow-hidden rounded-[28px] border border-white/65 bg-[#fff9ff]/76 text-[#4f4a72] shadow-[0_24px_70px_rgba(105,86,150,0.20)] backdrop-blur-2xl"
        >
          <div class="absolute inset-0 pointer-events-none bg-[radial-gradient(circle_at_18%_10%,rgba(255,220,238,0.85),transparent_34%),radial-gradient(circle_at_94%_0%,rgba(205,224,255,0.70),transparent_34%)]"></div>
          <div class="relative flex h-full flex-col">
            <header class="px-5 pb-4 pt-[calc(env(safe-area-inset-top,0px)+18px)]">
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <p class="text-xs font-medium leading-5 text-[#9b91b7]">陪伴记忆</p>
                  <h2 class="mt-1 text-lg font-semibold leading-7 text-[#4a4a6a]">私人空间</h2>
                  <p class="mt-1.5 text-xs leading-5 text-[#7e779f]">保存你们的陪伴、记忆和房间氛围。</p>
                </div>
                <button
                  type="button"
                  class="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-white/70 bg-white/60 text-[#7b719f] shadow-sm"
                  aria-label="关闭私人空间"
                  @click="emit('update:privateSpaceOpen', false)"
                >
                  <span class="i-carbon-close text-lg"></span>
                </button>
              </div>
            </header>

            <div class="relative flex-1 overflow-y-auto px-4 pb-[calc(env(safe-area-inset-bottom,0px)+18px)]">
              <section class="space-y-3">
                <div class="rounded-[22px] border border-white/60 bg-white/42 p-3.5">
                  <div class="flex items-center gap-3">
                    <img :src="botAvatarUrl" :alt="botDisplayName" class="h-11 w-11 rounded-full border border-white/70 shadow-sm">
                    <div>
                      <p class="text-[11px] text-[#9e95bd]">我的角色</p>
                      <h3 class="text-sm font-semibold text-[#514873]">{{ botDisplayName }}</h3>
                    </div>
                  </div>
                  <div class="mt-3 grid grid-cols-2 gap-2 text-xs text-[#716a92]">
                    <button class="rounded-full bg-white/45 px-3 py-2 text-left"><span class="i-carbon-music mr-1 text-[#b796df]"></span>角色声音</button>
                    <button class="rounded-full bg-white/45 px-3 py-2 text-left"><span class="i-carbon-person-favorite mr-1 text-[#b796df]"></span>角色服装</button>
                    <button class="rounded-full bg-white/45 px-3 py-2 text-left"><span class="i-carbon-face-wink mr-1 text-[#b796df]"></span>角色人格</button>
                    <button class="rounded-full bg-white/45 px-3 py-2 text-left"><span class="i-carbon-notebook-reference mr-1 text-[#b796df]"></span>角色设定</button>
                  </div>
                </div>

                <div class="rounded-[22px] border border-white/60 bg-white/36 p-3.5">
                  <p class="mb-2.5 text-sm font-semibold text-[#514873]">记忆中的你</p>
                  <div class="space-y-2 text-xs text-[#716a92]">
                    <button class="flex w-full items-center gap-2 rounded-full bg-white/42 px-3 py-2 text-left"><span class="i-carbon-bookmark-filled text-[#e3a0bf]"></span>长期偏好</button>
                    <button class="flex w-full items-center gap-2 rounded-full bg-white/42 px-3 py-2 text-left"><span class="i-carbon-star text-[#d6a85f]"></span>兴趣</button>
                    <button class="flex w-full items-center gap-2 rounded-full bg-white/42 px-3 py-2 text-left"><span class="i-carbon-events text-[#89a9d8]"></span>共同经历</button>
                    <button class="flex w-full items-center gap-2 rounded-full bg-white/42 px-3 py-2 text-left"><span class="i-carbon-favorite text-[#c49ee2]"></span>长期关系</button>
                  </div>
                </div>

                <div class="rounded-[22px] border border-white/60 bg-white/36 p-3.5">
                  <p class="mb-2.5 text-sm font-semibold text-[#514873]">空间氛围</p>
                  <div class="grid grid-cols-2 gap-2 text-xs text-[#716a92]">
                    <button class="rounded-full bg-white/42 px-3 py-2 text-left"><span class="i-carbon-image mr-1 text-[#89a9d8]"></span>背景切换</button>
                    <button class="rounded-full bg-white/42 px-3 py-2 text-left"><span class="i-carbon-partly-cloudy mr-1 text-[#d6a85f]"></span>天气联动</button>
                    <button class="rounded-full bg-white/42 px-3 py-2 text-left"><span class="i-carbon-home mr-1 text-[#c49ee2]"></span>房间风格</button>
                    <button class="rounded-full bg-white/42 px-3 py-2 text-left"><span class="i-carbon-moon mr-1 text-[#8ca2de]"></span>昼夜模式</button>
                  </div>
                </div>

                <div class="rounded-[22px] border border-white/60 bg-white/32 p-3.5">
                  <p class="mb-2.5 text-sm font-semibold text-[#514873]">对话管理</p>
                  <div class="space-y-2 text-xs text-[#716a92]">
                    <button class="flex w-full items-center gap-2 rounded-full bg-white/42 px-3 py-2 text-left" @click="emit('update:showAllDialog', true)"><span class="i-carbon-chat"></span>查看全部对话</button>
                    <button class="flex w-full items-center gap-2 rounded-full bg-white/42 px-3 py-2 text-left"><span class="i-carbon-download"></span>导出聊天记录</button>
                    <button class="flex w-full items-center gap-2 rounded-full bg-white/42 px-3 py-2 text-left text-[#a86d83]"><span class="i-carbon-trash-can"></span>清空历史记录</button>
                  </div>
                </div>

                <div class="rounded-[22px] border border-white/60 bg-white/30 p-3.5">
                  <p class="mb-2.5 text-sm font-semibold text-[#514873]">账号与隐私</p>
                  <div v-if="isUserLoggedIn" class="space-y-2 text-xs text-[#716a92]">
                    <button class="flex w-full items-center gap-2 rounded-full bg-white/42 px-3 py-2 text-left"><span class="i-carbon-devices"></span>登录设备</button>
                    <button class="flex w-full items-center gap-2 rounded-full bg-white/42 px-3 py-2 text-left"><span class="i-carbon-security"></span>隐私管理</button>
                    <button class="flex w-full items-center gap-2 rounded-full bg-white/42 px-3 py-2 text-left" @click="emit('logout')"><span class="i-carbon-logout"></span>退出登录</button>
                  </div>
                  <div v-else class="text-xs leading-5 text-[#716a92]">
                    <p class="mb-1 text-[#9b91b7]">登入后可以同步你的陪伴记忆</p>
                    <div class="flex items-center gap-2">
                      <button class="chat-auth-text-action" @click="emit('openLogin')">登入</button>
                      <span class="text-[#c8c1dd]">/</span>
                      <button class="chat-auth-text-action" @click="emit('openRegister')">注册</button>
                    </div>
                  </div>
                </div>
              </section>
            </div>
          </div>
        </aside>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped lang="scss">
.chat-mobile-viewport {
  min-height: 100vh;
  height: 100vh;
  background:
    radial-gradient(circle at 14% 4%, rgba(255, 215, 234, 0.76), transparent 30%),
    radial-gradient(circle at 86% 2%, rgba(221, 235, 255, 0.76), transparent 34%),
    linear-gradient(135deg, #f8f3ff 0%, #fff7fb 48%, #f3f6ff 100%);
  font-family: var(--soulmeet-font-family);

  &::before {
    content: "";
    position: absolute;
    inset: 0;
    z-index: 1;
    pointer-events: none;
    background:
      linear-gradient(180deg, rgba(255, 247, 253, 0.58), transparent 24%, transparent 66%, rgba(248, 243, 255, 0.72)),
      radial-gradient(circle at 50% 78%, rgba(232, 218, 255, 0.38), transparent 42%);
  }
}

.chat-private-space-panel {
  font-family: var(--soulmeet-font-family);
}

.chat-mobile-viewport > header,
.chat-mobile-viewport > main,
.chat-mobile-viewport > footer {
  position: absolute;
  z-index: 12;
}

.chat-mobile-viewport > header :deep(.backdrop-blur-2xl),
.chat-mobile-viewport > footer > div {
  border-color: rgba(255, 255, 255, 0.78);
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.68), rgba(255, 247, 253, 0.48)),
    rgba(255, 255, 255, 0.5);
  box-shadow: 0 18px 42px rgba(139, 122, 230, 0.15), inset 0 1px 0 rgba(255, 255, 255, 0.78);
}

.chat-mobile-viewport :deep(button[class*="bg-[#8b7fd4]"]) {
  background: linear-gradient(135deg, #8b7ae6, #c59dff 58%, #ffbddd) !important;
  box-shadow: 0 10px 24px rgba(139, 122, 230, 0.22);
}

.chat-mobile-viewport :deep(.bg-white\/56),
.chat-mobile-viewport :deep(.bg-white\/58),
.chat-mobile-viewport :deep(.bg-white\/70),
.chat-mobile-viewport :deep(.bg-white\/74),
.chat-mobile-viewport :deep(.bg-white\/76),
.chat-mobile-viewport :deep(.bg-white\/78) {
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.72);
}

.conversation-continue-button {
  position: relative;
  display: inline-flex;
  min-height: 48px;
  align-items: center;
  justify-content: center;
  gap: 0.45rem;
  overflow: hidden;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.72);
  background:
    linear-gradient(135deg, rgba(151, 120, 241, 0.96) 0%, rgba(198, 129, 240, 0.94) 52%, rgba(247, 176, 225, 0.96) 100%);
  padding: 0 1.35rem;
  color: #fff;
  font-size: 0.95rem;
  font-weight: 700;
  letter-spacing: 0;
  box-shadow:
    0 16px 30px rgba(167, 111, 226, 0.24),
    0 7px 18px rgba(255, 176, 225, 0.17),
    inset 0 1px 0 rgba(255, 255, 255, 0.72);
  text-shadow: 0 1px 8px rgba(80, 56, 130, 0.16);
  transition: transform 160ms ease, filter 160ms ease;
}

.conversation-continue-button:active {
  transform: scale(0.98);
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

.mobile-weather-pill {
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.72), rgba(255, 247, 253, 0.52)),
    rgba(245, 240, 255, 0.5) !important;
  box-shadow:
    0 8px 18px rgba(117, 96, 168, 0.1),
    inset 0 1px 0 rgba(255, 255, 255, 0.78);
  color: #625b84;
}

.mobile-weather-pill__icon {
  color: #8f78df !important;
}

.mobile-weather-pill__icon.i-carbon-sun {
  color: #f59e0b !important;
}

.mobile-weather-pill__icon.i-carbon-rain,
.mobile-weather-pill__icon.i-carbon-rain-drizzle {
  color: #2563eb !important;
}

.mobile-weather-pill__icon.i-carbon-snow {
  color: #0891b2 !important;
}

.mobile-weather-pill__icon.i-carbon-fog {
  color: #6b7280 !important;
}

.mobile-weather-pill__icon.i-carbon-cloudy {
  color: #64748b !important;
}

.mobile-weather-pill__icon.i-carbon-partly-cloudy {
  color: #f59e0b !important;
}

.chat-private-space-link {
  appearance: none;
  display: inline-flex;
  max-width: 100%;
  min-width: 0;
  align-items: center;
  gap: 0.35rem;
  border: 0;
  background: transparent;
  padding: 0;
  color: #706790;
  font: inherit;
  font-weight: 600;
  line-height: 1.35;
  text-align: left;
  text-decoration: underline;
  text-decoration-color: transparent;
  text-underline-offset: 4px;
}

.chat-private-space-link--mobile {
  font-size: 0.95rem;
}

.chat-private-space-link span:first-child {
  color: #b59ce8;
}

.chat-private-space-link:active,
.chat-private-space-link:focus-visible {
  color: #7d62df;
  text-decoration-color: rgba(125, 98, 223, 0.36);
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
  text-decoration: underline;
  text-decoration-color: transparent;
  text-underline-offset: 3px;
}

.chat-auth-text-action:active,
.chat-auth-text-action:focus-visible {
  color: #7d62df;
  text-decoration-color: rgba(125, 98, 223, 0.36);
  outline: none;
}

.assistant-task-reply-shell {
  padding: 0.1rem 0 0.3rem;
  color: #514b78;
}

.assistant-task-reply-shell .assistant-reply-header {
  margin-bottom: 0.45rem;
  padding: 0 0.1rem;
}

.assistant-task-reply-shell .assistant-reply-header img {
  border: 1px solid rgba(255, 255, 255, 0.76);
  box-shadow: 0 4px 10px rgba(115, 92, 165, 0.08);
}

.assistant-chat-reply-shell {
  padding: 0.1rem 0.15rem 0.35rem;
  color: #514b78;
}

.mobile-chat-thread-round {
  content-visibility: auto;
  contain-intrinsic-size: 260px;
}

.assistant-chat-reply-shell,
.assistant-task-reply-shell {
  contain: layout paint;
}

.assistant-chat-reply-shell .assistant-reply-header {
  margin-bottom: 0.35rem;
}

.assistant-chat-reply-shell .assistant-reply-header img {
  border: 1px solid rgba(255, 255, 255, 0.76);
  box-shadow: 0 4px 10px rgba(115, 92, 165, 0.08);
}

.mobile-user-reply-text {
  margin: 0;
  color: #5a5880;
  font-family: var(--soulmeet-font-family);
  font-size: var(--soulmeet-chat-user-font-size);
  line-height: 1.72;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
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

@supports (height: 100dvh) {
  .chat-mobile-viewport {
    min-height: 100dvh;
    height: 100dvh;
  }
}

.scrollbar-none {
  scrollbar-width: none;
}

.scrollbar-none::-webkit-scrollbar {
  display: none;
}

.overlay-enter-active,
.overlay-leave-active {
  transition: opacity 0.25s ease;
}

.overlay-enter-from,
.overlay-leave-to {
  opacity: 0;
}

.drawer-left-enter-active,
.drawer-left-leave-active {
  transition: transform 0.25s ease;
}

.drawer-left-enter-from,
.drawer-left-leave-to {
  transform: translateX(-100%);
}

.drawer-right-enter-active,
.drawer-right-leave-active {
  transition: opacity 0.24s ease, transform 0.28s cubic-bezier(0.2, 0.8, 0.2, 1);
}

.drawer-right-enter-from,
.drawer-right-leave-to {
  opacity: 0;
  transform: translateX(100%);
}

.drawer-up-enter-active,
.drawer-up-leave-active {
  transition: transform 0.25s ease;
}

.drawer-up-enter-from,
.drawer-up-leave-to {
  transform: translateY(100%);
}

.private-space-enter-active,
.private-space-leave-active {
  transition: opacity 0.26s ease, transform 0.32s cubic-bezier(0.2, 0.8, 0.2, 1);
}

.private-space-enter-from,
.private-space-leave-to {
  opacity: 0;
  transform: translateX(-22px);
}

.prose {
  :deep(p) {
    margin: 0;
  }
}

.drawer-prose {
  :deep(p) {
    margin: 0.4em 0;
  }

  :deep(p:first-child) {
    margin-top: 0;
  }

  :deep(p:last-child) {
    margin-bottom: 0;
  }

  :deep(ul),
  :deep(ol) {
    margin: 0.45em 0;
    padding-left: 1.25em;
  }

  :deep(code) {
    border-radius: 0.25rem;
    background: #f0eef5;
    padding: 0.125em 0.25em;
    font-size: 0.875em;
  }
}

.mobile-session-card-meta {
  display: flex;
  min-width: 42px;
  flex: 0 0 auto;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.25rem;
}

.mobile-session-card-time {
  color: #b5b3c8;
  font-size: 0.69rem;
  line-height: 1rem;
  white-space: nowrap;
}

.mobile-session-action-menu-wrap {
  position: relative;
}

.mobile-session-more-button {
  display: inline-flex;
  width: 30px;
  height: 24px;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: #a59bc0;
  opacity: 0;
  transition: opacity 0.16s ease, color 0.16s ease, background 0.16s ease;
}

.mobile-session-card:hover .mobile-session-more-button,
.mobile-session-card:focus-within .mobile-session-more-button,
.mobile-session-card:active .mobile-session-more-button,
.mobile-session-more-button.is-open {
  opacity: 1;
}

.mobile-session-more-button:focus-visible,
.mobile-session-more-button:active,
.mobile-session-more-button.is-open {
  background: rgba(245, 239, 255, 0.88);
  color: #7d62df;
  outline: none;
}

.mobile-session-action-menu {
  position: absolute;
  top: calc(100% + 0.32rem);
  right: 0;
  z-index: 32;
  width: 112px;
  overflow: hidden;
  border-radius: 14px;
  border: 1px solid rgba(232, 225, 246, 0.88);
  background: rgba(255, 253, 255, 0.96);
  padding: 0.35rem;
  box-shadow: 0 14px 30px rgba(105, 86, 150, 0.16);
  backdrop-filter: blur(16px);
}

.mobile-session-action-menu-item {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 0.4rem;
  border: 0;
  border-radius: 10px;
  background: transparent;
  padding: 0.48rem 0.55rem;
  color: #6f6594;
  font-size: 0.78rem;
  font-weight: 600;
  text-align: left;
}

.mobile-session-action-menu-item:active,
.mobile-session-action-menu-item:focus-visible {
  background: rgba(245, 239, 255, 0.92);
  color: #7d62df;
  outline: none;
}

.mobile-session-action-menu-item--danger {
  color: #b56d82;
}

.mobile-session-action-menu-item--danger:active,
.mobile-session-action-menu-item--danger:focus-visible {
  background: rgba(255, 240, 246, 0.9);
  color: #d85d78;
}

.mobile-session-action-menu-enter-active,
.mobile-session-action-menu-leave-active {
  transition: opacity 0.16s ease, transform 0.16s ease;
}

.mobile-session-action-menu-enter-from,
.mobile-session-action-menu-leave-to {
  opacity: 0;
  transform: translateY(-4px) scale(0.98);
}
</style>
