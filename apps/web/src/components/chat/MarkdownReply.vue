<script setup lang="ts">
import { computed } from 'vue'
import type { PropType } from 'vue'

const props = defineProps({
  text: { type: String, required: true },
  compact: { type: Boolean, default: false },
  renderMarkdown: { type: Function as PropType<(text: string) => string>, required: true },
})

const renderedHtml = computed(() => props.renderMarkdown(props.text))
</script>

<template>
  <div
    class="markdown-reply"
    :class="{ 'markdown-reply--compact': compact }"
    v-html="renderedHtml"
  ></div>
</template>

<style scoped>
.markdown-reply {
  color: #625b84;
  font-family: var(--soulmeet-font-family);
  font-size: var(--soulmeet-chat-content-font-size);
  line-height: 1.82;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.markdown-reply--compact {
  font-size: var(--soulmeet-chat-content-compact-font-size);
  line-height: 1.78;
}

.markdown-reply :deep(*) {
  max-width: 100%;
  overflow-wrap: anywhere;
}

.markdown-reply :deep(p) {
  margin: 0;
}

.markdown-reply :deep(p + p),
.markdown-reply :deep(p + ul),
.markdown-reply :deep(p + ol),
.markdown-reply :deep(ul + p),
.markdown-reply :deep(ol + p),
.markdown-reply :deep(blockquote + p),
.markdown-reply :deep(pre + p) {
  margin-top: 9px;
}

.markdown-reply :deep(h1),
.markdown-reply :deep(h2),
.markdown-reply :deep(h3),
.markdown-reply :deep(h4) {
  margin: 13px 0 6px;
  color: #514873;
  font-size: 1em;
  font-weight: 700;
  line-height: 1.45;
  letter-spacing: 0;
}

.markdown-reply :deep(h1:first-child),
.markdown-reply :deep(h2:first-child),
.markdown-reply :deep(h3:first-child),
.markdown-reply :deep(h4:first-child) {
  margin-top: 0;
}

.markdown-reply :deep(strong) {
  color: #554493;
  font-weight: 700;
}

.markdown-reply :deep(em) {
  color: #756b9f;
}

.markdown-reply :deep(ul),
.markdown-reply :deep(ol) {
  margin: 8px 0 0;
  padding-left: 1.35em;
}

.markdown-reply :deep(li) {
  margin-top: 4px;
  padding-left: 0.1em;
}

.markdown-reply :deep(li:first-child) {
  margin-top: 0;
}

.markdown-reply :deep(li::marker) {
  color: #9c83e5;
  font-weight: 700;
}

.markdown-reply :deep(blockquote) {
  margin: 10px 0 0;
  border-left: 3px solid rgba(157, 130, 229, 0.56);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.42);
  padding: 8px 11px;
  color: #675f8d;
}

.markdown-reply :deep(code) {
  border: 1px solid rgba(203, 188, 242, 0.62);
  border-radius: 7px;
  background: rgba(247, 242, 255, 0.82);
  padding: 0.1em 0.34em;
  color: #6552a8;
  font-size: 0.92em;
}

.markdown-reply :deep(pre) {
  margin: 10px 0 0;
  overflow-x: auto;
  border: 1px solid rgba(222, 211, 246, 0.78);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.52);
  padding: 10px 12px;
}

.markdown-reply :deep(pre code) {
  border: 0;
  border-radius: 0;
  background: transparent;
  padding: 0;
  color: #554e79;
}

.markdown-reply :deep(a) {
  color: #7058d6;
  font-weight: 650;
  text-decoration: underline;
  text-decoration-color: rgba(112, 88, 214, 0.34);
  text-underline-offset: 3px;
}

.markdown-reply :deep(a:hover) {
  color: #8c65df;
  text-decoration-color: rgba(140, 101, 223, 0.58);
}

.markdown-reply :deep(hr) {
  margin: 12px 0;
  border: 0;
  border-top: 1px solid rgba(211, 200, 236, 0.72);
}

.markdown-reply :deep(table) {
  display: block;
  margin-top: 10px;
  max-width: 100%;
  overflow-x: auto;
  border-collapse: collapse;
}

.markdown-reply :deep(th),
.markdown-reply :deep(td) {
  border: 1px solid rgba(218, 207, 242, 0.78);
  padding: 6px 8px;
  text-align: left;
  vertical-align: top;
}

.markdown-reply :deep(th) {
  background: rgba(248, 244, 255, 0.82);
  color: #554493;
  font-weight: 700;
}
</style>
