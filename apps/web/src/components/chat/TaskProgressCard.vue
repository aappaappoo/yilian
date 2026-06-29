<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import type { PropType } from 'vue'
import { resolveProgressSkillLog } from '../../utils/skillCatalog'
import type { ProgressSkillLogoKind } from '../../utils/skillCatalog'
import type { TaskProgressSnapshot, TaskProgressItem, TaskRunStatus } from '../../composables/useChat'

const props = defineProps({
  data: { type: Object as PropType<TaskProgressSnapshot | null>, default: null },
})

const emit = defineEmits<{
  (e: 'retry', item: TaskProgressItem): void
}>()

const expanded = ref(false)
const detailExpanded = ref(false)
const retryNotice = ref('')
const displayData = ref<TaskProgressSnapshot | null>(null)
const isVisible = ref(false)
const dismissedTerminalTaskKeys = ref<Set<string>>(new Set())
let retryNoticeTimer: ReturnType<typeof setTimeout> | null = null
let hideTimer: ReturnType<typeof setTimeout> | null = null
let clearTimer: ReturnType<typeof setTimeout> | null = null
const terminalTaskTimers = new Map<string, ReturnType<typeof setTimeout>>()

const AUTO_HIDE_DELAY_BY_STATUS: Partial<Record<TaskRunStatus, number>> = {
  success: 5000,
  cancelled: 2200,
}
const TERMINAL_TASK_DISMISS_DELAY = 5000

const snapshotStatus = computed(() => displayData.value?.status ?? 'pending')
const activeItems = computed(() => displayData.value?.tasks.filter(task => isActiveTask(task)) ?? [])
const resultItems = computed(() => displayData.value?.tasks.filter(task => !isActiveTask(task)) ?? [])
const visibleResultItems = computed(() => resultItems.value.filter(task => !dismissedTerminalTaskKeys.value.has(terminalTaskKey(task))))
const allCompleted = computed(() => snapshotStatus.value === 'success')
const hasFailed = computed(() => ['failed', 'partial_success'].includes(snapshotStatus.value) || !!displayData.value?.tasks.some(task => task.status === 'failed'))
const showFailurePanel = computed(() => ['failed', 'partial_success'].includes(snapshotStatus.value))
const allFailed = computed(() => snapshotStatus.value === 'failed')
const partiallyCompleted = computed(() => snapshotStatus.value === 'partial_success')
const cancelled = computed(() => snapshotStatus.value === 'cancelled')
const hasNeedInput = computed(() => !!displayData.value?.tasks.some(task => task.status === 'need_input'))
const firstFailedTask = computed(() => displayData.value?.tasks.find(task => task.status === 'failed') ?? null)
const canRetryFailedTask = computed(() => !!firstFailedTask.value?.retryable && !!firstFailedTask.value?.retryToken)
const primaryTask = computed(() => activeItems.value[0] ?? resultItems.value[0] ?? null)
const taskRowCount = computed(() => visibleResultItems.value.length + activeItems.value.length)
const hasScrollableTaskRows = computed(() => taskRowCount.value > 3)

const totalLabel = computed(() => {
  const count = displayData.value?.taskCount ?? 0
  const completed = displayData.value?.completedCount ?? resultItems.value.length
  const active = displayData.value?.activeCount ?? activeItems.value.length
  if (allCompleted.value) return `任务已完成 · ${count} 个任务`
  if (allFailed.value) return `任务执行失败 · ${count} 个任务`
  if (partiallyCompleted.value) return `部分任务完成 · ${count} 个任务`
  if (cancelled.value) return 'Aini 先停在这里'
  if (hasNeedInput.value) return `等待补充信息 · 已完成 ${completed}/${count} · 待处理 ${active}`
  if (snapshotStatus.value === 'pending') return `任务等待中 · ${count} 个任务`
  return `任务执行中 · 已完成 ${completed}/${count}`
})

const headlineClass = computed(() => {
  if (allFailed.value) return 'text-[#c04f5d]'
  if (partiallyCompleted.value) return 'text-[#bd7a21]'
  if (cancelled.value) return 'text-[#5f5785]'
  return 'text-[#433d73]'
})

const progressClass = computed(() => {
  if (allCompleted.value) return 'bg-gradient-to-r from-[#a7efd7] via-[#b5eadc] to-[#c7b7ff]'
  if (allFailed.value) return 'bg-gradient-to-r from-[#ffc2cb] via-[#f09dac] to-[#d985a0]'
  if (partiallyCompleted.value) return 'bg-gradient-to-r from-[#ffdca4] via-[#ffc4d6] to-[#c9a7ff]'
  if (cancelled.value) return 'bg-gradient-to-r from-[#e7e1f2] to-[#cfc4df]'
  return 'task-progress-card__bar-fill'
})

const primaryTaskIconTone = computed(() => {
  return primaryTask.value ? taskIconTone(primaryTask.value) : 'task-progress-card__icon-shell--default'
})

const primaryTaskLogoKind = computed(() => {
  return primaryTask.value ? taskLogoKind(primaryTask.value) : 'default'
})

const primaryTaskDisplayIcon = computed(() => {
  return primaryTask.value ? taskDisplayIcon(primaryTask.value) : null
})

function shouldShowTaskList(data: TaskProgressSnapshot): boolean {
  if (data.status === 'cancelled') return false
  return data.tasks.length > 1
    || data.status === 'failed'
    || data.status === 'partial_success'
    || data.tasks.some(task => task.status === 'failed' || task.status === 'need_input')
}

watch(() => props.data, async (data) => {
  if (hideTimer !== null) {
    clearTimeout(hideTimer)
    hideTimer = null
  }
  if (clearTimer !== null) {
    clearTimeout(clearTimer)
    clearTimer = null
  }

  if (!data || !data.tasks.length) {
    resetTerminalTaskDismissals()
    isVisible.value = false
    clearTimer = setTimeout(() => {
      displayData.value = null
      resetTerminalTaskDismissals()
      clearTimer = null
    }, 760)
    return
  }

  displayData.value = data
  syncTerminalTaskDismissals(data)
  if (shouldShowTaskList(data)) {
    expanded.value = true
  }
  await nextTick()
  isVisible.value = true

  const autoHideDelay = data.status ? AUTO_HIDE_DELAY_BY_STATUS[data.status] : undefined
  if (autoHideDelay != null) {
    expanded.value = false
    detailExpanded.value = false
    hideTimer = setTimeout(() => {
      isVisible.value = false
      clearTimer = setTimeout(() => {
        displayData.value = null
        resetTerminalTaskDismissals()
        clearTimer = null
      }, 860)
      hideTimer = null
    }, autoHideDelay)
  }
}, { immediate: true, deep: true })

