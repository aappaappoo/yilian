<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import type { EmotionState } from '@soulmeet/shared'

export interface EmotionDebugOption {
  label: string
  title: string
  source: string
  icon: string
  state: EmotionState
}

const props = defineProps<{
  options: EmotionDebugOption[]
  currentLabel: string
  boundarySelector?: string
}>()

const emit = defineEmits<{
  (event: 'selectEmotion', option: EmotionDebugOption): void
  (event: 'reset'): void
}>()

const PANEL_POSITION_KEY = 'soulmeet.chat.emotionDebugPanel.position.v1'
const PANEL_COLLAPSED_KEY = 'soulmeet.chat.emotionDebugPanel.collapsed.v1'
const PANEL_WIDTH = 272
const PANEL_HEIGHT = 360
const COLLAPSED_PANEL_WIDTH = 236
const COLLAPSED_PANEL_HEIGHT = 54
const VIEWPORT_PADDING = 12

const panelRef = ref<HTMLElement | null>(null)
const position = ref({ x: 24, y: 96 })
const dragging = ref(false)
const collapsed = ref(false)

let dragOffsetX = 0
let dragOffsetY = 0

const panelStyle = computed(() => ({
  transform: `translate3d(${position.value.x}px, ${position.value.y}px, 0)`,
}))

const currentOption = computed(() => (
  props.options.find(option => option.label === props.currentLabel)
  ?? props.options.find(option => option.label === 'neutral')
  ?? props.options[0]
))

function getDragBoundaryRect(): DOMRect | null {
  if (typeof document === 'undefined' || !props.boundarySelector) return null
  const element = document.querySelector<HTMLElement>(props.boundarySelector)
  const rect = element?.getBoundingClientRect()
  if (!rect || rect.width <= 0 || rect.height <= 0) return null
  return rect
}

function clampToRange(value: number, min: number, max: number): number {
  if (max < min) return min
  return Math.min(Math.max(min, value), max)
}

function clampPosition(x: number, y: number) {
  if (typeof window === 'undefined') return { x, y }

  const rect = panelRef.value?.getBoundingClientRect()
  const boundaryRect = getDragBoundaryRect()
  const fallbackWidth = collapsed.value ? COLLAPSED_PANEL_WIDTH : PANEL_WIDTH
  const fallbackHeight = collapsed.value ? COLLAPSED_PANEL_HEIGHT : PANEL_HEIGHT
  const width = rect?.width || fallbackWidth
  const height = rect?.height || fallbackHeight
  const minX = boundaryRect ? boundaryRect.left + VIEWPORT_PADDING : VIEWPORT_PADDING
  const minY = boundaryRect ? boundaryRect.top + VIEWPORT_PADDING : VIEWPORT_PADDING
  const maxX = boundaryRect
    ? boundaryRect.right - width - VIEWPORT_PADDING
    : window.innerWidth - width - VIEWPORT_PADDING
  const maxY = boundaryRect
    ? boundaryRect.bottom - height - VIEWPORT_PADDING
    : window.innerHeight - height - VIEWPORT_PADDING

  return {
    x: clampToRange(x, minX, maxX),
    y: clampToRange(y, minY, maxY),
  }
}

function savePosition() {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(PANEL_POSITION_KEY, JSON.stringify(position.value))
}

function saveCollapsed() {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(PANEL_COLLAPSED_KEY, JSON.stringify(collapsed.value))
}

function restoreCollapsed() {
  if (typeof window === 'undefined') return

  try {
    const raw = window.localStorage.getItem(PANEL_COLLAPSED_KEY)
    if (raw) {
      collapsed.value = JSON.parse(raw) === true
    }
  } catch (err) {
    console.warn('[EmotionDebugPanel] 恢复折叠状态失败:', err)
  }
}

function restorePosition() {
  if (typeof window === 'undefined') return

  try {
    const raw = window.localStorage.getItem(PANEL_POSITION_KEY)
    if (raw) {
      const saved = JSON.parse(raw) as { x?: number; y?: number }
      if (Number.isFinite(saved.x) && Number.isFinite(saved.y)) {
        position.value = clampPosition(Number(saved.x), Number(saved.y))
        return
      }
    }
  } catch (err) {
    console.warn('[EmotionDebugPanel] 恢复拖拽位置失败:', err)
  }

  const boundaryRect = getDragBoundaryRect()
  position.value = boundaryRect
    ? clampPosition(boundaryRect.right - PANEL_WIDTH - 28, boundaryRect.top + 88)
    : clampPosition(window.innerWidth - PANEL_WIDTH - 28, 88)
}

