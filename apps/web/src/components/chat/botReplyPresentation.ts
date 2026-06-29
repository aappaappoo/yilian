import { parseHealthMetricCard } from './healthMetricCard'
import type { ChatMessage } from '../../composables/useChat'

interface BotReplyPresentationInput {
  text: string
  source?: string
  pending?: ChatMessage['pending']
  artifact?: Record<string, unknown> | null
}

const TASK_REPLY_SOURCES = new Set(['task_result'])
const NON_RESULT_REPLY_SOURCES = new Set(['pre_action_notice'])
const BLOCKING_TASK_STATUSES = new Set([
  'failed',
  'failure',
  'cancelled',
  'canceled',
  'need_input',
  'needs_input',
  'missing_input',
  'paused_need_input',
])

function hasArtifact(artifact?: Record<string, unknown> | null): boolean {
  return !!artifact && Object.keys(artifact).length > 0
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

function normalizedStatus(value: unknown): string {
  return typeof value === 'string' ? value.trim().toLowerCase() : ''
}

function artifactStatus(artifact?: Record<string, unknown> | null): string {
  const root = asRecord(artifact)
  if (!root) return ''
  const result = asRecord(root.result)
  const nestedResult = asRecord(result?.result)
  const draft = asRecord(root.draft)
  return normalizedStatus(root.status)
    || normalizedStatus(result?.status)
    || normalizedStatus(nestedResult?.status)
    || normalizedStatus(draft?.status)
}

function hasBlockingArtifactStatus(artifact?: Record<string, unknown> | null): boolean {
  const status = artifactStatus(artifact)
  return !!status && BLOCKING_TASK_STATUSES.has(status)
}

function hasNonFinalTaskSemantics(text: string): boolean {
  const source = text.trim()
  if (!source) return true
  if (/(请问|还需要|需要你|请补充|补充一下|告诉我|你想|您想|想查|想找).{0,28}(城市|区县|地点|位置|出发|目的地|时间|日期|关键词|预算|人数|区域|找什么)/.test(source)) return true
  if (/(失败|暂时不可用|稍后再试|无法获取|未能获取|查询失败|获取失败|执行失败|没能找到|没有找到|没有搜到|没搜到|无结果|暂时没有完成|抱歉)/.test(source)) return true
  return false
}

export function hasDisplayableTaskCard(input: BotReplyPresentationInput): boolean {
  const text = (input.text || '').trim()
  const artifact = input.artifact
  if (!text && !hasArtifact(artifact)) return false
  if (NON_RESULT_REPLY_SOURCES.has(input.source || '')) return false
  if (input.pending) return false
  if (hasBlockingArtifactStatus(artifact)) return false
  if (text && hasNonFinalTaskSemantics(text)) return false

  return !!parseHealthMetricCard(artifact)
}

export function isTaskReplyPresentation(input: BotReplyPresentationInput): boolean {
  const source = input.source || ''
  const text = (input.text || '').trim()

  if (!text) return false
  if (NON_RESULT_REPLY_SOURCES.has(source)) return false
  if (TASK_REPLY_SOURCES.has(source) || hasArtifact(input.artifact)) {
    return hasDisplayableTaskCard(input)
  }

  if (hasNonFinalTaskSemantics(text)) return false

  return !!parseHealthMetricCard(input.artifact)
}
