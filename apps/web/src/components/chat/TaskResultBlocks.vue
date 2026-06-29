<script setup lang="ts">
import { computed } from 'vue'
import type { PropType } from 'vue'
import HealthMetricCard from './HealthMetricCard.vue'
import MarkdownReply from './MarkdownReply.vue'
import { parseHealthMetricCard } from './healthMetricCard'

interface ResultBlock {
  title: string
  body: string
}

type BlockKind = 'health' | 'failure' | 'markdown'

interface DisplayBlock extends ResultBlock {
  key: string
  kind: BlockKind
  healthData: ReturnType<typeof parseHealthMetricCard>
}

const props = defineProps({
  text: { type: String, required: true },
  artifact: { type: Object as PropType<Record<string, unknown> | null>, default: null },
  renderMarkdown: { type: Function as PropType<(text: string) => string>, required: true },
})

const rawBlocks = computed(() => splitTaskResultBlocks(props.text))
const artifactHealthMetricCard = computed(() => parseHealthMetricCard(props.artifact))
const blocks = computed(() => (
  artifactHealthMetricCard.value
    ? [{ title: '', body: props.text }]
    : rawBlocks.value
))
const displayBlocks = computed(() => blocks.value.map((block, index): DisplayBlock => {
  const signature = `${block.title}\n${block.body}`
  const healthData = artifactHealthMetricCard.value
  const kind = resolveBlockKind(block, {
    signature,
    healthData,
  })

  return {
    ...block,
    key: `${block.title || 'result'}-${index}`,
    kind,
    healthData,
  }
}))

function splitTaskResultBlocks(text: string): ResultBlock[] {
  const source = (text || '').trim()
  if (!source) return []

  const matches = Array.from(source.matchAll(/^【([^】]+)】\s*$/gm))
  if (!matches.length) {
    return [{ title: '', body: source }]
  }

  const result: ResultBlock[] = []
  matches.forEach((match, index) => {
    const title = (match[1] || '').trim()
    const start = (match.index ?? 0) + match[0].length
    const end = matches[index + 1]?.index ?? source.length
    const body = source.slice(start, end).trim()
    if (title || body) {
      result.push({ title, body })
    }
  })
  return result
}

function resolveBlockKind(block: ResultBlock, parsed: {
  signature: string
  healthData: ReturnType<typeof parseHealthMetricCard>
}): BlockKind {
  if (parsed.healthData) return 'health'
  if (/(失败|暂时不可用|稍后再试|无法获取|没能找到|没有找到|抱歉)/.test(parsed.signature)) return 'failure'
  return 'markdown'
}

</script>

<template>
  <div class="task-result-blocks">
    <section
      v-for="block in displayBlocks"
      :key="block.key"
      class="task-result-block"
      :class="`task-result-block--${block.kind}`"
    >
      <div
        v-if="block.kind === 'health' && block.healthData"
        class="task-result-block__health"
      >
        <MarkdownReply
          :text="block.body"
          :render-markdown="renderMarkdown"
          compact
        />
        <HealthMetricCard :data="block.healthData" />
      </div>

      <div v-else class="task-result-block__plain">
        <p v-if="block.title" class="task-result-block__title">{{ block.title }}</p>
        <MarkdownReply
          :text="block.body"
          :render-markdown="renderMarkdown"
          compact
        />
      </div>
    </section>
  </div>
</template>

<style scoped>
.task-result-blocks {
  display: grid;
  gap: 12px;
}

.task-result-block {
  min-width: 0;
}

.task-result-block__plain {
  display: block;
  padding: 0;
}

.task-result-block__health {
  display: grid;
  gap: 12px;
}

.task-result-block__title {
  margin: 0 0 6px;
  color: #514873;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.4;
}

</style>