onBeforeUnmount(() => {
  if (retryNoticeTimer !== null) clearTimeout(retryNoticeTimer)
  if (hideTimer !== null) clearTimeout(hideTimer)
  if (clearTimer !== null) clearTimeout(clearTimer)
  resetTerminalTaskDismissals()
})

function itemStyle(item: TaskProgressItem): string {
  if (item.status === 'success') return 'bg-gradient-to-r from-[#9de8d0] to-[#c2b4ff]'
  if (item.status === 'failed') return 'bg-gradient-to-r from-[#ffc0ca] to-[#e78390]'
  if (item.status === 'cancelled') return 'bg-gradient-to-r from-[#d9d3e8] to-[#b8aecf]'
  if (item.status === 'partial_success') return 'bg-gradient-to-r from-[#ffdca4] to-[#c9a7ff]'
  if (item.status === 'pending') return 'bg-[repeating-linear-gradient(90deg,#ece6f9_0_8px,#f5f1fc_8px_16px)]'
  if (item.status === 'queued') return 'bg-[repeating-linear-gradient(90deg,#ece6f9_0_8px,#f5f1fc_8px_16px)]'
  if (item.status === 'need_input') return 'bg-gradient-to-r from-[#ffe6a7] to-[#f5b7ca]'
  return 'task-progress-card__bar-fill'
}

function isActiveTask(item: TaskProgressItem): boolean {
  return ['pending', 'queued', 'running', 'need_input'].includes(item.status)
}

function isTerminalTask(item: TaskProgressItem): boolean {
  return item.status === 'success' || item.status === 'failed'
}

function terminalTaskKey(item: TaskProgressItem): string {
  return `${item.id}:${item.status}`
}

function clearTerminalTaskTimers() {
  terminalTaskTimers.forEach(timer => clearTimeout(timer))
  terminalTaskTimers.clear()
}

function resetTerminalTaskDismissals() {
  clearTerminalTaskTimers()
  dismissedTerminalTaskKeys.value = new Set()
}

function syncTerminalTaskDismissals(data: TaskProgressSnapshot) {
  const currentTerminalKeys = new Set(data.tasks.filter(isTerminalTask).map(terminalTaskKey))

  terminalTaskTimers.forEach((timer, key) => {
    if (!currentTerminalKeys.has(key)) {
      clearTimeout(timer)
      terminalTaskTimers.delete(key)
    }
  })

  const nextDismissedKeys = new Set([...dismissedTerminalTaskKeys.value].filter(key => currentTerminalKeys.has(key)))
  if (nextDismissedKeys.size !== dismissedTerminalTaskKeys.value.size) {
    dismissedTerminalTaskKeys.value = nextDismissedKeys
  }

  data.tasks.filter(isTerminalTask).forEach((task) => {
    const key = terminalTaskKey(task)
    if (dismissedTerminalTaskKeys.value.has(key) || terminalTaskTimers.has(key)) return

    const timer = setTimeout(() => {
      terminalTaskTimers.delete(key)
      const next = new Set(dismissedTerminalTaskKeys.value)
      next.add(key)
      dismissedTerminalTaskKeys.value = next
    }, TERMINAL_TASK_DISMISS_DELAY)

    terminalTaskTimers.set(key, timer)
  })
}

function statusText(status: TaskProgressItem['status']) {
  if (status === 'running') return '进行中'
  if (status === 'success') return '已完成'
  if (status === 'failed') return '失败'
  if (status === 'cancelled') return '已取消'
  if (status === 'partial_success') return '部分完成'
  if (status === 'need_input') return '待补充信息'
  return '待执行'
}

function statusBadgeClass(status: TaskProgressItem['status']): string {
  if (status === 'running') return 'bg-[#f1eaff]/82 text-[#8a63da] ring-1 ring-white/70'
  if (status === 'success') return 'bg-[#e9fbf4]/82 text-[#45a987] ring-1 ring-white/70'
  if (status === 'failed') return 'bg-[#fff0f2]/82 text-[#ca5b66] ring-1 ring-white/70'
  if (status === 'cancelled') return 'bg-[#f0edf7]/82 text-[#7c748e] ring-1 ring-white/70'
  if (status === 'partial_success') return 'bg-[#fff2da]/82 text-[#b66b18] ring-1 ring-white/70'
  if (status === 'need_input') return 'bg-[#fff6d7]/82 text-[#b96b25] ring-1 ring-white/70'
  return 'bg-[#f7f3ff]/82 text-[#9f99bf] ring-1 ring-white/70'
}

function taskActionLabel(item: TaskProgressItem): string {
  return item.actionLabel || statusText(item.status)
}

function taskActionIcon(item: TaskProgressItem): string {
  return item.actionIcon || 'i-carbon-progress-bar'
}

function shouldShowActionBadge(item: TaskProgressItem): boolean {
  if (!item.actionLabel) return false
  if ([
    'planner',
    'intent',
    'validation',
    'verify',
    'entity',
    'tool',
    'retry',
    'rollback',
    'replan',
    'frame',
    'respond',
    'result',
    'waiting',
  ].includes(item.actionTone || ''))
    return true
  return item.actionLabel !== statusText(item.status) && item.actionLabel !== '执行中'
}

