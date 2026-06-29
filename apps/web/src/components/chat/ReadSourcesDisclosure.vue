<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { PropType } from 'vue'
import type { BotReplyReference } from './botReplyFormatting'

interface SourceItem extends BotReplyReference {
  host: string
  iconUrl: string
}

const props = defineProps({
  references: { type: Array as PropType<BotReplyReference[]>, required: true },
})

const failedIconUrls = ref<Set<string>>(new Set())
const sourceItems = computed<SourceItem[]>(() => props.references.map(reference => ({
  ...reference,
  host: hostForUrl(reference.url),
  iconUrl: iconUrlForReference(reference),
})))
const previewItems = computed(() => sourceItems.value.slice(0, 4))
const extraCount = computed(() => Math.max(0, sourceItems.value.length - previewItems.value.length))

watch(sourceItems, (items) => {
  const activeUrls = new Set(items.map(item => item.iconUrl).filter(Boolean))
  failedIconUrls.value = new Set([...failedIconUrls.value].filter(url => activeUrls.has(url)))
})

function hostForUrl(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./i, '')
  } catch {
    return ''
  }
}

function iconUrlForReference(reference: BotReplyReference): string {
  if (reference.iconUrl) return reference.iconUrl
  try {
    const host = new URL(reference.url).hostname.toLowerCase()
    return host ? `https://icons.duckduckgo.com/ip3/${host}.ico` : ''
  } catch {
    return ''
  }
}

function shouldShowIcon(item: SourceItem): boolean {
  return Boolean(item.iconUrl && !failedIconUrls.value.has(item.iconUrl))
}

function handleIconError(iconUrl: string) {
  if (!iconUrl) return
  failedIconUrls.value = new Set([...failedIconUrls.value, iconUrl])
}
</script>

<template>
  <details class="read-sources-disclosure">
    <summary class="read-sources-disclosure__summary">
      <span class="read-sources-disclosure__icon i-carbon-search" aria-hidden="true"></span>
      <span class="read-sources-disclosure__label">已阅读 {{ sourceItems.length }} 个网页</span>
      <span class="read-sources-disclosure__preview" aria-hidden="true">
        <span
          v-for="item in previewItems"
          :key="item.url"
          class="read-sources-disclosure__site-icon read-sources-disclosure__site-icon--preview"
        >
          <img
            v-if="shouldShowIcon(item)"
            :src="item.iconUrl"
            alt=""
            loading="lazy"
            decoding="async"
            @error="handleIconError(item.iconUrl)"
          >
          <span v-else class="read-sources-disclosure__site-fallback i-carbon-earth" aria-hidden="true"></span>
        </span>
        <span v-if="extraCount" class="read-sources-disclosure__more">+{{ extraCount }}</span>
      </span>
      <span class="read-sources-disclosure__chevron i-carbon-chevron-down" aria-hidden="true"></span>
    </summary>

    <div class="read-sources-disclosure__panel">
      <a
        v-for="item in sourceItems"
        :key="item.url"
        class="read-sources-disclosure__item"
        :href="item.url"
        target="_blank"
        rel="noreferrer noopener"
      >
        <span class="read-sources-disclosure__site-icon read-sources-disclosure__site-icon--item">
          <img
            v-if="shouldShowIcon(item)"
            :src="item.iconUrl"
            :alt="item.host ? `${item.host} 图标` : '网页图标'"
            loading="lazy"
            decoding="async"
            @error="handleIconError(item.iconUrl)"
          >
          <span v-else class="read-sources-disclosure__site-fallback i-carbon-earth" aria-hidden="true"></span>
        </span>
        <span class="read-sources-disclosure__text">
          <span class="read-sources-disclosure__title">{{ item.label }}</span>
          <span v-if="item.host" class="read-sources-disclosure__host">{{ item.host }}</span>
        </span>
        <span class="read-sources-disclosure__launch i-carbon-launch" aria-hidden="true"></span>
      </a>
    </div>
  </details>
</template>

<style scoped>
.read-sources-disclosure {
  max-width: 100%;
  min-width: 0;
  color: #6b5f91;
}

.read-sources-disclosure__summary {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  min-height: 28px;
  padding: 0;
  cursor: pointer;
  list-style: none;
  user-select: none;
}

.read-sources-disclosure__summary::-webkit-details-marker {
  display: none;
}

.read-sources-disclosure__icon {
  flex: 0 0 auto;
  color: #8f8a9f;
  font-size: 15px;
}

.read-sources-disclosure__label {
  min-width: 0;
  color: #7a728e;
  font-size: 12px;
  font-weight: 650;
  line-height: 1.35;
  white-space: nowrap;
}

.read-sources-disclosure__preview {
  display: flex;
  flex: 1 1 auto;
  align-items: center;
  gap: 4px;
  min-width: 0;
  overflow: hidden;
}

.read-sources-disclosure__more {
  display: inline-grid;
  place-items: center;
  flex: 0 0 auto;
  width: 20px;
  height: 20px;
  border: 1px solid rgba(219, 211, 232, 0.72);
  border-radius: 999px;
  background: rgba(250, 247, 255, 0.78);
  color: #7c6ba4;
  font-size: 8px;
  font-weight: 750;
  line-height: 1;
}

.read-sources-disclosure__site-icon {
  display: inline-grid;
  place-items: center;
  flex: 0 0 auto;
  overflow: hidden;
  border: 1px solid rgba(219, 211, 232, 0.72);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.78);
  box-shadow: 0 4px 12px rgba(128, 103, 158, 0.08);
}

.read-sources-disclosure__site-icon img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.read-sources-disclosure__site-icon--preview {
  width: 20px;
  height: 20px;
}

.read-sources-disclosure__site-icon--item {
  width: 19px;
  height: 19px;
}

.read-sources-disclosure__site-fallback {
  color: #a493b9;
  font-size: 12px;
}

.read-sources-disclosure__more {
  background: rgba(255, 255, 255, 0.52);
  color: #8b7aa8;
}

.read-sources-disclosure__chevron {
  flex: 0 0 auto;
  color: #a993d1;
  font-size: 15px;
  transition: transform 0.18s ease;
}

.read-sources-disclosure[open] .read-sources-disclosure__chevron {
  transform: rotate(180deg);
}

.read-sources-disclosure__panel {
  display: grid;
  gap: 4px;
  padding: 4px 0 2px 24px;
}

.read-sources-disclosure__item {
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr) 16px;
  align-items: center;
  gap: 7px;
  min-width: 0;
  border-radius: 8px;
  padding: 4px 2px;
  color: inherit;
  text-decoration: none;
}

.read-sources-disclosure__item:hover {
  background: rgba(255, 255, 255, 0.38);
}

.read-sources-disclosure__text {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.read-sources-disclosure__title,
.read-sources-disclosure__host {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.read-sources-disclosure__title {
  color: #645b79;
  font-size: 12px;
  font-weight: 650;
  line-height: 1.35;
}

.read-sources-disclosure__host {
  color: #9a93a8;
  font-size: 10px;
  line-height: 1.25;
}

.read-sources-disclosure__launch {
  color: #b19bd5;
  font-size: 14px;
}

@media (max-width: 420px) {
  .read-sources-disclosure__summary {
    gap: 7px;
  }

  .read-sources-disclosure__label {
    font-size: 12px;
  }

  .read-sources-disclosure__site-icon--preview,
  .read-sources-disclosure__more {
    width: 18px;
    height: 18px;
    font-size: 8px;
  }
}
</style>
