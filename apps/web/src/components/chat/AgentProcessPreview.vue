<script setup lang="ts">
import { computed } from 'vue'

const STATUS_MAX_CHARS = 22

const props = defineProps({
  text: { type: String, default: '' },
  fallbackLabel: { type: String, default: '正在准备' },
})

const latestRawText = computed(() => {
  return props.text || props.fallbackLabel
})

const displayText = computed(() => truncateStatus(formatProcessText(latestRawText.value)))

function formatProcessText(raw: string): string {
  const text = raw.trim()
  if (!text) return props.fallbackLabel

  if (/initializing agent/i.test(text)) {
    return '初始化：准备服务'
  }

  const preparing = text.match(/preparing\s+((?:soul|elder)_[a-z_]+)/i)
  if (preparing) {
    return `准备：${toolLabel(preparing[1])}`
  }

  const toolCall = text.match(/^((?:soul|elder)_[a-z_]+)[：:]\s*(.+)$/i)
  if (toolCall) {
    const subject = summarizeToolArguments(toolCall[2])
    return subject ? `${toolAction(toolCall[1])}：${subject}` : `${toolAction(toolCall[1])}：${toolLabel(toolCall[1])}`
  }

  const toolDone = text.match(/^((?:soul|elder)_[a-z_]+)\s*返回(成功|失败)$/i)
  if (toolDone) {
    return toolDone[2] === '失败'
      ? `审核：${toolLabel(toolDone[1])}失败`
      : `正在整理：${toolLabel(toolDone[1])}`
  }

  if (/等待工具选择|直接答复/.test(text)) {
    return '正在思考下一步'
  }

  if (/最终答复|转入最终答复/.test(text)) {
    return '正在整理回复'
  }

  return text
}

function summarizeToolArguments(raw: string): string {
  const preferredKeys = ['destination', 'place', 'city', 'keyword', 'preferences', 'food_keyword', 'origin', 'date', 'days']
  const values = new Map<string, string>()
  for (const part of raw.split(/[；;]/)) {
    const [key, ...valueParts] = part.split('=')
    const value = valueParts.join('=').trim()
    if (!key || !value || !preferredKeys.includes(key.trim())) continue
    values.set(key.trim(), value.replace(/^["']|["']$/g, ''))
  }
  return preferredKeys
    .map(key => values.get(key))
    .filter((value): value is string => !!value)
    .slice(0, 3)
    .join(' ')
}

function toolLabel(name: string): string {
  if (name === 'soul_travel_plan' || name === 'elder_travel_plan') return '旅游攻略'
  if (name === 'weather' || name === 'elder_weather') return '天气'
  if (name === 'train_tickets' || name === 'train_ticket_price' || name === 'elder_train_tickets') return '车票'
  if (name === 'local_search' || name === 'elder_local_search') return '地点'
  return '信息'
}

function toolAction(name: string): string {
  if (name === 'soul_travel_plan' || name === 'elder_travel_plan') return '规划'
  if (name === 'train_tickets' || name === 'train_ticket_price' || name === 'elder_train_tickets') return '查询'
  return '查看'
}

function truncateStatus(text: string): string {
  const chars = Array.from(text.trim())
  if (chars.length <= STATUS_MAX_CHARS) return chars.join('')
  return `${chars.slice(0, STATUS_MAX_CHARS - 3).join('')}...`
}
</script>

<template>
  <Transition name="agent-process-preview" mode="out-in">
    <p :key="displayText" class="agent-process-preview" aria-live="polite">
      {{ displayText }}
    </p>
  </Transition>
</template>

<style scoped>
.agent-process-preview {
  margin: 2px 0 0;
  color: rgba(112, 106, 130, 0.64);
  font-size: 13px;
  font-weight: 500;
  line-height: 1.7;
  letter-spacing: 0;
  overflow-wrap: anywhere;
  animation: agent-process-preview-breathe 1.9s ease-in-out infinite;
}

.agent-process-preview-enter-active,
.agent-process-preview-leave-active {
  transition: opacity 180ms ease, transform 180ms ease;
}

.agent-process-preview-enter-from,
.agent-process-preview-leave-to {
  opacity: 0;
  transform: translateY(2px);
}

@keyframes agent-process-preview-breathe {
  0%,
  100% {
    opacity: 0.46;
  }
  50% {
    opacity: 0.86;
  }
}
</style>