function actionBadgeClass(item: TaskProgressItem): string {
  if (item.actionTone === 'planner') return 'bg-[#f3edff]/84 text-[#7658cf] ring-1 ring-white/72'
  if (item.actionTone === 'intent') return 'bg-[#f2ecff]/82 text-[#775bd8] ring-1 ring-white/72'
  if (item.actionTone === 'validation') return 'bg-[#fff4de]/82 text-[#b56c21] ring-1 ring-white/72'
  if (item.actionTone === 'verify') return 'bg-[#edf8ff]/82 text-[#4f82be] ring-1 ring-white/72'
  if (item.actionTone === 'entity') return 'bg-[#eef7ff]/82 text-[#5f83c8] ring-1 ring-white/72'
  if (item.actionTone === 'tool') return 'bg-[#eefbf6]/82 text-[#3f9b78] ring-1 ring-white/72'
  if (item.actionTone === 'retry') return 'bg-[#fff0e3]/86 text-[#c06c29] ring-1 ring-white/72'
  if (item.actionTone === 'rollback') return 'bg-[#f1efff]/86 text-[#705ac8] ring-1 ring-white/72'
  if (item.actionTone === 'replan') return 'bg-[#f4edff]/86 text-[#7a5bd4] ring-1 ring-white/72'
  if (item.actionTone === 'frame') return 'bg-[#eef7ff]/82 text-[#5b76c8] ring-1 ring-white/72'
  if (item.actionTone === 'respond') return 'bg-[#fff0fa]/82 text-[#bd65a0] ring-1 ring-white/72'
  if (item.actionTone === 'result') return 'bg-[#fff0fa]/82 text-[#bd65a0] ring-1 ring-white/72'
  if (item.actionTone === 'waiting') return 'bg-[#fff7d9]/86 text-[#ad7428] ring-1 ring-white/72'
  if (item.actionTone === 'failed') return 'bg-[#fff0f2]/86 text-[#ca5b66] ring-1 ring-white/72'
  if (item.actionTone === 'cancelled') return 'bg-[#f0edf7]/86 text-[#7c748e] ring-1 ring-white/72'
  if (item.actionTone === 'done') return 'bg-[#e9fbf4]/82 text-[#45a987] ring-1 ring-white/72'
  return 'bg-[#f7f3ff]/82 text-[#8175c8] ring-1 ring-white/72'
}

function resultCardClass(item: TaskProgressItem): string {
  if (item.status === 'success') return 'border-[#d9f4ea] bg-[linear-gradient(145deg,rgba(255,255,255,0.72),rgba(233,251,244,0.58))]'
  if (item.status === 'failed') return 'border-[#ffd5d9] bg-[linear-gradient(145deg,rgba(255,255,255,0.72),rgba(255,244,245,0.68))]'
  if (item.status === 'cancelled') return 'border-[#e2ddeb] bg-[linear-gradient(145deg,rgba(255,255,255,0.72),rgba(244,241,249,0.62))]'
  return 'border-[#eadcff] bg-white/52'
}

function resultIconClass(item: TaskProgressItem): string {
  if (item.status === 'success') return 'i-carbon-checkmark-filled text-[#66bfa0]'
  if (item.status === 'failed') return 'i-carbon-warning-alt-filled text-[#d86876]'
  if (item.status === 'cancelled') return 'i-carbon-close-filled text-[#9b91a9]'
  return 'i-carbon-checkmark-outline text-[#8a75d6]'
}

function shouldShowResultIcon(item: TaskProgressItem): boolean {
  return !(item.status === 'success' && taskActionIcon(item) === 'i-carbon-checkmark-filled')
}

function taskIconTone(item: TaskProgressItem): string {
  const logoKind = taskLogoKind(item)
  if (logoKind === 'failed') return 'task-progress-card__icon-shell--failed'
  const toneByLogoKind: Record<ProgressSkillLogoKind, string> = {
    weather: 'task-progress-card__icon-shell--weather',
    train: 'task-progress-card__icon-shell--train',
    hotel: 'task-progress-card__icon-shell--hotel',
    travel: 'task-progress-card__icon-shell--travel',
    food: 'task-progress-card__icon-shell--food',
    flight: 'task-progress-card__icon-shell--flight',
    time: 'task-progress-card__icon-shell--time',
    reminder: 'task-progress-card__icon-shell--reminder',
    default: 'task-progress-card__icon-shell--default',
  }
  return toneByLogoKind[logoKind]
}

function taskLogoKind(item: TaskProgressItem): ProgressSkillLogoKind | 'failed' {
  if (item.status === 'failed') return 'failed'
  return resolveProgressSkillLog({
    rawName: item.name,
    skillName: item.skillName,
    description: item.description,
    icon: item.icon,
    status: item.status,
  }).logoKind
}

function taskDisplayIcon(item: TaskProgressItem): string | null {
  if (item.status === 'failed') return null
  return item.displayIcon || resolveProgressSkillLog({
    rawName: item.name,
    skillName: item.skillName,
    description: item.description,
    icon: item.icon,
    status: item.status,
  }).icon || null
}

function isUtilityIcon(icon: string | null): boolean {
  if (!icon || !icon.startsWith('i-')) return false
  return [...icon].every((char) => {
    const code = char.charCodeAt(0)
    return char === '-' || char === '_' || (code >= 48 && code <= 57) || (code >= 65 && code <= 90) || (code >= 97 && code <= 122)
  })
}

function phaseText(item: TaskProgressItem): string | null {
  if (retryText(item)) return null
  if (item.phaseIndex != null && item.phaseCount != null && item.phaseCount > 0)
    return `${item.phaseIndex}/${item.phaseCount}`
  return null
}

function retryText(item: TaskProgressItem): string | null {
  if (!item.attempt || item.attempt <= 0) return null
  const key = item.phaseKey?.toLowerCase() || ''
  const isRetryPhase = key.includes('retry') || key.includes('recovery')
  if (!isRetryPhase) return `${item.attempt}`
  if (item.phaseCount != null && item.phaseCount > 0) return `${item.attempt}/${item.phaseCount}`
  if (item.retryMaxAttempts != null && item.retryMaxAttempts > 0) return `${item.attempt}/${item.retryMaxAttempts}`
  return `${item.attempt}`
}

function taskHistory(item: TaskProgressItem) {
  return item.history?.filter(entry => entry.phaseLabel || entry.description || entry.phaseKey) ?? []
}

function historyLabel(item: NonNullable<TaskProgressItem['history']>[number]): string {
  return item.phaseLabel || item.description || item.phaseKey || '正在处理当前阶段'
}

