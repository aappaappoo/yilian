<script setup lang="ts">
import type { SkillBundle } from './types'

defineProps<{
  bundle: SkillBundle
}>()

const emit = defineEmits<{
  (e: 'action', bundle: SkillBundle): void
}>()
</script>

<template>
  <article class="skill-bundle-card relative overflow-hidden rounded-[22px] border border-white/65 bg-white/58 p-3 shadow-[0_12px_32px_rgba(124,102,180,0.12)] backdrop-blur-xl">
    <div class="absolute inset-0 bg-[linear-gradient(135deg,rgba(255,236,247,0.72),rgba(239,232,255,0.48),rgba(255,255,255,0.26))]"></div>
    <div class="relative flex items-center gap-4">
      <div class="flex h-[76px] w-[96px] shrink-0 items-center justify-center rounded-[18px] border border-white/70 bg-white/54 text-[38px]">
        {{ bundle.icon }}
      </div>
      <div class="min-w-0 flex-1">
        <div class="mb-1 flex items-center gap-2">
          <h3 class="truncate text-[17px] font-semibold text-[#403764]">{{ bundle.title }}</h3>
          <span class="shrink-0 rounded-full bg-[#eee7ff] px-2.5 py-1 text-[12px] font-medium text-[#8066d8]">{{ bundle.badge }}</span>
        </div>
        <p class="line-clamp-2 text-[13px] leading-6 text-[#746d96]">{{ bundle.description }}</p>
        <div class="mt-2 flex items-center justify-between gap-3">
          <span class="text-[18px] font-semibold text-[#f05c9a]">{{ bundle.price }}</span>
          <button
            type="button"
            class="inline-flex h-9 shrink-0 items-center justify-center rounded-full bg-[#8e6be8] px-4 text-sm font-medium text-white shadow-[0_8px_18px_rgba(142,107,232,0.24)] transition hover:bg-[#7d5bdc]"
            @click="emit('action', bundle)"
          >
            让她学习
          </button>
        </div>
      </div>
    </div>
  </article>
</template>

<style scoped lang="scss">
.skill-bundle-card {
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.72), rgba(251, 250, 255, 0.52), rgba(255, 255, 255, 0.36)),
    rgba(255, 255, 255, 0.58);
  box-shadow: 0 12px 32px rgba(110, 94, 160, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.78);

  button {
    background: linear-gradient(90deg, #efe9ff, #ddd3ff);
    color: #6e5ec4;
  }
}
</style>
