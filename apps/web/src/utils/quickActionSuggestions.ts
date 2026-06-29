export interface QuickActionMessage {
  role: 'user' | 'assistant'
  text: string
}

export const MAX_QUICK_ACTIONS = 4
export const DEFAULT_QUICK_ACTIONS = [
  '明天适合出门吗？',
  '今天要带伞吗？',
  '附近有什么清淡餐厅？',
  '周末去哪走走不累？',
  '帮我两小时后提醒吃药',
  '附近有室内景点吗？',
  '雨天出门要注意什么？',
  '长护险怎么申请？',
  '福州到厦门有车票吗？',
  '附近哪里适合散步？',
  '明天穿薄外套吗？',
  '午饭吃点什么好？',
  '帮我明早提醒复诊',
  '去厦门玩两天怎么安排？',
  '附近有什么好消化的？',
  '这条消息是真的吗？',
  '明天适合去海边吗？',
  '老人坐动车要注意什么？',
  '附近有什么平价饭店？',
  '帮我记一下买药',
]

const MAX_CONTEXT_MESSAGES = 8
const MAX_CONTEXT_TEXT_CHARS = 700
const MAX_ACTION_CHARS = 18
const BLOCKED_ACTION_PATTERNS = [
  /鞋/,
  /鞋子.*哪/,
  /哪双/,
  /选哪个/,
  /哪个车次/,
  /先去哪/,
  /哪一家/,
  /优先级/,
]

function limitChars(value: string, maxChars: number): string {
  const chars = Array.from(value)
  return chars.length > maxChars ? chars.slice(0, maxChars).join('') : value
}

function shuffledActions(items: string[]): string[] {
  const result = [...items]
  for (let index = result.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(Math.random() * (index + 1))
    const current = result[index]
    result[index] = result[swapIndex]
    result[swapIndex] = current
  }
  return result
}

export function createDefaultQuickActions(limit = MAX_QUICK_ACTIONS): string[] {
  return shuffledActions(DEFAULT_QUICK_ACTIONS).slice(0, limit)
}

function normalizeAction(value: unknown): string {
  const text = limitChars(String(value ?? '')
    .replace(/\s+/g, '')
    .replace(/^[\d一二三四五六七八九十]+[.、)\s-]*/, '')
    .replace(/^["'“”‘’]+|["'“”‘’。!！]+$/g, '')
    .trim(), MAX_ACTION_CHARS)
  if (BLOCKED_ACTION_PATTERNS.some(pattern => pattern.test(text))) return ''
  return text
}

export function buildQuickActionMessages(messages: QuickActionMessage[]): QuickActionMessage[] {
  return messages
    .filter(message => message.text.trim())
    .slice(-MAX_CONTEXT_MESSAGES)
    .map(message => ({
      role: message.role,
      text: limitChars(message.text.trim(), MAX_CONTEXT_TEXT_CHARS),
    }))
}

export function sanitizeQuickActionSuggestions(value: unknown, limit = MAX_QUICK_ACTIONS): string[] {
  if (!Array.isArray(value)) return []
  const actions: string[] = []
  for (const item of value) {
    const normalized = normalizeAction(item)
    if (!normalized || actions.includes(normalized)) continue
    actions.push(normalized)
    if (actions.length >= limit) break
  }
  return actions
}