function historyBadge(item: NonNullable<TaskProgressItem['history']>[number]): string {
  const parts: string[] = []
  if (item.status) parts.push(statusText(item.status))
  if (item.progress != null) parts.push(`${Math.round(item.progress)}%`)
  if (item.attempt && item.attempt > 0) {
    if (item.phaseCount && item.phaseCount > 0) parts.push(`重试 ${item.attempt}/${item.phaseCount}`)
    else parts.push(`重试 ${item.attempt}`)
  }
  if (item.durationMs != null && item.durationMs > 0) parts.push(formatDuration(item.durationMs))
  return parts.join(' · ')
}

function historyDotClass(item: NonNullable<TaskProgressItem['history']>[number]): string {
  if (item.status === 'success') return 'bg-[#80d8b6]'
  if (item.status === 'failed') return 'bg-[#df7885]'
  if (item.attempt && item.attempt > 0) return 'bg-[#f1a467]'
  if (item.phaseKey?.includes('llm')) return 'bg-[#c49cff]'
  return 'bg-[#b9a5ee]'
}

function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms <= 0) return ''
  if (ms < 1000) return `${Math.round(ms)}ms`
  const seconds = ms / 1000
  if (seconds < 10) return `${seconds.toFixed(1)}s`
  return `${Math.round(seconds)}s`
}

function setRetryNotice(message: string) {
  retryNotice.value = message
  if (retryNoticeTimer !== null) {
    clearTimeout(retryNoticeTimer)
  }
  retryNoticeTimer = setTimeout(() => {
    retryNotice.value = ''
    retryNoticeTimer = null
  }, 1800)
}

function handleRetry() {
  const failedTask = firstFailedTask.value
  if (!failedTask?.retryable || !failedTask.retryToken) {
    setRetryNotice('这次失败不能直接重试，请稍后重新发起。')
    return
  }
  emit('retry', failedTask)
  setRetryNotice(failedTask.retryReason || '正在重新理解需求...')
}
</script>

