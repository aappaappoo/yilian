import { ref } from 'vue'
import type { ServerMessage } from '@soulmeet/shared'
import { resolveProgressSkillLog } from '../utils/skillCatalog'
export type TaskRunStatus = 'pending' | 'queued' | 'running' | 'success' | 'failed' | 'cancelled' | 'partial_success' | 'need_input'

export interface TaskProgressHistoryItem {
  phaseKey?: string
  phaseLabel?: string
  description?: string
  status?: TaskRunStatus
  progress?: number
  phaseIndex?: number
  phaseCount?: number
  attempt?: number
  elapsedMs?: number
  durationMs?: number
}

export interface TaskProgressItem {
  id: string
  name: string
  skillName?: string
  status: TaskRunStatus
  progress: number
  description: string
  resultText?: string
  errorReason?: string
  errorDetail?: string
  failedAt?: string
  icon?: string
  displayIcon?: string
  phaseKey?: string    // 当前阶段唯一标识（后端结构化字段）
  phaseLabel?: string  // 当前阶段描述（后端结构化字段）
  phaseIndex?: number  // 当前阶段序号（1-based）
  phaseCount?: number  // 总阶段数
  attempt?: number     // 重试次数（0=首次，1+=重试）
  actionLabel?: string
  actionLog?: string
  actionIcon?: string
  actionTone?: ProgressActionTone
  retryable?: boolean
  retryToken?: string
  retryReason?: string
  retryAttempt?: number
  retryMaxAttempts?: number
  artifact?: Record<string, unknown>
  history?: TaskProgressHistoryItem[]
}

export interface TaskProgressSnapshot {
  title?: string
  status?: TaskRunStatus
  summary?: string
  taskCount: number
  completedCount?: number
  activeCount?: number
  totalProgress: number
  tasks: TaskProgressItem[]
}

export interface ChatContentBlock {
  id: string
  type: string
  title?: string
  text: string
  segments?: string[]
  source?: string
}

export type ProgressActionTone =
  | 'planner'
  | 'intent'
  | 'validation'
  | 'verify'
  | 'entity'
  | 'tool'
  | 'retry'
  | 'rollback'
  | 'replan'
  | 'frame'
  | 'respond'
  | 'result'
  | 'waiting'
  | 'done'
  | 'failed'
  | 'cancelled'
  | 'running'

interface ProgressActionCopy {
  label: string
  log: string
  icon: string
  tone: ProgressActionTone
}

function normalizedActionText(...parts: Array<string | undefined>): string {
  return parts
    .filter(Boolean)
    .map(part => String(part))
    .join(' ')
    .trim()
    .toLowerCase()
}

