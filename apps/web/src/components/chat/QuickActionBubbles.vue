<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { PropType } from 'vue'

const MAX_VISIBLE_ACTIONS = 4
const REFRESH_INTERVAL_MS = 5000

const props = defineProps({
  actions: { type: Array as PropType<string[]>, required: true },
  variant: { type: String as PropType<'desktop' | 'mobile'>, default: 'desktop' },
  disabled: { type: Boolean, default: false },
  visibleLimit: { type: Number, default: MAX_VISIBLE_ACTIONS },
})

const emit = defineEmits<{
  (e: 'select', value: string): void
}>()

const visibleActions = ref<string[]>(props.actions.slice(0, MAX_VISIBLE_ACTIONS))
const pendingActions = ref(new Set<string>())
let refreshTimer: number | null = null
let refillCursor = MAX_VISIBLE_ACTIONS

const isMobile = computed(() => props.variant === 'mobile')
const maxVisibleActions = computed(() => Math.min(
  Math.max(Math.floor(props.visibleLimit || MAX_VISIBLE_ACTIONS), 1),
  MAX_VISIBLE_ACTIONS,
))

watch(
  () => [props.actions, maxVisibleActions.value] as const,
  ([actions, limit]) => {
    visibleActions.value = actions.slice(0, limit)
    pendingActions.value = new Set()
    refillCursor = limit
  },
  { deep: true, immediate: true },
)

function nextActionCandidate(): string | null {
  const pool = props.actions.filter(action => !visibleActions.value.includes(action))
  if (!pool.length) return null

  const action = pool[refillCursor % pool.length]
  refillCursor += 1
  return action
}

function refillVisibleActions() {
  if (visibleActions.value.length >= maxVisibleActions.value) return

  const nextActions = [...visibleActions.value]
  while (nextActions.length < maxVisibleActions.value) {
    visibleActions.value = nextActions
    const candidate = nextActionCandidate()
    if (!candidate || nextActions.includes(candidate)) break
    nextActions.push(candidate)
  }
  visibleActions.value = nextActions.slice(0, maxVisibleActions.value)
}

function selectAction(action: string) {
  if (props.disabled) return
  if (pendingActions.value.has(action)) return
  pendingActions.value = new Set([...pendingActions.value, action])
  visibleActions.value = visibleActions.value.filter(item => item !== action)
  window.setTimeout(() => {
    const nextPending = new Set(pendingActions.value)
    nextPending.delete(action)
    pendingActions.value = nextPending
    emit('select', action)
  }, isMobile.value ? 180 : 240)
}

onMounted(() => {
  refreshTimer = window.setInterval(refillVisibleActions, REFRESH_INTERVAL_MS)
})

onBeforeUnmount(() => {
  if (refreshTimer !== null) {
    window.clearInterval(refreshTimer)
    refreshTimer = null
  }
})
</script>

<template>
  <TransitionGroup
    tag="div"
    name="quick-bubble"
    class="quick-bubbles"
    :class="isMobile ? 'quick-bubbles--mobile' : 'quick-bubbles--desktop'"
  >
    <button
      v-for="(action, index) in visibleActions"
      :key="action"
      type="button"
      class="quick-bubble"
      :class="`quick-bubble--${index + 1}`"
      :disabled="disabled"
      @click="selectAction(action)"
    >
      <span class="quick-bubble__glow"></span>
      <span class="quick-bubble__text">{{ action }}</span>
    </button>
  </TransitionGroup>
</template>

<style scoped>
.quick-bubbles {
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  gap: 14px;
}

.quick-bubbles--desktop {
  flex-wrap: nowrap;
  justify-content: flex-start;
  min-height: 58px;
  overflow: hidden;
  padding: 2px 0 6px;
}

.quick-bubbles--mobile {
  justify-content: flex-start;
  gap: 10px;
  overflow-x: auto;
  padding: 4px 4px 10px;
  scrollbar-width: none;
}

.quick-bubbles--mobile::-webkit-scrollbar {
  display: none;
}

.quick-bubble {
  position: relative;
  isolation: isolate;
  display: inline-flex;
  min-height: 48px;
  max-width: 100%;
  align-items: center;
  justify-content: center;
  overflow: visible;
  border: 1px solid rgba(255, 255, 255, 0.82);
  border-radius: 24px 26px 25px 18px;
  background:
    linear-gradient(145deg, rgba(255, 255, 255, 0.78), rgba(255, 246, 252, 0.62) 56%, rgba(242, 235, 255, 0.58));
  box-shadow:
    0 16px 30px rgba(98, 79, 146, 0.14),
    0 4px 12px rgba(255, 174, 219, 0.12),
    inset 0 1px 0 rgba(255, 255, 255, 0.96),
    inset 0 -10px 18px rgba(238, 226, 255, 0.3);
  color: #574f78;
  cursor: pointer;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.2;
  padding: 12px 18px 13px;
  transform: translateZ(0);
  transition:
    border-color 180ms ease,
    background 180ms ease,
    box-shadow 180ms ease,
    color 180ms ease,
    transform 180ms ease;
  white-space: nowrap;
}