async function toggleCollapsed() {
  collapsed.value = !collapsed.value
  saveCollapsed()
  await nextTick()
  position.value = clampPosition(position.value.x, position.value.y)
  savePosition()
}

function startDrag(event: PointerEvent) {
  if (event.button !== 0 && event.pointerType === 'mouse') return

  const rect = panelRef.value?.getBoundingClientRect()
  dragOffsetX = event.clientX - (rect?.left ?? position.value.x)
  dragOffsetY = event.clientY - (rect?.top ?? position.value.y)
  dragging.value = true

  window.addEventListener('pointermove', handleDragMove)
  window.addEventListener('pointerup', stopDrag)
  window.addEventListener('pointercancel', stopDrag)
}

function handleDragMove(event: PointerEvent) {
  if (!dragging.value) return
  position.value = clampPosition(event.clientX - dragOffsetX, event.clientY - dragOffsetY)
}

function stopDrag() {
  if (!dragging.value) return

  dragging.value = false
  savePosition()
  window.removeEventListener('pointermove', handleDragMove)
  window.removeEventListener('pointerup', stopDrag)
  window.removeEventListener('pointercancel', stopDrag)
}

function handleResize() {
  position.value = clampPosition(position.value.x, position.value.y)
  savePosition()
}

onMounted(async () => {
  await nextTick()
  restoreCollapsed()
  restorePosition()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  window.removeEventListener('pointermove', handleDragMove)
  window.removeEventListener('pointerup', stopDrag)
  window.removeEventListener('pointercancel', stopDrag)
})
</script>

<template>
  <section
    ref="panelRef"
    class="emotion-debug-panel"
    :class="{ 'is-dragging': dragging, 'is-collapsed': collapsed }"
    :style="panelStyle"
    aria-label="情绪控制面板"
  >
    <header
      class="emotion-debug-panel__header"
      @pointerdown.prevent="startDrag"
    >
      <div class="emotion-debug-panel__title-row">
        <h2>情绪控制</h2>
        <p v-if="collapsed && currentOption" class="emotion-debug-panel__current">
          当前：{{ currentOption.title }}
        </p>
      </div>
      <div class="emotion-debug-panel__actions">
        <button
          v-if="!collapsed"
          class="emotion-debug-panel__reset"
          type="button"
          @pointerdown.stop
          @click.stop="emit('reset')"
        >
          重置
        </button>
        <button
          class="emotion-debug-panel__toggle"
          type="button"
          :aria-label="collapsed ? '展开情绪调试面板' : '折叠情绪调试面板'"
          @pointerdown.stop
          @click.stop="toggleCollapsed"
        >
          <span
            :class="collapsed ? 'i-carbon-chevron-down' : 'i-carbon-chevron-up'"
            aria-hidden="true"
          />
        </button>
      </div>
    </header>

    <div v-if="!collapsed" class="emotion-debug-panel__grid">
      <button
        v-for="option in props.options"
        :key="option.label"
        class="emotion-debug-panel__option"
        :class="{ 'is-active': option.label === props.currentLabel }"
        type="button"
        @click="emit('selectEmotion', option)"
      >
        <span :class="['emotion-debug-panel__icon', option.icon]" aria-hidden="true" />
        <span>
          <strong>{{ option.title }}</strong>
        </span>
      </button>
    </div>
  </section>
</template>

<style scoped lang="scss">
.emotion-debug-panel {
  position: fixed;
  top: 0;
  left: 0;
  z-index: 80;
  width: min(272px, calc(100vw - 24px));
  max-height: calc(100vh - 24px);
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.76);
  border-radius: 24px;
  background:
    radial-gradient(circle at 14% 0%, rgba(255, 220, 238, 0.68), transparent 34%),
    radial-gradient(circle at 92% 4%, rgba(218, 229, 255, 0.58), transparent 32%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.78), rgba(250, 246, 255, 0.58)),
    rgba(251, 250, 255, 0.76);
  box-shadow: 0 18px 48px rgba(105, 86, 150, 0.14), inset 0 1px 0 rgba(255, 255, 255, 0.86);
  backdrop-filter: blur(20px);
  color: #4a4a6a;
  font-family: var(--soulmeet-font-family);
  user-select: none;
}

.emotion-debug-panel.is-dragging {
  cursor: grabbing;
  box-shadow: 0 22px 56px rgba(105, 86, 150, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.9);
}

.emotion-debug-panel.is-collapsed {
  width: min(236px, calc(100vw - 24px));
}