<template>
  <Transition name="task-progress-card">
    <section v-if="displayData && isVisible" class="task-progress-card relative overflow-hidden rounded-[28px] border border-white/72 bg-[linear-gradient(145deg,rgba(255,255,255,0.72),rgba(255,244,251,0.58)_46%,rgba(242,235,255,0.62))] px-4 py-3 shadow-[0_18px_48px_rgba(135,108,178,0.18),inset_0_1px_0_rgba(255,255,255,0.78)] backdrop-blur-2xl md:px-5">
      <div class="pointer-events-none absolute -top-10 left-10 h-20 w-40 rounded-full bg-[#ffd9ef]/36 blur-2xl"></div>
      <div class="pointer-events-none absolute -right-8 -bottom-12 h-24 w-44 rounded-full bg-[#cbb7ff]/32 blur-2xl"></div>
      <div class="pointer-events-none absolute inset-x-6 top-0 h-px bg-gradient-to-r from-transparent via-white/85 to-transparent"></div>

        <div class="relative flex items-center justify-between gap-3">
          <div class="flex min-w-0 flex-1 items-start gap-3">
            <span class="task-progress-card__icon-shell task-progress-card__icon-shell--large h-10 w-10 shrink-0 text-lg md:h-11 md:w-11 md:text-xl" :class="primaryTaskIconTone">
              <span v-if="primaryTaskDisplayIcon && isUtilityIcon(primaryTaskDisplayIcon)" class="task-progress-card__skill-icon" :class="primaryTaskDisplayIcon" aria-hidden="true"></span>
              <span v-else-if="primaryTaskDisplayIcon" class="task-progress-card__emoji" aria-hidden="true">{{ primaryTaskDisplayIcon }}</span>
              <span v-else class="task-progress-card__logo" :class="`task-progress-card__logo--${primaryTaskLogoKind}`">
                <span></span>
              </span>
            </span>
              <div class="min-w-0 flex-1">
                <div class="flex min-w-0 items-center gap-2">
                  <h3 class="min-w-0 flex-1 truncate text-sm font-semibold tracking-wide md:text-[15px]" :class="headlineClass">{{ totalLabel }}</h3>
                </div>
                <div class="mt-2 flex items-center">
                <div class="relative h-3 flex-1 overflow-hidden rounded-full border border-white/80 bg-[linear-gradient(180deg,rgba(255,255,255,0.86),rgba(239,232,251,0.78))] shadow-[inset_0_1px_1px_rgba(255,255,255,0.95),inset_0_-1px_2px_rgba(151,125,190,0.16)]">
                  <div class="h-full rounded-full shadow-[inset_0_1px_0_rgba(255,255,255,0.7),0_0_14px_rgba(201,167,255,0.42)] transition-all duration-700 ease-out"
                       :class="progressClass"
                       :style="{ width: `${displayData.totalProgress}%` }"></div>
                  <div class="pointer-events-none absolute inset-x-0 top-0 h-1.5 rounded-full bg-white/50"></div>
                </div>
                </div>
              </div>
            </div>
            <button class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-white/75 bg-white/64 text-[#715cc8] shadow-[0_8px_22px_rgba(143,125,255,0.16),inset_0_1px_0_rgba(255,255,255,0.88)] transition-all hover:-translate-y-0.5 hover:bg-white/82 hover:shadow-[0_10px_26px_rgba(143,125,255,0.22)] active:translate-y-0 active:scale-95"
                  :aria-label="expanded ? '收起任务详情' : '展开任务详情'" @click="expanded = !expanded">
            <span class="text-lg leading-none">{{ expanded ? '⌃' : '⌄' }}</span>
          </button>
        </div>

      <div v-if="expanded" class="relative mt-3 space-y-2 rounded-2xl border border-white/72 bg-white/40 p-2.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.72)] md:p-3">
      <div v-if="showFailurePanel" class="rounded-xl border border-[#ffd5d9] bg-[#fff4f5]/70 px-3 py-2.5">
        <div class="flex items-start gap-2">
          <span class="i-carbon-warning-alt-filled mt-0.5 shrink-0 text-lg text-[#d86876]"></span>
          <div class="min-w-0 flex-1">
            <p class="text-xs font-semibold text-[#b94d5e]">失败原因</p>
            <p class="mt-1 text-xs leading-5 text-[#8f6670]">{{ firstFailedTask?.errorReason || '任务执行失败，暂时无法获取详细原因。' }}</p>
            <div class="mt-2 flex flex-wrap gap-2">
              <button
                class="rounded-full border border-[#f0bdc5] bg-white/62 px-3 py-1.5 text-xs font-medium text-[#b94d5e] transition hover:bg-white disabled:cursor-not-allowed disabled:border-[#ead6de] disabled:bg-white/38 disabled:text-[#b9a6af]"
                :disabled="!canRetryFailedTask"
                @click="handleRetry"
              >
                重试
              </button>
              <button class="rounded-full border border-[#ead6de] bg-white/50 px-3 py-1.5 text-xs font-medium text-[#7b6470] transition hover:bg-white" @click="detailExpanded = !detailExpanded">
                {{ detailExpanded ? '收起详情' : '查看详情' }}
              </button>
            </div>
            <div v-if="detailExpanded" class="mt-2 rounded-lg bg-white/58 px-3 py-2 text-[11px] leading-5 text-[#7f7388]">
              <p v-if="firstFailedTask?.failedAt">错误时间：{{ firstFailedTask.failedAt }}</p>
              <p>失败子任务：{{ firstFailedTask?.name || '任务执行' }}</p>
              <p>技术摘要：{{ firstFailedTask?.errorDetail || '暂无可解析的技术摘要' }}</p>
            </div>
            <p v-if="retryNotice" class="mt-2 text-[11px] text-[#9f6570]">{{ retryNotice }}</p>
          </div>
        </div>
      </div>

          <div
            class="task-progress-card__task-scroll space-y-2"
            :class="{ 'task-progress-card__task-scroll--enabled': hasScrollableTaskRows }"
          >
            <TransitionGroup v-if="visibleResultItems.length" name="task-progress-card__task-list" tag="div" class="space-y-2">
              <div
                v-for="item in visibleResultItems"
                :key="`result-${item.id}-${item.status}`"
                class="task-progress-card__task-row rounded-2xl border px-2.5 py-2.5 shadow-[0_8px_18px_rgba(143,125,190,0.08)]"
                :class="[resultCardClass(item), { 'task-progress-card__task-row--terminal': isTerminalTask(item) }]"
              >
                <div class="flex items-start gap-2.5">
                  <span class="task-progress-card__icon-shell mt-0.5 h-7 w-7 shrink-0 text-sm" :class="taskIconTone(item)">
                    <span v-if="isUtilityIcon(taskDisplayIcon(item))" class="task-progress-card__skill-icon task-progress-card__skill-icon--small" :class="taskDisplayIcon(item)" aria-hidden="true"></span>
                    <span v-else-if="taskDisplayIcon(item)" class="task-progress-card__emoji task-progress-card__emoji--small" aria-hidden="true">{{ taskDisplayIcon(item) }}</span>
                    <span v-else class="task-progress-card__logo" :class="`task-progress-card__logo--${taskLogoKind(item)}`">
                      <span></span>
                    </span>
                  </span>
                  <div class="min-w-0 flex-1">
                    <div class="flex items-center justify-between gap-2">
                      <p class="truncate text-[13px] font-semibold text-[#3f3b70]">{{ item.name }}</p>
                      <div class="flex shrink-0 items-center gap-1.5">
                        <span v-if="shouldShowResultIcon(item)" class="text-base" :class="resultIconClass(item)"></span>
                        <span v-if="shouldShowActionBadge(item)" class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium" :class="actionBadgeClass(item)">
                          <span class="text-sm" :class="taskActionIcon(item)" aria-hidden="true"></span>
                          <span>{{ taskActionLabel(item) }}</span>
                        </span>
                        <span class="rounded-full px-2 py-0.5 text-[11px]" :class="statusBadgeClass(item.status)">
                          {{ statusText(item.status) }}
                        </span>
                      </div>
                    </div>
                    <p v-if="item.actionLog" class="mt-1 line-clamp-1 text-[11px] leading-4 text-[#8b82a2]">
                      {{ item.actionLog }}
                    </p>
                    <div v-if="taskHistory(item).length" class="task-progress-card__history mt-2 space-y-1.5">
                      <div v-for="(step, stepIndex) in taskHistory(item)" :key="`${item.id}-result-history-${stepIndex}-${step.phaseKey || 'phase'}`" class="task-progress-card__history-row">
                        <span class="task-progress-card__history-dot" :class="historyDotClass(step)"></span>
                        <p class="min-w-0 flex-1 truncate text-[11px] leading-4 text-[#786f93]">{{ historyLabel(step) }}</p>
                        <span v-if="historyBadge(step)" class="shrink-0 text-[10px] text-[#a096b8]">{{ historyBadge(step) }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </TransitionGroup>

        <div v-for="item in activeItems" :key="item.id" class="task-progress-card__task-row rounded-2xl border border-white/70 bg-white/48 px-2.5 py-2 shadow-[0_8px_18px_rgba(143,125,190,0.08)]">
        <div class="flex items-start gap-2.5">
          <span class="task-progress-card__icon-shell mt-0.5 h-7 w-7 shrink-0 text-sm" :class="taskIconTone(item)">
            <span v-if="isUtilityIcon(taskDisplayIcon(item))" class="task-progress-card__skill-icon task-progress-card__skill-icon--small" :class="taskDisplayIcon(item)" aria-hidden="true"></span>
            <span v-else-if="taskDisplayIcon(item)" class="task-progress-card__emoji task-progress-card__emoji--small" aria-hidden="true">{{ taskDisplayIcon(item) }}</span>
            <span v-else class="task-progress-card__logo" :class="`task-progress-card__logo--${taskLogoKind(item)}`">
              <span></span>
            </span>
          </span>
          <div class="min-w-0 flex-1">
            <div class="flex items-center justify-between gap-2">
              <p class="truncate text-[13px] font-semibold text-[#3f3b70]">{{ item.name }}</p>
              <div class="flex shrink-0 items-center gap-1">
                <!-- 阶段指示器：步骤 X/Y -->
                <span v-if="phaseText(item) && item.status === 'running'" class="rounded-full bg-[#efe9ff] px-1.5 py-0.5 text-[10px] font-medium text-[#7b69cc]">
                  步骤 {{ phaseText(item) }}
                </span>
                <!-- 重试指示器 -->
                <span v-if="retryText(item) && item.status === 'running'" class="rounded-full bg-[#fff3e0] px-1.5 py-0.5 text-[10px] font-medium text-[#e0803a]">
                  重试 {{ retryText(item) }}
                </span>
                <span v-if="shouldShowActionBadge(item)" class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium" :class="actionBadgeClass(item)">
                  <span class="text-sm" :class="taskActionIcon(item)" aria-hidden="true"></span>
                  <span>{{ taskActionLabel(item) }}</span>
                </span>
                <span class="rounded-full px-2 py-0.5 text-[11px]" :class="statusBadgeClass(item.status)">
                  {{ statusText(item.status) }}
                </span>
              </div>
            </div>
            <div class="mt-1.5 flex items-center gap-2">
              <div class="h-1.5 flex-1 overflow-hidden rounded-full bg-white/68 shadow-[inset_0_1px_2px_rgba(121,101,160,0.12)]">
                <div class="h-full rounded-full transition-all duration-700 ease-out" :class="itemStyle(item)" :style="{ width: `${item.progress}%` }"></div>
              </div>
              <span v-if="item.status === 'success'" class="i-carbon-checkmark-filled text-base text-[#66bfa0]"></span>
              <span v-else-if="item.status === 'failed'" class="i-carbon-warning-alt-filled text-base text-[#d86876]"></span>
              <span v-else-if="item.status === 'need_input'" class="i-carbon-warning text-base text-[#b45309]"></span>
              <span v-else-if="item.status === 'cancelled'" class="i-carbon-close-filled text-base text-[#9b91a9]"></span>
              <span v-else class="text-[11px] font-medium text-[#706a9c]">{{ item.progress }}%</span>
            </div>
            <p v-if="item.actionLog" class="mt-1.5 line-clamp-2 text-[11px] leading-4 text-[#81779e]">
              {{ item.actionLog }}
            </p>
            <p v-if="item.status === 'failed'" class="mt-1.5 line-clamp-2 text-[11px] leading-4 text-[#cb5d68]">
              {{ item.errorReason || '任务执行失败，暂时无法获取详细原因。' }}
            </p>
            <div v-if="taskHistory(item).length" class="task-progress-card__history mt-2 space-y-1.5">
              <div v-for="(step, stepIndex) in taskHistory(item)" :key="`${item.id}-active-history-${stepIndex}-${step.phaseKey || 'phase'}`" class="task-progress-card__history-row">
                <span class="task-progress-card__history-dot" :class="historyDotClass(step)"></span>
                <p class="min-w-0 flex-1 truncate text-[11px] leading-4 text-[#786f93]">{{ historyLabel(step) }}</p>
                <span v-if="historyBadge(step)" class="shrink-0 text-[10px] text-[#a096b8]">{{ historyBadge(step) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
        </div>

        <p v-if="hasScrollableTaskRows" class="px-1 text-center text-[11px] text-[#9c92b7]">
          还有 {{ taskRowCount - 3 }} 个子任务，滚动查看
        </p>
    </div>
    </section>
  </Transition>
</template>

<style scoped>
.task-progress-card__bar-fill {
  background-image: linear-gradient(90deg, #f6a9df 0%, #d4a8ff 48%, #9f90f1 100%);
}

.task-progress-card__task-row {
  min-height: 64px;
}

.task-progress-card__task-row--terminal {
  animation: task-progress-card-terminal-fade 5000ms ease forwards;
}

.task-progress-card__history {
  max-height: 148px;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding-right: 2px;
}

.task-progress-card__history-row {
  display: flex;
  min-height: 20px;
  align-items: center;
  gap: 8px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.36);
  padding: 3px 7px;
}

.task-progress-card__history-dot {
  width: 7px;
  height: 7px;
  flex-shrink: 0;
  border-radius: 999px;
  box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.58);
}

.task-progress-card__task-list-move,
.task-progress-card__task-list-leave-active {
  transition:
    opacity 700ms ease,
    transform 700ms cubic-bezier(0.65, 0, 0.35, 1),
    filter 700ms ease;
}

.task-progress-card__task-list-leave-to {
  opacity: 0;
  filter: blur(6px) saturate(0.9);
  transform: translateY(-6px) scale(0.985);
}

@keyframes task-progress-card-terminal-fade {
  0% {
    opacity: 1;
    filter: blur(0) saturate(1);
    transform: translateY(0);
  }

  18% {
    opacity: 1;
  }

  100% {
    opacity: 0;
    filter: blur(5px) saturate(0.9);
    transform: translateY(-6px);
  }
}

.task-progress-card__task-scroll {
  max-height: none;
}

.task-progress-card__task-scroll--enabled {
  max-height: 224px;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding-right: 4px;
  scrollbar-width: thin;
  scrollbar-color: rgba(188, 166, 230, 0.72) rgba(255, 255, 255, 0.28);
}

.task-progress-card__task-scroll--enabled::-webkit-scrollbar {
  width: 6px;
}

.task-progress-card__task-scroll--enabled::-webkit-scrollbar-track {
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.34);
}

.task-progress-card__task-scroll--enabled::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: linear-gradient(180deg, rgba(244, 167, 223, 0.72), rgba(164, 142, 232, 0.72));
}

@media (max-width: 640px) {
  .task-progress-card__task-scroll--enabled {
    max-height: 210px;
  }
}

.task-progress-card__icon-shell {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.76);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.58);
  box-shadow:
    0 9px 20px rgba(117, 98, 170, 0.12),
    inset 0 1px 0 rgba(255, 255, 255, 0.86);
}