const INTERNAL_PROGRESS_ID_PATTERN = /\b(?:task|run|request|ref|call|session|speak|user)[_-]?id\b\s*[:=]\s*['"]?[-\w]{6,}['"]?/gi
const UUID_PATTERN = /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi
const TASK_RUN_STATUSES: TaskRunStatus[] = ['pending', 'queued', 'running', 'success', 'failed', 'cancelled', 'partial_success', 'need_input']

function looksLikeInternalProgressText(text: string): boolean {
  const trimmed = text.trim()
  const lowered = trimmed.toLowerCase()
  if (trimmed.startsWith('{') && trimmed.endsWith('}') && ['request_id', 'run_id', 'task_id', 'frame_trace_decider'].some(key => lowered.includes(key))) {
    return true
  }
  return ['request_id', 'run_id', 'task_id', 'ref_task_id'].some(key => lowered.includes(key))
}

function fallbackProgressText(status: TaskRunStatus): string {
  if (status === 'queued' || status === 'pending') return '已理解你的需求，正在安排下一步。'
  if (status === 'running') return '正在执行当前动作。'
  if (status === 'need_input') return '需要你补充信息后继续。'
  if (status === 'success') return '动作已完成，正在整理回复。'
  if (status === 'failed') return '当前动作执行失败。'
  if (status === 'cancelled') return '当前任务已停止。'
  if (status === 'partial_success') return '部分动作已完成。'
  return 'Aini 正在处理任务。'
}

function sanitizeProgressText(raw: unknown, fallback = ''): string {
  const text = String(raw ?? '').trim()
  if (!text) return fallback
  if (looksLikeInternalProgressText(text)) return fallback
  const cleaned = text
    .replace(INTERNAL_PROGRESS_ID_PATTERN, '')
    .replace(UUID_PATTERN, '')
    .replace(/\s{2,}/g, ' ')
    .replace(/^[\s,，;；]+|[\s,，;；]+$/g, '')
  return cleaned || fallback
}

function normalizeProgressHistory(raw: unknown): TaskProgressHistoryItem[] | undefined {
  if (!Array.isArray(raw)) return undefined
  const history = raw
    .map((entry): TaskProgressHistoryItem | null => {
      if (!entry || typeof entry !== 'object') return null
      const item = entry as Record<string, unknown>
      const rawStatus = String(item.status ?? '').trim() as TaskRunStatus
      const status = TASK_RUN_STATUSES.includes(rawStatus) ? rawStatus : undefined
      const phaseLabel = item.phase_label ? sanitizeProgressText(item.phase_label, '') : undefined
      const description = sanitizeProgressText(item.description ?? '', phaseLabel || '')
      const phaseKey = item.phase_key ? String(item.phase_key) : undefined
      if (!phaseKey && !phaseLabel && !description) return null
      return {
        phaseKey,
        phaseLabel,
        description,
        status,
        progress: item.progress != null ? Math.max(0, Math.min(100, Number(item.progress))) : undefined,
        phaseIndex: item.phase_index != null ? Number(item.phase_index) : undefined,
        phaseCount: item.phase_count != null ? Number(item.phase_count) : undefined,
        attempt: item.attempt != null ? Number(item.attempt) : undefined,
        elapsedMs: item.elapsed_ms != null ? Number(item.elapsed_ms) : undefined,
        durationMs: item.duration_ms != null ? Number(item.duration_ms) : undefined,
      }
    })
    .filter((entry): entry is TaskProgressHistoryItem => entry !== null)
  return history.length ? history : undefined
}

function resolveProgressAction(input: {
  status: TaskRunStatus
  phaseKey?: string
  phaseLabel?: string
  description?: string
  skillName?: string
  attempt?: number
  errorReason?: string
}): ProgressActionCopy {
  const phaseLabel = input.phaseLabel?.trim()
  const fallbackLog = phaseLabel || input.description?.trim() || 'Aini 正在推进当前节点。'
  const signature = normalizedActionText(input.phaseKey, phaseLabel, input.description, input.skillName)

  if (input.status === 'need_input') {
    return {
      label: '等待补充',
      log: input.description?.trim() || '还缺少关键信息，需要你补充后继续。',
      icon: 'i-carbon-help-filled',
      tone: 'waiting',
    }
  }
  if (input.status === 'failed') {
    return {
      label: '执行失败',
      log: input.errorReason || fallbackLog || '当前节点执行失败，已停止推进。',
      icon: 'i-carbon-warning-alt-filled',
      tone: 'failed',
    }
  }
  if (input.status === 'cancelled') {
    return {
      label: '已停止',
      log: 'Aini 已按你的操作停下当前任务。',
      icon: 'i-carbon-pause-filled',
      tone: 'cancelled',
    }
  }
  if (input.status === 'success') {
    return {
      label: '回复完成',
      log: '结果已经整理完成，可以直接查看回复。',
      icon: 'i-carbon-checkmark-filled',
      tone: 'done',
    }
  }
  if (input.status === 'partial_success') {
    return {
      label: '部分完成',
      log: fallbackLog || '部分节点已经完成，剩余节点未能完整返回。',
      icon: 'i-carbon-incomplete',
      tone: 'done',
    }
  }
  if (input.status === 'queued' || input.status === 'pending') {
    return {
      label: '等待调度',
      log: input.description?.trim() || '任务已进入队列，正在等待 Aini 开始处理。',
      icon: 'i-carbon-time',
      tone: 'running',
    }
  }

  if ((input.attempt ?? 0) > 0 || /retry|重试|again/.test(signature)) {
    if (/rollback|回滚|recovery|recover|repair|fallback|降级|修复/.test(signature)) {
      return {
        label: '回滚重试',
        log: phaseLabel || `当前路径不够稳定，正在回退后重新尝试第 ${input.attempt || 1} 次。`,
        icon: 'i-carbon-restart',
        tone: 'rollback',
      }
    }
    return {
      label: '失败重试',
      log: phaseLabel || `上一次请求没有成功，正在进行第 ${input.attempt || 1} 次重试。`,
      icon: 'i-carbon-renew',
      tone: 'retry',
    }
  }

  if (/rollback|回滚|recovery|recover|repair|fallback|降级|修复/.test(signature)) {
    return {
      label: '回滚重试',
      log: phaseLabel || '当前路径不够稳定，正在回退到更稳的处理方式重新尝试。',
      icon: 'i-carbon-restart',
      tone: 'rollback',
    }
  }

  if (/conversation_interpreter|intent|route|router|interpret|understand|match|意图|理解|路由|匹配/.test(signature)) {
    return {
      label: '意图识别',
      log: phaseLabel || '正在理解你的问题，判断该走普通聊天还是任务技能。',
      icon: 'i-carbon-idea',
      tone: 'intent',
    }
  }

  if (/validat|check|guard|governance|permission|preflight|prepare|preparing|参数|校验|检查|权限|安全|准备|补全/.test(signature)) {
    return {
      label: '参数校验',
      log: phaseLabel || '正在校验必要信息，确认参数可以被后续工具正确使用。',
      icon: 'i-carbon-rule',
      tone: 'validation',
    }
  }

  if (/entity|field_extract|field.*extract|extract.*field|extract|resolver|resolve|geocod|地点解析|车站解析|实体|字段抽取|识别地点|确认.*位置|获取地理/.test(signature)) {
    return {
      label: '实体识别',
      log: phaseLabel || '正在识别地点、日期、关键词等信息，用来补全任务参数。',
      icon: 'i-carbon-data-vis-1',
      tone: 'entity',
    }
  }

  if (/polish|synthesis|synthesize|present|compose|summary|summar|parse|parsing|整理|解析|润色|生成回复|汇总/.test(signature)) {
    return {
      label: '结果整理',
      log: phaseLabel || '工具结果已返回，正在整理成适合回复你的内容。',
      icon: 'i-carbon-document-preliminary',
      tone: 'result',
    }
  }

  if (/fetch|search|request|query|tool|provider|http|api|weather|train|ticket|hotel|poi|scenic|availability|schedule|调用|请求|查询|搜索|获取|工具|数据源|车次|景点|住宿|天气/.test(signature)) {
    return {
      label: '调用工具',
      log: phaseLabel || '正在调用外部工具或数据源，等待结果返回。',
      icon: 'i-carbon-tool-kit',
      tone: 'tool',
    }
  }

  return {
    label: '执行中',
    log: fallbackLog,
    icon: 'i-carbon-progress-bar',
    tone: 'running',
  }
}

function toDisplayDescription(status: TaskRunStatus, rawDescription: string, phaseLabel?: string): string {
  // need_input：直接使用后端发来的追问文本作为描述
  if (status === 'need_input') return rawDescription.trim() || '请补充信息后继续'
  // 优先使用后端结构化的阶段描述
  if (phaseLabel) return phaseLabel
  const desc = rawDescription.trim()
  if (desc && !['任务完成', '查询成功', '执行完成', '任务执行中', 'completed', 'done'].includes(desc.toLowerCase())) return desc
  if (status === 'success') return '任务已完成'
  if (status === 'failed') return '任务执行失败'
  if (status === 'cancelled') return '任务已取消'
  if (status === 'partial_success') return '部分任务完成'
  if (status === 'running') return '正在执行中'
  return '等待任务调度'
}

function hasFailureSemantics(text: string): boolean {
  const normalized = text.trim()
  if (!normalized) return false
  return [
    '暂时无法获取',
    '未能获取',
    '无法获取',
    '查询失败',
    '获取失败',
    '执行失败',
    '请稍后再试',
    '功能暂时不可用',
    '没有找到',
    '没能找到',
  ].some(marker => normalized.includes(marker))
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
  contentBlocks?: ChatContentBlock[]
  streamVersion?: number
  source?: string
  streaming?: boolean
  pending?: 'typing' | 'task_creation'
  timestamp: Date
  artifact?: Record<string, unknown>
}

const MAIN_CONTENT_BLOCK_ID = 'main'
const PRE_ACTION_NOTICE_SOURCE = 'pre_action_notice'
const TASK_RESULT_SOURCE = 'task_result'
const ASSISTANT_STREAM_MIN_FLUSH_INTERVAL_MS = 48

export function getChatMessageText(message: Pick<ChatMessage, 'text' | 'contentBlocks'>): string {
  if (message.contentBlocks?.length) {
    return message.contentBlocks
      .map(block => block.text || block.segments?.join('') || '')
      .filter(Boolean)
      .join('\n\n')
      .trim()
  }
  return message.text
}

function generateId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  // 降级方案：兼容不支持 crypto.randomUUID 的旧浏览器
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
}

