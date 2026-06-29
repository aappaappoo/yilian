<script setup lang="ts">
import { computed } from 'vue'
import type { PropType } from 'vue'
import type { ChatContentBlock } from '../../composables/useChat'
import MarkdownReply from './MarkdownReply.vue'
import type { BotReplyImage } from './botReplyFormatting'
import { formatBotReplyMarkdown } from './botReplyFormatting'

interface MarkdownRenderItem {
  id: string
  kind: 'markdown'
  text: string
  title?: string
  block: ChatContentBlock
}

interface GalleryRenderItem {
  id: string
  kind: 'gallery'
  images: BotReplyImage[]
}

type RenderItem = MarkdownRenderItem | GalleryRenderItem

const MAX_INLINE_IMAGES = 6
const MAX_GALLERY_IMAGES = 3
const MAX_INLINE_GALLERIES = 3

const props = defineProps({
  blocks: { type: Array as PropType<ChatContentBlock[]>, required: true },
  images: { type: Array as PropType<BotReplyImage[]>, default: () => [] },
  renderMarkdown: { type: Function as PropType<(text: string) => string>, required: true },
})

const emit = defineEmits<{
  (event: 'imageError', url: string): void
}>()

const visibleBlocks = computed(() => props.blocks.filter((block) => {
  if (block.text.trim() || block.title) return true
  return Boolean(block.segments?.some(segment => segment.trim()))
}))

const renderItems = computed(() => buildRenderItems(visibleBlocks.value, props.images))

function blockClass(block: ChatContentBlock): string {
  return `content-block-renderer__block--${block.type || 'markdown'}`
}

function blockPlainText(block: ChatContentBlock): string {
  return block.text || block.segments?.join('') || ''
}

function blockMarkdownText(block: ChatContentBlock): string {
  return formatBotReplyMarkdown(blockPlainText(block))
}

function blockSectionText(text: string): string[] {
  const source = formatBotReplyMarkdown(text)
  if (!source.trim()) return []
  const lines = source.split('\n')
  const sections: string[] = []
  let current: string[] = []

  for (const line of lines) {
    if (current.some(item => item.trim()) && isSectionStart(line)) {
      sections.push(current.join('\n').trim())
      current = []
    }
    current.push(line)
  }

  if (current.some(item => item.trim())) {
    sections.push(current.join('\n').trim())
  }
  return sections.filter(Boolean)
}

function isSectionStart(line: string): boolean {
  const trimmed = line.trim()
  if (!trimmed || trimmed.includes('|')) return false
  return /^(?:#{1,6}\s+|[一二三四五六七八九十]+[、.．]\s*\S|(?:Day|DAY)\s*\d|第\s*[一二三四五六七八九十\d]+\s*[天日站]|方案\s*\d|[0-9]+[.、]\s*\S)/.test(trimmed)
}

function normalizeMatchText(text: string): string {
  return text.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, '')
}

function imageMatchScore(sectionText: string, image: BotReplyImage): number {
  const haystack = normalizeMatchText(sectionText)
  if (!haystack) return 0
  const rawTokens = [image.caption, image.alt, image.sourceTitle]
    .filter((value): value is string => Boolean(value))
    .flatMap(value => value.split(/[^\p{L}\p{N}]+/u))
    .map(normalizeMatchText)
    .filter(token => token.length >= 2 && !/^(图片|网页配图|攻略|旅游|旅行|来源)$/.test(token))

  let score = 0
  for (const token of new Set(rawTokens)) {
    if (token.length >= 3 && haystack.includes(token)) score += token.length
    else if (token.length === 2 && haystack.includes(token)) score += 1
  }
  return score
}

function pickGalleryImages(sectionText: string, images: BotReplyImage[], usedUrls: Set<string>): BotReplyImage[] {
  return images
    .filter(image => !usedUrls.has(image.url))
    .map(image => ({ image, score: imageMatchScore(sectionText, image) }))
    .filter(item => item.score >= 3)
    .sort((left, right) => right.score - left.score)
    .slice(0, MAX_GALLERY_IMAGES)
    .map(item => item.image)
}