.task-progress-card__icon-shell::before {
  content: '';
  position: absolute;
  inset: 3px;
  border-radius: 13px;
  background: linear-gradient(145deg, rgba(255, 255, 255, 0.38), transparent);
  pointer-events: none;
}

.task-progress-card__icon-shell > span {
  position: relative;
  z-index: 1;
}

.task-progress-card__logo {
  position: relative;
  display: block;
  width: 1.42em;
  height: 1.42em;
  color: currentColor;
}

.task-progress-card__emoji {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.1em;
  height: 1.1em;
  font-size: 1.28em;
  line-height: 1;
  filter: drop-shadow(0 2px 4px rgba(112, 89, 162, 0.14));
}

.task-progress-card__emoji--small {
  font-size: 1.18em;
}

.task-progress-card__skill-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.2em;
  height: 1.2em;
  font-size: 1.34em;
  line-height: 1;
  filter: drop-shadow(0 2px 4px rgba(112, 89, 162, 0.14));
}

.task-progress-card__skill-icon--small {
  font-size: 1.18em;
}

.task-progress-card__icon-shell--large .task-progress-card__logo {
  width: 1.5em;
  height: 1.5em;
}

.task-progress-card__logo,
.task-progress-card__logo span,
.task-progress-card__logo::before,
.task-progress-card__logo::after,
.task-progress-card__logo span::before,
.task-progress-card__logo span::after {
  box-sizing: border-box;
}