.quick-bubbles--desktop .quick-bubble {
  width: min(168px, 100%);
  flex: 1 1 0;
  min-width: 0;
  max-width: 176px;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.9),
    inset 0 -10px 18px rgba(238, 226, 255, 0.24);
  transform: translateZ(0);
}

.quick-bubbles--mobile .quick-bubble {
  min-height: 42px;
  max-width: 178px;
  flex: 0 0 auto;
  font-size: 12px;
  padding: 10px 13px 11px;
}

.quick-bubble:hover {
  border-color: rgba(255, 255, 255, 0.96);
  background:
    linear-gradient(145deg, rgba(255, 255, 255, 0.9), rgba(255, 241, 250, 0.72) 54%, rgba(236, 228, 255, 0.7));
  box-shadow:
    0 20px 38px rgba(98, 79, 146, 0.2),
    0 6px 16px rgba(255, 174, 219, 0.16),
    inset 0 1px 0 rgba(255, 255, 255, 1),
    inset 0 -10px 18px rgba(238, 226, 255, 0.36);
  color: #4f4777;
  transform: translateY(-4px) rotate(-0.6deg) scale(1.02);
}

.quick-bubble:active {
  transform: translateY(0) scale(0.98);
}

.quick-bubble:disabled {
  cursor: wait;
  opacity: 0.58;
  transform: none;
}

.quick-bubble::before {
  content: "";
  position: absolute;
  left: 18px;
  top: 9px;
  width: 42%;
  height: 12px;
  border-radius: 999px;
  background: linear-gradient(90deg, rgba(255, 255, 255, 0.82), rgba(255, 255, 255, 0));
  pointer-events: none;
}

.quick-bubble::after {
  content: "";
  position: absolute;
  right: 18px;
  bottom: 8px;
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.62);
  box-shadow:
    -14px -22px 0 -4px rgba(255, 255, 255, 0.34),
    0 0 12px rgba(255, 255, 255, 0.48);
  opacity: 0.82;
  z-index: -1;
}

.quick-bubble__glow {
  position: absolute;
  inset: auto auto -16px 14%;
  z-index: -1;
  width: 72%;
  height: 26px;
  border-radius: 999px;
  background: rgba(126, 99, 172, 0.14);
  filter: blur(12px);
  transform: rotate(-5deg);
}

.quick-bubble__text {
  position: relative;
  z-index: 1;
  display: block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: center;
  white-space: nowrap;
}

.quick-bubble--2 {
  border-radius: 25px 18px 26px 24px;
  transform: translateY(10px) rotate(1.2deg);
}

.quick-bubble--2::after {
  right: auto;
  left: 18px;
}

.quick-bubble--3 {
  border-radius: 20px 27px 22px 26px;
  transform: translateY(-4px) rotate(-1deg);
}

.quick-bubble--3::after {
  right: 22px;
}

.quick-bubble--4 {
  border-radius: 27px 23px 18px 25px;
  transform: translateY(8px) rotate(-0.8deg);
}

.quick-bubble--4::after {
  right: auto;
  left: 24px;
}

.quick-bubbles--desktop .quick-bubble--2,
.quick-bubbles--desktop .quick-bubble--3,
.quick-bubbles--desktop .quick-bubble--4 {
  transform: translateZ(0);
}

.quick-bubbles--desktop .quick-bubble::before,
.quick-bubbles--desktop .quick-bubble::after,
.quick-bubbles--desktop .quick-bubble__glow {
  display: none;
}

.quick-bubble--2:hover,
.quick-bubble--3:hover,
.quick-bubble--4:hover {
  transform: translateY(-4px) rotate(-0.6deg) scale(1.02);
}

.quick-bubbles--desktop .quick-bubble:hover,
.quick-bubbles--desktop .quick-bubble--2:hover,
.quick-bubbles--desktop .quick-bubble--3:hover,
.quick-bubbles--desktop .quick-bubble--4:hover {
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.96),
    inset 0 -10px 18px rgba(238, 226, 255, 0.28);
  transform: translateY(-2px);
}

.quick-bubble-move,
.quick-bubble-enter-active,
.quick-bubble-leave-active {
  transition:
    opacity 260ms ease,
    filter 260ms ease,
    transform 260ms cubic-bezier(0.16, 1, 0.3, 1);
}

.quick-bubble-enter-from {
  opacity: 0;
  filter: blur(6px);
  transform: translateY(18px) scale(0.78);
}

.quick-bubble-leave-active {
  position: absolute;
}

.quick-bubble-leave-to {
  opacity: 0;
  filter: blur(8px);
  transform: translateY(-18px) scale(0.62);
}

@media (prefers-reduced-motion: reduce) {
  .quick-bubble,
  .quick-bubble-move,
  .quick-bubble-enter-active,
  .quick-bubble-leave-active {
    transition-duration: 1ms;
  }
}
</style>
