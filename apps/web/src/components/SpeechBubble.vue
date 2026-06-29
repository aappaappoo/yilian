<script setup lang="ts">
import { ref, watch, onUnmounted } from 'vue'

const props = defineProps<{ text: string }>()

const visible = ref(false)
let hideTimer: ReturnType<typeof setTimeout> | null = null

function scheduleHide() {
  if (hideTimer !== null) {
    clearTimeout(hideTimer)
  }
  hideTimer = setTimeout(() => {
    visible.value = false
    hideTimer = null
  }, 5000)
}

watch(
  () => props.text,
  (newText) => {
    if (newText) {
      visible.value = true
      scheduleHide()
    } else {
      visible.value = false
      if (hideTimer !== null) {
        clearTimeout(hideTimer)
        hideTimer = null
      }
    }
  },
)

onUnmounted(() => {
  if (hideTimer !== null) {
    clearTimeout(hideTimer)
  }
})
</script>

<template>
  <transition name="speech-bubble-fade">
    <div v-if="visible" class="speech-bubble">
      <p class="speech-bubble__text">{{ text }}</p>
      <!-- Comic-style tail pointing left toward the character -->
      <div class="speech-bubble__tail" />
    </div>
  </transition>
</template>

<style scoped>
.speech-bubble {
  position: relative;
  max-width: 260px;
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(8px);
  border-radius: 18px;
  padding: 12px 16px;
  box-shadow: 0 4px 16px rgba(100, 90, 160, 0.18), 0 1.5px 4px rgba(0,0,0,0.08);
  word-break: break-word;
}

.speech-bubble__text {
  margin: 0;
  font-size: 0.875rem;
  line-height: 1.5;
  color: #4a4a6a;
}

/* Tail pointing left (toward the character on the left) */
.speech-bubble__tail {
  position: absolute;
  left: -10px;
  top: 50%;
  transform: translateY(-50%);
  width: 0;
  height: 0;
  border-top: 9px solid transparent;
  border-bottom: 9px solid transparent;
  border-right: 12px solid rgba(255, 255, 255, 0.88);
  filter: drop-shadow(-3px 2px 3px rgba(100, 90, 160, 0.12));
}

/* Fade transition */
.speech-bubble-fade-enter-active,
.speech-bubble-fade-leave-active {
  transition: opacity 0.4s ease, transform 0.4s ease;
}

.speech-bubble-fade-enter-from,
.speech-bubble-fade-leave-to {
  opacity: 0;
  transform: translateX(8px) scale(0.96);
}
</style>