.task-progress-card__logo span,
.task-progress-card__logo::before,
.task-progress-card__logo::after,
.task-progress-card__logo span::before,
.task-progress-card__logo span::after {
  content: '';
  position: absolute;
  display: block;
}

.task-progress-card__logo--weather span {
  right: 0.04em;
  top: 0.03em;
  width: 0.72em;
  height: 0.72em;
  border-radius: 999px;
  background: #ffd979;
  box-shadow: 0 0 0 0.16em rgba(255, 217, 121, 0.28);
}

.task-progress-card__logo--weather::before {
  left: 0.08em;
  bottom: 0.18em;
  width: 1.08em;
  height: 0.44em;
  border-radius: 999px;
  background: currentColor;
  opacity: 0.9;
}

.task-progress-card__logo--weather::after {
  left: 0.24em;
  bottom: 0.4em;
  width: 0.48em;
  height: 0.48em;
  border-radius: 999px;
  background: currentColor;
  box-shadow: 0.34em 0.08em 0 -0.02em currentColor;
  opacity: 0.9;
}

.task-progress-card__logo--train span {
  inset: 0.14em 0.18em 0.18em;
  border-radius: 0.18em 0.18em 0.26em 0.26em;
  background: currentColor;
}

.task-progress-card__logo--train span::before {
  left: 0.2em;
  right: 0.2em;
  top: 0.18em;
  height: 0.32em;
  border-radius: 0.08em;
  background: rgba(255, 255, 255, 0.78);
  box-shadow: 0 0.48em 0 -0.1em rgba(255, 255, 255, 0.72);
}

.task-progress-card__logo--train span::after {
  left: 0.18em;
  right: 0.18em;
  bottom: -0.22em;
  height: 0.08em;
  border-radius: 999px;
  background: currentColor;
  box-shadow: 0 0.16em 0 rgba(124, 106, 209, 0.28);
}

.task-progress-card__logo--hotel span {
  left: 0.24em;
  bottom: 0.16em;
  width: 0.9em;
  height: 1.08em;
  border-radius: 0.16em;
  background: currentColor;
}

.task-progress-card__logo--hotel span::before {
  left: 0.18em;
  top: 0.2em;
  width: 0.16em;
  height: 0.16em;
  border-radius: 0.04em;
  background: rgba(255, 255, 255, 0.78);
  box-shadow:
    0.34em 0 rgba(255, 255, 255, 0.78),
    0 0.3em rgba(255, 255, 255, 0.78),
    0.34em 0.3em rgba(255, 255, 255, 0.78);
}

.task-progress-card__logo--hotel span::after {
  left: 0.34em;
  bottom: 0;
  width: 0.22em;
  height: 0.32em;
  border-radius: 0.08em 0.08em 0 0;
  background: rgba(255, 255, 255, 0.82);
}

.task-progress-card__logo--travel span {
  left: 0.36em;
  top: 0.12em;
  width: 0.72em;
  height: 0.72em;
  border: 0.18em solid currentColor;
  border-radius: 999px 999px 999px 0;
  transform: rotate(-45deg);
}

.task-progress-card__logo--travel span::before {
  left: 0.09em;
  top: 0.09em;
  width: 0.18em;
  height: 0.18em;
  border-radius: 999px;
  background: currentColor;
}

.task-progress-card__logo--travel::after {
  left: 0.18em;
  right: 0.1em;
  bottom: 0.12em;
  height: 0.12em;
  border-radius: 999px;
  background: currentColor;
  opacity: 0.28;
}

.task-progress-card__logo--food span {
  left: 0.18em;
  bottom: 0.22em;
  width: 0.82em;
  height: 0.64em;
  border: 0.16em solid currentColor;
  border-top: 0;
  border-radius: 0 0 0.3em 0.3em;
}

.task-progress-card__logo--food span::before {
  right: -0.34em;
  top: 0.08em;
  width: 0.34em;
  height: 0.34em;
  border: 0.12em solid currentColor;
  border-left: 0;
  border-radius: 0 999px 999px 0;
}

.task-progress-card__logo--food::before {
  left: 0.3em;
  top: 0.06em;
  width: 0.08em;
  height: 0.42em;
  border-radius: 999px;
  background: currentColor;
  opacity: 0.48;
  box-shadow: 0.26em 0 0 currentColor;
}

.task-progress-card__logo--flight span {
  left: 0.15em;
  top: 0.62em;
  width: 1.16em;
  height: 0.18em;
  border-radius: 999px;
  background: currentColor;
  transform: rotate(-28deg);
}

.task-progress-card__logo--flight span::before {
  left: 0.45em;
  top: -0.36em;
  width: 0.18em;
  height: 0.78em;
  border-radius: 999px;
  background: currentColor;
  transform: rotate(82deg);
}

.task-progress-card__logo--flight span::after {
  right: 0.02em;
  top: -0.18em;
  width: 0.2em;
  height: 0.44em;
  border-radius: 999px;
  background: currentColor;
  transform: rotate(36deg);
}