export function useChat() {
  const messages = ref<ChatMessage[]>([])
  const streamingMessage = ref<ChatMessage | null>(null)
  // Tracks the in-progress user bubble shown while STT partial results stream in
  const partialUserMessage = ref<ChatMessage | null>(null)
  const taskProgress = ref<TaskProgressSnapshot | null>(null)
  const assistantProcessText = ref('')
  const assistantFailedTaskReasons = ref<Record<string, string>>({})
  let assistantBlockDeltaBuffer = new Map<string, string>()
  let assistantStreamFlushFrame: number | null = null
  let assistantStreamFlushTimer: ReturnType<typeof setTimeout> | null = null
  let lastAssistantStreamFlushAt = 0

  function pendingText(kind: ChatMessage['pending']): string {
    if (kind === 'task_creation') return '正在创建任务'
    return '正在准备'
  }

  function clearAssistantStreamFlush() {
    if (assistantStreamFlushFrame !== null && typeof window !== 'undefined') {
      window.cancelAnimationFrame(assistantStreamFlushFrame)
      assistantStreamFlushFrame = null
    }
    if (assistantStreamFlushTimer !== null) {
      clearTimeout(assistantStreamFlushTimer)
      assistantStreamFlushTimer = null
    }
    assistantBlockDeltaBuffer = new Map()
  }

  function clearAssistantProcessText() {
    assistantProcessText.value = ''
  }

  function nowMs(): number {
    return typeof performance !== 'undefined' && typeof performance.now === 'function'
      ? performance.now()
      : Date.now()
  }

  function syncMessageText(message: ChatMessage) {
    message.text = getChatMessageText(message)
  }

  function bumpStreamVersion(message: ChatMessage) {
    message.streamVersion = (message.streamVersion || 0) + 1
  }

  function createAssistantMessage(options: {
    id?: string
    text?: string
    source?: string
    streaming?: boolean
    pending?: ChatMessage['pending']
    artifact?: Record<string, unknown>
    contentBlocks?: ChatContentBlock[]
  } = {}): ChatMessage {
    const newMsg: ChatMessage = {
      id: options.id || generateId(),
      role: 'assistant',
      text: options.text || '',
      source: options.source,
      streaming: options.streaming,
      pending: options.pending,
      timestamp: new Date(),
      artifact: options.artifact,
      contentBlocks: options.contentBlocks,
    }
    if (newMsg.contentBlocks?.length) {
      syncMessageText(newMsg)
    }
    return newMsg
  }

  function ensureStreamingAssistant(messageId?: string, source?: string): ChatMessage {
    const current = streamingMessage.value
    if (current) {
      if (messageId && current.id !== messageId && !current.pending) {
        current.id = messageId
      }
      if (source) current.source = source
      if (current.pending) {
        current.pending = undefined
        current.text = ''
        current.contentBlocks = []
      }
      current.streaming = true
      return current
    }

    const newMsg = createAssistantMessage({
      id: messageId,
      source,
      streaming: true,
      contentBlocks: [],
    })
    messages.value.push(newMsg)
    streamingMessage.value = newMsg
    return newMsg
  }

  function mergeAssistantArtifact(message: ChatMessage, artifact: Record<string, unknown>) {
    message.artifact = {
      ...(message.artifact || {}),
      ...artifact,
    }
  }

  function ensureContentBlock(
    message: ChatMessage,
    blockId = MAIN_CONTENT_BLOCK_ID,
    blockType = 'markdown',
    title?: string,
    source?: string,
  ): ChatContentBlock {
    if (!message.contentBlocks) {
      message.contentBlocks = []
    }
    let block = message.contentBlocks.find(item => item.id === blockId)
    if (!block) {
      block = {
        id: blockId,
        type: blockType || 'markdown',
        title,
        text: '',
        segments: [],
        source,
      }
      message.contentBlocks.push(block)
      return block
    }
    if (blockType) block.type = blockType
    if (title) block.title = title
    if (source) block.source = source
    return block
  }

  function blockBufferKey(messageId: string | undefined, blockId: string): string {
    return `${messageId || ''}\u0000${blockId || MAIN_CONTENT_BLOCK_ID}`
  }

  function parseBlockBufferKey(key: string): { messageId?: string; blockId: string } {
    const [messageId, blockId] = key.split('\u0000')
    return { messageId: messageId || undefined, blockId: blockId || MAIN_CONTENT_BLOCK_ID }
  }

  function flushAssistantStreamBuffer() {
    if (assistantStreamFlushFrame !== null) {
      assistantStreamFlushFrame = null
    }
    if (assistantStreamFlushTimer !== null) {
      clearTimeout(assistantStreamFlushTimer)
      assistantStreamFlushTimer = null
    }
    if (!assistantBlockDeltaBuffer.size) return
    lastAssistantStreamFlushAt = nowMs()

    const pendingDeltas = assistantBlockDeltaBuffer
    assistantBlockDeltaBuffer = new Map()
    for (const [key, text] of pendingDeltas) {
      if (!text) continue
      const { messageId, blockId } = parseBlockBufferKey(key)
      const current = ensureStreamingAssistant(messageId)
      const block = ensureContentBlock(current, blockId)
      if (!block.segments) {
        block.segments = block.text ? [block.text] : []
        block.text = ''
      }
      block.segments.push(text)
      bumpStreamVersion(current)
    }
  }

  function scheduleAssistantStreamFlush() {
    if (assistantStreamFlushFrame !== null || assistantStreamFlushTimer !== null) return
    const elapsed = nowMs() - lastAssistantStreamFlushAt
    const delay = Math.max(0, ASSISTANT_STREAM_MIN_FLUSH_INTERVAL_MS - elapsed)
    assistantStreamFlushTimer = setTimeout(() => {
      assistantStreamFlushTimer = null
      if (typeof window !== 'undefined' && typeof window.requestAnimationFrame === 'function') {
        assistantStreamFlushFrame = window.requestAnimationFrame(flushAssistantStreamBuffer)
        return
      }
      flushAssistantStreamBuffer()
    }, delay)
  }

  function appendAssistantBlockDelta(messageId: string | undefined, blockId: string | undefined, text: string) {
    if (!text) return
    clearAssistantProcessText()
    const key = blockBufferKey(messageId, blockId || MAIN_CONTENT_BLOCK_ID)
    assistantBlockDeltaBuffer.set(key, `${assistantBlockDeltaBuffer.get(key) || ''}${text}`)
    scheduleAssistantStreamFlush()
  }

  function removePendingAssistant(kind?: ChatMessage['pending']) {
    const pending = streamingMessage.value
    if (!pending?.pending) return
    if (kind && pending.pending !== kind) return
    clearAssistantStreamFlush()
    messages.value = messages.value.filter(message => message.id !== pending.id)
    streamingMessage.value = null
  }

  function stopAssistantOutput() {
    clearAssistantStreamFlush()
    clearAssistantProcessText()
    const current = streamingMessage.value
    if (!current) return
    if (current.pending || !getChatMessageText(current).trim()) {
      messages.value = messages.value.filter(message => message.id !== current.id)
    }
    else {
      current.streaming = false
      current.pending = undefined
    }
    streamingMessage.value = null
  }

  function clearTaskProgress() {
    taskProgress.value = null
  }

  function startAssistantPending(kind: NonNullable<ChatMessage['pending']>) {
    clearAssistantProcessText()
    if (streamingMessage.value?.pending) {
      streamingMessage.value.pending = kind
      streamingMessage.value.text = pendingText(kind)
      return
    }
    const newMsg: ChatMessage = {
      id: generateId(),
      role: 'assistant',
      text: pendingText(kind),
      streaming: true,
      pending: kind,
      timestamp: new Date(),
    }
    messages.value.push(newMsg)
    streamingMessage.value = newMsg
  }

  function normalizeStatus(raw: string | undefined): TaskRunStatus {
    const status = (raw || '').toLowerCase()
    if (['pending', 'waiting'].includes(status)) return 'pending'
    if (status === 'queued') return 'queued'
    if (['running', 'in_progress', 'processing'].includes(status)) return 'running'
    if (['success', 'done', 'completed', 'finished'].includes(status)) return 'success'
    if (['cancelled', 'canceled', 'cancel'].includes(status)) return 'cancelled'
    if (['partial_success', 'partial', 'partially_success'].includes(status)) return 'partial_success'
    if (['need_input', 'needs_input', 'missing_input'].includes(status)) return 'need_input'
    return 'failed'
  }

  function isTerminalTaskStatus(status: TaskRunStatus): boolean {
    return ['success', 'failed', 'cancelled', 'partial_success'].includes(status)
  }

  function deriveSnapshotStatus(tasks: TaskProgressItem[], rawStatus?: unknown): TaskRunStatus {
    if (rawStatus) return normalizeStatus(String(rawStatus))
    const hasActive = tasks.some(t => ['queued', 'pending', 'running', 'need_input'].includes(t.status))
    const hasFailed = tasks.some(t => t.status === 'failed')
    const hasSuccess = tasks.some(t => t.status === 'success')
    if (hasActive) return 'running'
    if (hasFailed && hasSuccess) return 'partial_success'
    if (hasFailed) return 'failed'
    if (tasks.length && tasks.every(t => t.status === 'cancelled')) return 'cancelled'
    if (tasks.length && tasks.every(t => t.status === 'success')) return 'success'
    return 'pending'
  }

  function tryUpdateTaskProgress(raw: unknown) {
    if (!raw || typeof raw !== 'object') return
    const payload = raw as Record<string, unknown>
    const list = Array.isArray(payload.tasks) ? payload.tasks : null
    if (!list) return
    const tasks: TaskProgressItem[] = list.map((item, idx) => {
      const task = (item ?? {}) as Record<string, unknown>
      const rawStatus = normalizeStatus(String(task.status ?? 'queued'))
      const id = String(task.id ?? `task-${idx + 1}`)
      const assistantFailureReason = assistantFailedTaskReasons.value[id]
      const phaseKey = task.phase_key ? String(task.phase_key) : undefined
      const fallbackText = fallbackProgressText(rawStatus)
      const phaseLabel = task.phase_label ? sanitizeProgressText(task.phase_label, '') : undefined
      const rawDescription = sanitizeProgressText(task.description ?? task.message ?? '', fallbackText)
      const normalizedStatus = rawStatus
      const status = assistantFailureReason ? 'failed' : normalizedStatus
      const rawName = sanitizeProgressText(task.name ?? task.title ?? '', '')
      const errorReason = assistantFailureReason
        || (task.error_reason ? sanitizeProgressText(task.error_reason, '任务执行失败') : undefined)
      const skillName = task.skill_name ? String(task.skill_name) : undefined
      const icon = assistantFailureReason ? 'i-carbon-warning-alt-filled' : (task.icon ? String(task.icon) : undefined)
      const displayLog = resolveProgressSkillLog({
        rawName,
        skillName,
        description: rawDescription,
        icon,
        status: rawStatus,
      }, idx)
      const actionCopy = resolveProgressAction({
        status,
        phaseKey,
        phaseLabel,
        description: rawDescription,
        skillName,
        attempt: task.attempt != null ? Number(task.attempt) : undefined,
        errorReason,
      })
      return {
        id,
        name: displayLog.title,
        skillName,
        status,
        progress: assistantFailureReason
          ? Math.min(95, Math.max(0, Math.min(100, Number(task.progress ?? 0))))
          : isTerminalTaskStatus(status)
            ? 100
            : Math.max(0, Math.min(100, Number(task.progress ?? 0))),
        description: toDisplayDescription(status, rawDescription, phaseLabel),
        resultText: task.result_text ? String(task.result_text) : undefined,
        errorReason,
        errorDetail: assistantFailureReason ? 'assistant final message indicates task failure' : (task.error_detail ? String(task.error_detail) : undefined),
        failedAt: task.failed_at ? String(task.failed_at) : undefined,
        icon,
        displayIcon: status === 'failed' ? undefined : displayLog.icon,
        phaseKey,
        phaseLabel,
        phaseIndex: task.phase_index != null ? Number(task.phase_index) : undefined,
        phaseCount: task.phase_count != null ? Number(task.phase_count) : undefined,
        attempt: task.attempt != null ? Number(task.attempt) : undefined,
        actionLabel: actionCopy.label,
        actionLog: actionCopy.log,
        actionIcon: actionCopy.icon,
        actionTone: actionCopy.tone,
        retryable: task.retryable === true,
        retryToken: task.retry_token ? String(task.retry_token) : undefined,
        retryReason: task.retry_reason ? String(task.retry_reason) : undefined,
        retryAttempt: task.retry_attempt != null ? Number(task.retry_attempt) : undefined,
        retryMaxAttempts: task.retry_max_attempts != null ? Number(task.retry_max_attempts) : undefined,
        artifact: task.artifact && typeof task.artifact === 'object'
          ? task.artifact as Record<string, unknown>
          : undefined,
        history: normalizeProgressHistory(task.history),
      }
    })
    const explicitTotal = Number(payload.total_progress)
    const computedTotal = tasks.length ? Math.round(tasks.reduce((sum, t) => sum + t.progress, 0) / tasks.length) : 0
    const snapshotStatus = tasks.some(task => task.status === 'failed')
      ? deriveSnapshotStatus(tasks)
      : deriveSnapshotStatus(tasks, payload.status)
    taskProgress.value = {
      title: payload.title ? sanitizeProgressText(payload.title, '') : undefined,
      status: snapshotStatus,
      summary: payload.summary ? sanitizeProgressText(payload.summary, fallbackProgressText(snapshotStatus)) : undefined,
      taskCount: Number(payload.task_count ?? tasks.length),
      completedCount: payload.completed_count != null ? Number(payload.completed_count) : undefined,
      activeCount: payload.active_count != null ? Number(payload.active_count) : undefined,
      totalProgress: Number.isFinite(explicitTotal) ? Math.max(0, Math.min(100, explicitTotal)) : computedTotal,
      tasks,
    }
  }

  function markCurrentTaskFailedFromAssistant(text: string) {
    if (!taskProgress.value || !hasFailureSemantics(text)) return
    const hasFailure = taskProgress.value.tasks.some(task => task.status === 'failed')
    if (hasFailure) return

    const affectedTaskIds = taskProgress.value.tasks
      .filter(task => ['pending', 'queued', 'running', 'success'].includes(task.status))
      .map(task => task.id)
    if (!affectedTaskIds.length) return

    assistantFailedTaskReasons.value = {
      ...assistantFailedTaskReasons.value,
      ...Object.fromEntries(affectedTaskIds.map(id => [id, text])),
    }

    taskProgress.value = {
      ...taskProgress.value,
      status: 'failed',
      summary: '任务执行失败',
      totalProgress: Math.min(taskProgress.value.totalProgress, 95),
      tasks: taskProgress.value.tasks.map((task) => {
        if (!affectedTaskIds.includes(task.id)) return task
        const actionCopy = resolveProgressAction({
          status: 'failed',
          phaseKey: task.phaseKey,
          phaseLabel: task.phaseLabel,
          description: '任务执行失败',
          skillName: task.skillName,
          attempt: task.attempt,
          errorReason: text,
        })
        return {
          ...task,
          status: 'failed',
          progress: Math.min(task.progress, 95),
          description: '任务执行失败',
          errorReason: text,
          errorDetail: 'assistant final message indicates task failure',
          icon: 'i-carbon-warning-alt-filled',
          actionLabel: actionCopy.label,
          actionLog: actionCopy.log,
          actionIcon: actionCopy.icon,
          actionTone: actionCopy.tone,
        }
      }),
    }
  }

  function shouldReplaceStreamingAssistant(msg: ServerMessage): boolean {
    const current = streamingMessage.value
    if (!current) return false
    if (msg.type !== 'assistant_text') return true
    if (msg.source !== TASK_RESULT_SOURCE) return true
    return current.pending === 'task_creation' || current.source === TASK_RESULT_SOURCE
  }

  function findLatestPreActionAssistant(): ChatMessage | null {
    for (let index = messages.value.length - 1; index >= 0; index--) {
      const candidate = messages.value[index]
      if (candidate.role === 'user') return null
      if (candidate.role !== 'assistant') continue
      if (candidate.source === PRE_ACTION_NOTICE_SOURCE) return candidate
      if (candidate.text.trim()) return null
    }
    return null
  }

  function mergeTaskResultWithPreAction(msg: Extract<ServerMessage, { type: 'assistant_text' }>): boolean {
    if (msg.source !== TASK_RESULT_SOURCE) return false
    const preAction = findLatestPreActionAssistant()
    if (!preAction) return false

    const preActionText = preAction.text.trim()
    const resultText = msg.text.trim()
    preAction.text = preActionText && resultText
      ? `${preActionText}\n\n${resultText}`
      : resultText || preActionText
    preAction.contentBlocks = [{
      id: MAIN_CONTENT_BLOCK_ID,
      type: 'markdown',
      text: preAction.text,
      segments: undefined,
      source: msg.source,
    }]
    preAction.source = msg.source
    preAction.artifact = msg.artifact
    preAction.streaming = false
    preAction.pending = undefined
    if (streamingMessage.value?.id === preAction.id) {
      streamingMessage.value = null
    }
    return true
  }

  function finishAssistantMessage(message: ChatMessage, options: {
    text?: string
    source?: string
    artifact?: Record<string, unknown>
  } = {}) {
    const finalText = options.text ?? ''
    if (finalText.trim()) {
      if (!message.contentBlocks?.length) {
        message.contentBlocks = [{
          id: MAIN_CONTENT_BLOCK_ID,
          type: 'markdown',
          text: finalText,
          segments: undefined,
          source: options.source,
        }]
      }
      else if (message.contentBlocks.length === 1) {
        message.contentBlocks[0].text = finalText
        message.contentBlocks[0].segments = undefined
        if (options.source) message.contentBlocks[0].source = options.source
      }
      else {
        for (const block of message.contentBlocks) {
          if (!block.text && block.segments?.length) {
            block.text = block.segments.join('')
          }
          block.segments = undefined
        }
      }
      message.text = finalText
    }
    else {
      for (const block of message.contentBlocks || []) {
        if (!block.text && block.segments?.length) {
          block.text = block.segments.join('')
        }
        block.segments = undefined
      }
      syncMessageText(message)
    }
    for (const block of message.contentBlocks || []) {
      if (!block.text && block.segments?.length) {
        block.text = block.segments.join('')
      }
      block.segments = undefined
    }
    if (options.source) message.source = options.source
    if (options.artifact) message.artifact = options.artifact
    message.streaming = false
    message.pending = undefined
  }

  function mergeFinalAssistantTextWithLatest(msg: Extract<ServerMessage, { type: 'assistant_text' }>): boolean {
    const latest = messages.value[messages.value.length - 1]
    if (!latest || latest.role !== 'assistant') return false
    const latestText = getChatMessageText(latest).trim()
    const finalText = msg.text.trim()
    if (!latestText || latestText !== finalText) return false
    finishAssistantMessage(latest, {
      text: msg.text,
      source: msg.source,
      artifact: msg.artifact,
    })
    return true
  }

  function handleServerMessage(msg: ServerMessage) {
    switch (msg.type) {
      case 'assistant_process':
        assistantProcessText.value = msg.text
        break

      case 'task_progress':
        tryUpdateTaskProgress(msg)
        break

      case 'user_text_partial':
        // Create or update the streaming user bubble with the latest partial text
        if (!partialUserMessage.value) {
          const newMsg: ChatMessage = {
            id: generateId(),
            role: 'user',
            text: msg.text,
            streaming: true,
            timestamp: new Date(),
          }
          messages.value.push(newMsg)
          partialUserMessage.value = newMsg
        }
        else {
          partialUserMessage.value.text = msg.text
        }
        break

      case 'user_text':
        // Finalise an existing partial bubble or push a new message if there was none
        if (partialUserMessage.value) {
          partialUserMessage.value.text = msg.text
          partialUserMessage.value.streaming = false
          partialUserMessage.value = null
        }
        else {
          messages.value.push({
            id: generateId(),
            role: 'user',
            text: msg.text,
            timestamp: new Date(),
          })
        }
        break

      case 'assistant_message_start':
        ensureStreamingAssistant(msg.message_id, msg.source)
        break

      case 'assistant_sources': {
        const current = ensureStreamingAssistant(msg.message_id, msg.source)
        mergeAssistantArtifact(current, { references: msg.references })
        bumpStreamVersion(current)
        break
      }

      case 'content_block_start': {
        const current = ensureStreamingAssistant(msg.message_id, msg.source)
        ensureContentBlock(current, msg.block_id, msg.block_type, msg.title, msg.source)
        bumpStreamVersion(current)
        break
      }

      case 'content_block_delta':
        appendAssistantBlockDelta(msg.message_id, msg.block_id, msg.delta)
        break

      case 'content_block_finish': {
        flushAssistantStreamBuffer()
        const current = streamingMessage.value
        if (current && (!msg.message_id || current.id === msg.message_id)) {
          ensureContentBlock(current, msg.block_id)
          bumpStreamVersion(current)
        }
        break
      }

      case 'assistant_message_finish': {
        clearAssistantProcessText()
        flushAssistantStreamBuffer()
        const current = streamingMessage.value
        if (current && (!msg.message_id || current.id === msg.message_id)) {
          const finalText = msg.text || getChatMessageText(current)
          markCurrentTaskFailedFromAssistant(finalText)
          finishAssistantMessage(current, {
            text: msg.text,
            source: msg.source,
            artifact: msg.artifact,
          })
          streamingMessage.value = null
        }
        break
      }

      case 'assistant_text':
        clearAssistantProcessText()
        if (msg.source === 'interrupted' && !msg.text.trim()) {
          stopAssistantOutput()
          break
        }
        flushAssistantStreamBuffer()
        markCurrentTaskFailedFromAssistant(msg.text)
        // 完整消息 —— 结束流式或直接添加
        const currentStreaming = shouldReplaceStreamingAssistant(msg) ? streamingMessage.value : null
        if (currentStreaming) {
          finishAssistantMessage(currentStreaming, {
            text: msg.text,
            source: msg.source,
            artifact: msg.artifact,
          })
          streamingMessage.value = null
        }
        else {
          if (!mergeFinalAssistantTextWithLatest(msg) && !mergeTaskResultWithPreAction(msg)) {
            messages.value.push(createAssistantMessage({
              text: msg.text,
              source: msg.source,
              artifact: msg.artifact,
              contentBlocks: msg.text.trim()
                ? [{
                    id: MAIN_CONTENT_BLOCK_ID,
                    type: 'markdown',
                    text: msg.text,
                    source: msg.source,
                  }]
                : undefined,
            }))
          }
        }
        break

      case 'assistant_text_interrupted':
        stopAssistantOutput()
        clearTaskProgress()
        clearAssistantProcessText()
        break
    }
  }

  function addUserMessage(text: string) {
    messages.value.push({
      id: generateId(),
      role: 'user',
      text,
      timestamp: new Date(),
    })
  }

  function addLocalUserMessage(text: string) {
    const newMsg: ChatMessage = {
      id: generateId(),
      role: 'user',
      text,
      timestamp: new Date(),
    }
    messages.value.push(newMsg)
    partialUserMessage.value = newMsg
  }

  function clearMessages() {
    clearAssistantStreamFlush()
    clearAssistantProcessText()
    messages.value = []
    streamingMessage.value = null
    partialUserMessage.value = null
  }

  function resetChat() {
    clearAssistantStreamFlush()
    clearAssistantProcessText()
    messages.value = []
    streamingMessage.value = null
    partialUserMessage.value = null
    taskProgress.value = null
    assistantFailedTaskReasons.value = {}
  }

  function replaceMessages(nextMessages: ChatMessage[]) {
    clearAssistantStreamFlush()
    clearAssistantProcessText()
    messages.value = nextMessages
    streamingMessage.value = null
    partialUserMessage.value = null
    taskProgress.value = null
    assistantFailedTaskReasons.value = {}
  }

  return {
    messages,
    streamingMessage,
    partialUserMessage,
    taskProgress,
    assistantProcessText,
    handleServerMessage,
    addUserMessage,
    addLocalUserMessage,
    startAssistantPending,
    clearAssistantPending: removePendingAssistant,
    stopAssistantOutput,
    clearTaskProgress,
    clearMessages,
    resetChat,
    replaceMessages,
  }
}
