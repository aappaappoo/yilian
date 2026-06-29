<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useSessionStore } from '../stores/session'
import { useEscapeKey } from '../composables/useEscapeKey'

const { t } = useI18n()
const sessionStore = useSessionStore()

const open = defineModel<boolean>('open', { default: false })

function close() {
  open.value = false
}

function handleOverlayClick() {
  close()
}

useEscapeKey(close, {
  enabled: () => open.value,
  priority: 50,
})
</script>

<template>
  <Teleport to="body">
    <!-- 遮罩层 -->
    <Transition name="overlay">
      <div
        v-if="open"
        class="status-overlay fixed inset-0 bg-black/20 z-40"
        role="presentation"
        @click="handleOverlayClick"
      />
    </Transition>

    <!-- 抽屉 -->
    <Transition name="drawer">
      <div
        v-if="open"
        class="status-drawer fixed bottom-0 left-0 right-0 z-50 bg-white rounded-t-2xl shadow-lg max-h-[50vh] overflow-y-auto"
        role="dialog"
        aria-modal="true"
        tabindex="-1"
      >
        <!-- 拖拽指示条 -->
        <div class="flex justify-center pt-2 pb-1">
          <div class="drawer-handle w-10 h-1 bg-gray-300 rounded-full" />
        </div>

        <div class="px-4 pb-4">
          <h2 class="status-title font-semibold text-gray-700 mb-4">
            {{ t('chat.statusPanel') }}
          </h2>

          <!-- 当前节点 -->
          <div class="mb-6">
            <p class="text-xs text-gray-400 mb-1">
              {{ t('chat.currentNode') }}
            </p>
            <p class="status-code text-sm font-mono text-indigo-600 bg-indigo-50 px-2 py-1 rounded">
              {{ sessionStore.currentNode || '—' }}
            </p>
          </div>

          <!-- 情绪状态 -->
          <div class="mb-6">
            <p class="text-xs text-gray-400 mb-2">
              {{ t('chat.emotion.title') }}
            </p>
            <div class="space-y-2">
              <div
                v-for="key in ['sadness', 'anxiety', 'anger'] as const"
                :key="key"
              >
                <div class="flex justify-between text-xs text-gray-600 mb-0.5">
                  <span>{{ t(`chat.emotion.${key}`) }}</span>
                  <span>{{ Math.round(sessionStore.emotionState[key] * 100) }}%</span>
                </div>
                <div class="emotion-track h-1.5 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    class="h-full rounded-full transition-all duration-500"
                    :class="{
                      'bg-blue-400': key === 'sadness',
                      'bg-yellow-400': key === 'anxiety',
                      'bg-red-400': key === 'anger',
                    }"
                    :style="{ width: `${sessionStore.emotionState[key] * 100}%` }"
                  />
                </div>
              </div>
            </div>
            <div v-if="sessionStore.emotionState.label" class="mt-2">
              <p class="text-xs text-gray-400">
                {{ t('chat.emotion.label') }}：
                <span class="text-gray-600">{{ sessionStore.emotionState.label }}</span>
              </p>
            </div>
            <div v-if="sessionStore.emotionState.keywords.length" class="mt-2 flex flex-wrap gap-1">
              <span
                v-for="kw in sessionStore.emotionState.keywords"
                :key="kw"
                class="status-keyword text-xs bg-purple-50 text-purple-600 px-2 py-0.5 rounded-full"
              >
                {{ kw }}
              </span>
            </div>
          </div>

          <!-- 可用工具 -->
          <div v-if="sessionStore.availableTools.length">
            <p class="text-xs text-gray-400 mb-2">
              {{ t('chat.tools') }}
            </p>
            <div class="space-y-1">
              <div
                v-for="tool in sessionStore.availableTools"
                :key="tool"
                class="tool-chip text-xs font-mono text-gray-600 bg-gray-50 px-2 py-1 rounded"
              >
                {{ tool }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped lang="scss">
.status-overlay {
  font-family: var(--soulmeet-font-family);
  background:
    radial-gradient(circle at 18% 8%, rgba(255, 215, 234, 0.28), transparent 34%),
    radial-gradient(circle at 82% 0%, rgba(221, 235, 255, 0.28), transparent 36%),
    rgba(30, 24, 48, 0.24);
  backdrop-filter: blur(3px);
}

.status-drawer {
  border-radius: 30px 30px 0 0;
  border: 1px solid rgba(255, 255, 255, 0.78);
  background:
    radial-gradient(circle at 12% 0%, rgba(255, 215, 234, 0.76), transparent 32%),
    radial-gradient(circle at 92% 0%, rgba(221, 235, 255, 0.72), transparent 34%),
    linear-gradient(135deg, rgba(255, 255, 255, 0.88), rgba(255, 247, 253, 0.72));
  box-shadow: 0 -22px 70px rgba(74, 55, 118, 0.22), inset 0 1px 0 rgba(255, 255, 255, 0.86);
  color: #3f365c;

  :deep(button),
  :deep(input) {
    font-family: inherit;
  }
}

.drawer-handle {
  background: #d8ccef;
}

.status-title {
  color: #4c3b7c;
  font-size: 18px;
}

.status-code,
.tool-chip,
.status-keyword {
  border: 1px solid rgba(220, 204, 255, 0.58);
  background: rgba(255, 255, 255, 0.58);
  color: #6f58c5;
}

.emotion-track {
  background: rgba(255, 255, 255, 0.68);
}

.overlay-enter-active,
.overlay-leave-active {
  transition: opacity 0.3s ease;
}
.overlay-enter-from,
.overlay-leave-to {
  opacity: 0;
}

.drawer-enter-active,
.drawer-leave-active {
  transition: transform 0.3s ease;
}
.drawer-enter-from,
.drawer-leave-to {
  transform: translateY(100%);
}
</style>