function buildRenderItems(blocks: ChatContentBlock[], images: BotReplyImage[]): RenderItem[] {
  const inlineImages = images.slice(0, MAX_INLINE_IMAGES)
  const usedUrls = new Set<string>()
  const items: RenderItem[] = []
  let galleryCount = 0
  let fallbackInserted = false

  for (const block of blocks) {
    const sourceText = blockPlainText(block)
    const sections = block.type === 'markdown' || block.type === 'main' || !block.type
      ? blockSectionText(sourceText)
      : [blockMarkdownText(block)]

    for (const [sectionIndex, section] of sections.entries()) {
      const itemId = `${block.id}-section-${sectionIndex}`
      items.push({
        id: itemId,
        kind: 'markdown',
        text: section,
        title: sectionIndex === 0 ? block.title : undefined,
        block,
      })

      if (!inlineImages.length || galleryCount >= MAX_INLINE_GALLERIES) continue
      let galleryImages = pickGalleryImages(section, inlineImages, usedUrls)
      if (!galleryImages.length && !fallbackInserted && section.length >= 48) {
        galleryImages = inlineImages
          .filter(image => !usedUrls.has(image.url))
          .slice(0, Math.min(2, MAX_GALLERY_IMAGES))
        fallbackInserted = galleryImages.length > 0
      }
      if (!galleryImages.length) continue

      for (const image of galleryImages) {
        usedUrls.add(image.url)
      }
      galleryCount += 1
      items.push({
        id: `${itemId}-gallery`,
        kind: 'gallery',
        images: galleryImages,
      })
    }
  }

  return items
}

function handleImageError(url: string) {
  emit('imageError', url)
}
</script>

<template>
  <div class="content-block-renderer">
    <section
      v-for="item in renderItems"
      :key="item.id"
      class="content-block-renderer__block"
      :class="item.kind === 'markdown' ? blockClass(item.block) : 'content-block-renderer__block--image_gallery'"
    >
      <template v-if="item.kind === 'markdown'">
        <p v-if="item.title" class="content-block-renderer__title">{{ item.title }}</p>
        <MarkdownReply
          :text="item.text"
          :render-markdown="renderMarkdown"
        />
      </template>

      <div
        v-else
        class="content-block-renderer__gallery"
        aria-label="正文配图"
      >
        <figure
          v-for="image in item.images"
          :key="image.url"
          class="content-block-renderer__figure"
        >
          <a
            v-if="image.sourceUrl"
            class="content-block-renderer__image-link"
            :href="image.sourceUrl"
            target="_blank"
            rel="noreferrer noopener"
          >
            <img
              class="content-block-renderer__image"
              :src="image.url"
              :alt="image.alt"
              loading="lazy"
              decoding="async"
              referrerpolicy="no-referrer"
              @error="handleImageError(image.url)"
            >
          </a>
          <img
            v-else
            class="content-block-renderer__image"
            :src="image.url"
            :alt="image.alt"
            loading="lazy"
            decoding="async"
            referrerpolicy="no-referrer"
            @error="handleImageError(image.url)"
          >
          <figcaption class="content-block-renderer__caption">{{ image.caption }}</figcaption>
        </figure>
      </div>
    </section>
  </div>
</template>

<style scoped>
.content-block-renderer {
  display: grid;
  gap: 10px;
  min-width: 0;
}

.content-block-renderer__block {
  min-width: 0;
}

.content-block-renderer__title {
  margin: 0 0 5px;
  color: #7a6aa4;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.45;
}

.content-block-renderer__block--tool_status {
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.46);
  padding: 10px 12px;
  box-shadow: inset 0 0 0 1px rgba(214, 196, 238, 0.46);
}

.content-block-renderer__gallery {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(136px, 1fr));
  gap: 9px;
  max-width: min(100%, 560px);
  padding: 1px 0 2px;
}

.content-block-renderer__figure {
  position: relative;
  min-width: 0;
  margin: 0;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.74);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.42);
  box-shadow: 0 10px 24px rgba(132, 112, 190, 0.14);
}

.content-block-renderer__image-link {
  display: block;
  color: inherit;
  text-decoration: none;
}

.content-block-renderer__image {
  display: block;
  width: 100%;
  aspect-ratio: 16 / 10;
  background: rgba(247, 243, 252, 0.76);
  object-fit: cover;
}

.content-block-renderer__caption {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  margin: 0;
  background: linear-gradient(180deg, rgba(42, 36, 58, 0), rgba(42, 36, 58, 0.58));
  padding: 18px 8px 7px;
  color: rgba(255, 255, 255, 0.94);
  font-size: 11px;
  font-weight: 650;
  line-height: 1.25;
  text-shadow: 0 1px 6px rgba(44, 38, 68, 0.34);
}

@media (max-width: 520px) {
  .content-block-renderer__gallery {
    display: flex;
    gap: 8px;
    overflow-x: auto;
    overflow-y: hidden;
    padding-bottom: 6px;
    scroll-snap-type: x proximity;
    -webkit-overflow-scrolling: touch;
  }

  .content-block-renderer__figure {
    flex: 0 0 min(72vw, 210px);
    scroll-snap-align: start;
  }
}
</style>