.task-progress-card__logo--time span {
  left: 0.18em;
  top: 0.28em;
  width: 0.84em;
  height: 0.84em;
  border: 0.13em solid currentColor;
  border-radius: 999px;
  background:
    radial-gradient(circle at 50% 50%, rgba(255, 255, 255, 0.86) 0 0.08em, transparent 0.09em),
    rgba(255, 255, 255, 0.18);
  box-shadow:
    inset 0 0 0 0.05em rgba(255, 255, 255, 0.36),
    0 0 0 0.09em rgba(255, 255, 255, 0.18);
}

.task-progress-card__logo--time span::before {
  left: 0.35em;
  top: 0.14em;
  width: 0.09em;
  height: 0.28em;
  border-radius: 999px;
  background: currentColor;
  transform-origin: 50% 100%;
}

.task-progress-card__logo--time span::after {
  left: 0.39em;
  top: 0.39em;
  width: 0.31em;
  height: 0.08em;
  border-radius: 999px;
  background: currentColor;
  transform: rotate(-32deg);
  transform-origin: 0 50%;
}

.task-progress-card__logo--time::before {
  right: 0.02em;
  top: 0.02em;
  width: 0.5em;
  height: 0.5em;
  border-radius: 999px;
  background: #ffd56f;
  box-shadow:
    0 0 0 0.13em rgba(255, 213, 111, 0.24),
    0 0 0.5em rgba(255, 190, 99, 0.5);
}

.task-progress-card__logo--time::after {
  right: 0.08em;
  top: 0.1em;
  width: 0.72em;
  height: 0.72em;
  border-top: 0.12em solid rgba(255, 198, 106, 0.74);
  border-right: 0.12em solid rgba(255, 198, 106, 0.74);
  border-radius: 0 999px 0 0;
  transform: rotate(-12deg);
}

.task-progress-card__logo--reminder span {
  left: 0.28em;
  top: 0.24em;
  width: 0.88em;
  height: 0.82em;
  border: 0.16em solid currentColor;
  border-radius: 999px 999px 0.24em 0.24em;
  border-bottom-width: 0.22em;
}

.task-progress-card__logo--reminder span::before {
  left: 0.26em;
  bottom: -0.42em;
  width: 0.18em;
  height: 0.18em;
  border-radius: 999px;
  background: currentColor;
}

.task-progress-card__logo--failed span {
  inset: 0.16em;
  border-radius: 999px;
  background: currentColor;
}

.task-progress-card__logo--failed span::before {
  left: 0.5em;
  top: 0.24em;
  width: 0.12em;
  height: 0.48em;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.86);
}

.task-progress-card__logo--failed span::after {
  left: 0.5em;
  bottom: 0.22em;
  width: 0.12em;
  height: 0.12em;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.86);
}

.task-progress-card__logo--default span {
  inset: 0.24em;
  border-radius: 0.24em;
  background: currentColor;
  transform: rotate(45deg);
  box-shadow: 0 0 0 0.12em rgba(255, 255, 255, 0.36);
}

.task-progress-card__icon-shell--weather {
  background:
    radial-gradient(circle at 66% 28%, rgba(255, 220, 137, 0.72), transparent 30%),
    linear-gradient(145deg, rgba(234, 244, 255, 0.82), rgba(245, 236, 255, 0.64));
  color: #6f8fd9;
}

.task-progress-card__icon-shell--train {
  background: linear-gradient(145deg, rgba(238, 233, 255, 0.9), rgba(255, 242, 250, 0.62));
  color: #7c6ad1;
}

.task-progress-card__icon-shell--travel {
  background: linear-gradient(145deg, rgba(237, 248, 255, 0.84), rgba(242, 235, 255, 0.66));
  color: #5f86c7;
}

.task-progress-card__icon-shell--hotel {
  background: linear-gradient(145deg, rgba(255, 239, 248, 0.86), rgba(245, 236, 255, 0.68));
  color: #bf78ad;
}

.task-progress-card__icon-shell--food {
  background: linear-gradient(145deg, rgba(255, 246, 223, 0.9), rgba(255, 235, 247, 0.68));
  color: #c4864d;
}

.task-progress-card__icon-shell--flight {
  background: linear-gradient(145deg, rgba(228, 244, 255, 0.88), rgba(240, 233, 255, 0.66));
  color: #6491d7;
}

.task-progress-card__icon-shell--time {
  background:
    radial-gradient(circle at 72% 20%, rgba(255, 217, 122, 0.78), transparent 26%),
    linear-gradient(145deg, rgba(255, 249, 232, 0.9), rgba(255, 232, 245, 0.7) 48%, rgba(238, 232, 255, 0.68));
  color: #b878d6;
}

.task-progress-card__icon-shell--reminder {
  background: linear-gradient(145deg, rgba(255, 246, 218, 0.86), rgba(246, 236, 255, 0.66));
  color: #b482d2;
}

.task-progress-card__icon-shell--failed {
  background: linear-gradient(145deg, rgba(255, 238, 241, 0.9), rgba(255, 246, 249, 0.68));
  color: #cf6571;
}

.task-progress-card__icon-shell--default {
  background: linear-gradient(145deg, rgba(247, 243, 255, 0.9), rgba(255, 245, 251, 0.64));
  color: #7b69cc;
}

.task-progress-card-enter-active {
  transition:
    opacity 820ms ease,
    transform 820ms cubic-bezier(0.16, 1, 0.3, 1),
    filter 820ms ease;
}

.task-progress-card-leave-active {
  transition:
    opacity 880ms ease,
    transform 880ms cubic-bezier(0.65, 0, 0.35, 1),
    filter 880ms ease;
}

.task-progress-card-enter-from {
  opacity: 0;
  filter: blur(10px) saturate(0.88);
  transform: translateY(14px) scale(0.985);
}

.task-progress-card-enter-to {
  opacity: 1;
  filter: blur(0) saturate(1);
  transform: translateY(0) scale(1);
}

.task-progress-card-leave-from {
  opacity: 1;
  filter: blur(0) saturate(1);
  transform: translateY(0) scale(1);
}

.task-progress-card-leave-to {
  opacity: 0;
  filter: blur(12px) saturate(0.84);
  transform: translateY(10px) scale(0.985);
}
</style>
