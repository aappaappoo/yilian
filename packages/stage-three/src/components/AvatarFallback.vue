<script setup lang="ts">
defineProps<{
  mini?: boolean
}>()
</script>

<template>
  <div class="avatar-fallback" :class="{ 'avatar-fallback--mini': mini }">
    <div class="avatar-fallback__inner">
      <span class="avatar-fallback__emoji">🤖</span>
    </div>
  </div>
</template>

<style scoped>
.avatar-fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  background: transparent;
  border-radius: 0.5rem;
  overflow: hidden;
}

.avatar-fallback--mini {
  width: 64px;
  height: 64px;
  border-radius: 50%;
}

.avatar-fallback__inner {
  animation: breathe 4s ease-in-out infinite;
}

.avatar-fallback__emoji {
  font-size: 3rem;
}

.avatar-fallback--mini .avatar-fallback__emoji {
  font-size: 1.5rem;
}

@keyframes breathe {
  0%, 100% { transform: scale(1.0); }
  50% { transform: scale(1.05); }
}
</style>