.emotion-debug-panel.is-collapsed .emotion-debug-panel__header {
  padding: 12px 14px;
}

.emotion-debug-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 15px 15px 10px;
  cursor: grab;
  touch-action: none;
}

.emotion-debug-panel__header h2 {
  flex: 0 0 auto;
  margin: 0;
  color: #4a4a6a;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0;
  line-height: 1.35;
  white-space: nowrap;
}

.emotion-debug-panel__title-row {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
}

.emotion-debug-panel__current {
  flex: 1 1 auto;
  margin: 0;
  min-width: 0;
  overflow: hidden;
  color: #8f89b4;
  font-size: 11px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.emotion-debug-panel__actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 6px;
}

.emotion-debug-panel__reset {
  flex: 0 0 auto;
  min-height: 28px;
  border: 1px solid rgba(255, 255, 255, 0.72);
  border-radius: 999px;
  padding: 5px 11px;
  color: #6f6594;
  background: rgba(255, 255, 255, 0.58);
  box-shadow: 0 6px 14px rgba(115, 92, 165, 0.08);
  font-family: inherit;
  font-size: 12px;
  font-weight: 600;
  line-height: 1;
  cursor: pointer;
  transition: background 0.16s ease, color 0.16s ease, border-color 0.16s ease;
}

.emotion-debug-panel__reset:hover,
.emotion-debug-panel__reset:focus-visible {
  border-color: rgba(218, 202, 250, 0.82);
  background: rgba(255, 255, 255, 0.76);
  color: #7d62df;
  outline: none;
}

.emotion-debug-panel__toggle {
  display: grid;
  flex: 0 0 auto;
  width: 30px;
  height: 30px;
  place-items: center;
  border: 1px solid rgba(255, 255, 255, 0.72);
  border-radius: 999px;
  color: #6f6594;
  background: rgba(255, 255, 255, 0.58);
  box-shadow: 0 6px 14px rgba(115, 92, 165, 0.08);
  cursor: pointer;
  transition: background 0.16s ease, color 0.16s ease, border-color 0.16s ease;
}

.emotion-debug-panel__toggle:hover,
.emotion-debug-panel__toggle:focus-visible {
  border-color: rgba(218, 202, 250, 0.82);
  background: rgba(255, 255, 255, 0.76);
  color: #7d62df;
  outline: none;
}

.emotion-debug-panel__toggle span {
  width: 16px;
  height: 16px;
}

.emotion-debug-panel__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  max-height: min(420px, calc(100vh - 104px));
  overflow: auto;
  padding: 1px 12px 14px;
}

.emotion-debug-panel__option {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 8px;
  min-width: 0;
  min-height: 44px;
  border: 1px solid rgba(255, 255, 255, 0.66);
  border-radius: 16px;
  padding: 8px 9px;
  color: #5a5880;
  background: rgba(255, 255, 255, 0.5);
  box-shadow: 0 8px 18px rgba(115, 92, 165, 0.07), inset 0 1px 0 rgba(255, 255, 255, 0.72);
  font-family: inherit;
  text-align: left;
  cursor: pointer;
  transition: transform 0.16s ease, background 0.16s ease, border-color 0.16s ease, box-shadow 0.16s ease;
}

.emotion-debug-panel__option:hover {
  border-color: rgba(222, 210, 250, 0.82);
  background: rgba(255, 255, 255, 0.72);
  transform: translateY(-1px);
}

.emotion-debug-panel__option.is-active {
  border-color: rgba(203, 185, 246, 0.82);
  color: #5f4e9f;
  background:
    radial-gradient(circle at 12% 0%, rgba(255, 224, 241, 0.76), transparent 36%),
    linear-gradient(145deg, rgba(255, 255, 255, 0.84), rgba(241, 235, 255, 0.78));
  box-shadow:
    0 10px 22px rgba(128, 95, 180, 0.13),
    inset 0 1px 0 rgba(255, 255, 255, 0.88);
}

.emotion-debug-panel__icon {
  flex: 0 0 auto;
  width: 18px;
  height: 18px;
  color: #8b7fd4;
}

.emotion-debug-panel__option.is-active .emotion-debug-panel__icon {
  color: #7d62df;
}

.emotion-debug-panel__option strong {
  display: block;
  min-width: 0;
  overflow: hidden;
  color: inherit;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.35;
}

@media (max-width: 640px) {
  .emotion-debug-panel {
    width: min(260px, calc(100vw - 24px));
    border-radius: 22px;
  }

  .emotion-debug-panel__grid {
    grid-template-columns: 1fr;
  }
}
</style>
