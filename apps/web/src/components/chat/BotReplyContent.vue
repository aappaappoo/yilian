<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { PropType } from 'vue'
import type { ChatContentBlock } from '../../composables/useChat'
import ContentBlockRenderer from './ContentBlockRenderer.vue'
import ReadSourcesDisclosure from './ReadSourcesDisclosure.vue'
import TaskResultBlocks from './TaskResultBlocks.vue'
import { isTaskReplyPresentation } from './botReplyPresentation'
import {
  extractBotReplyImages,
  extractBotReplyReferencePresentation,
  extractBotReplyReferencesFromArtifact,
  mergeBotReplyReferences,
} from './botReplyFormatting'

const props = defineProps({
  text: { type: String, required: true },
  contentBlocks: { type: Array as PropType<ChatContentBlock[] | undefined>, default: undefined },
  source: { type: String, default: '' },
  artifact: { type: Object as PropType<Record<string, unknown> | null>, default: null },
  renderMarkdown: { type: Function as PropType<(text: string) => string>, required: true },
})

const referencePresentation = computed(() => extractBotReplyReferencePresentation(props.text))
const artifactReferences = computed(() => extractBotReplyReferencesFromArtifact(props.artifact))
const references = computed(() => mergeBotReplyReferences(
  artifactReferences.value,
  referencePresentation.value.references,
))
const hasContentBlocks = computed(() => Array.isArray(props.contentBlocks) && props.contentBlocks.length > 0)
const fallbackContentBlocks = computed<ChatContentBlock[]>(() => (
  referencePresentation.value.bodyText.trim()
    ? [{
        id: 'main',
        type: 'markdown',
        text: referencePresentation.value.bodyText,
      }]
    : []
))
const isTaskReply = computed(() => isTaskReplyPresentation({
  text: referencePresentation.value.bodyText || props.text,
  source: props.source,
  artifact: props.artifact,
}) && !hasContentBlocks.value)
const images = computed(() => extractBotReplyImages(props.artifact))
const failedImageUrls = ref<Set<string>>(new Set())
const visibleImages = computed(() => images.value.filter(image => !failedImageUrls.value.has(image.url)))

watch(images, (nextImages) => {
  const nextUrls = new Set(nextImages.map(image => image.url))
  failedImageUrls.value = new Set([...failedImageUrls.value].filter(url => nextUrls.has(url)))
})

function handleImageError(url: string) {
  failedImageUrls.value = new Set([...failedImageUrls.value, url])
}
</script>

<template>
  <div class="bot-reply-content">
    <ReadSourcesDisclosure
      v-if="references.length"
      :references="references"
    />

    <ContentBlockRenderer
      v-if="hasContentBlocks"
      :blocks="props.contentBlocks || []"
      :images="visibleImages"
      :render-markdown="renderMarkdown"
      @image-error="handleImageError"
    />

    <TaskResultBlocks
      v-else-if="isTaskReply"
      :text="referencePresentation.bodyText"
      :artifact="props.artifact"
      :render-markdown="renderMarkdown"
    />

    <ContentBlockRenderer
      v-else-if="fallbackContentBlocks.length"
      :blocks="fallbackContentBlocks"
      :images="visibleImages"
      :render-markdown="renderMarkdown"
      @image-error="handleImageError"
    />
  </div>
</template>

<style scoped>
.bot-reply-content {
  display: grid;
  gap: 12px;
  min-width: 0;
}
</style>
