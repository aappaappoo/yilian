<script setup lang="ts">
import type { SkillPack } from './types'

const props = defineProps<{
  skill: SkillPack
}>()

const emit = defineEmits<{
  (e: 'action', skill: SkillPack): void
}>()

function statusClass(status: SkillPack['status']) {
  if (status === 'learned') return 'text-[#31a980]'
  if (status === 'member-free' || status === 'vip') return 'text-[#8b7ae6]'
  if (status === 'trial') return 'text-[#32a98b]'
  return 'text-[#a56ad8]'
}
</script>

<template>
  <article
    class="skill-card group relative min-h-[224px] overflow-hidden rounded-[24px] border border-white/60 bg-white/58 p-4 shadow-[0_14px_36px_rgba(124,102,180,0.12)] backdrop-blur-xl transition duration-300 hover:-translate-y-1 hover:border-[#d9c9ff]/80 hover:bg-white/72"
  >
    <div class="pointer-events-none absolute inset-0 opacity-70" :class="skill.accent"></div>
    <div class="relative flex h-full flex-col">
      <div class="flex gap-3">
        <div class="flex h-[86px] w-[86px] shrink-0 items-center justify-center rounded-[20px] border border-white/70 bg-white/58 text-[38px] shadow-inner">
          {{ skill.icon }}
        </div>
        <div class="min-w-0 flex-1 pt-1">
          <div class="mb-1 flex items-start gap-2">
            <h3 class="min-w-0 flex-1 text-[17px] font-semibold leading-6 text-[#38325f]">{{ skill.title }}</h3>
            <span v-if="skill.badge" class="shrink-0 rounded-full bg-[#ff78ad]/90 px-2.5 py-1 text-[11px] font-medium text-white shadow-sm">{{ skill.badge }}</span>
          </div>
          <p class="text-[13px] leading-6 text-[#716b95]">{{ skill.description }}</p>
        </div>
      </div>

      <div class="mt-4 flex flex-wrap gap-2">
        <span
          v-for="tag in skill.tags"
          :key="tag"
          class="rounded-lg bg-[#eeeaff]/70 px-2.5 py-1 text-[12px] text-[#7f72aa]"
        >
          {{ tag }}
        </span>
      </div>

      <div class="mt-auto flex items-center justify-between gap-3 pt-4">
        <div class="text-[16px] font-semibold" :class="statusClass(skill.status)">
          <span v-if="skill.status === 'learned'" class="i-carbon-checkmark-filled mr-1 align-[-2px]"></span>
          {{ skill.priceLabel }}
        </div>
        <button
          type="button"
          class="inline-flex h-9 shrink-0 items-center justify-center rounded-full border px-4 text-sm font-medium transition disabled:cursor-default disabled:border-[#b7e4d6] disabled:bg-[#e8fff6] disabled:text-[#31a980]"
          :class="skill.status === 'learned'
            ? ''
            : 'border-[#d7c8ff] bg-white/68 text-[#7d63d8] hover:bg-[#fff] hover:text-[#6e55c9]'"
          :disabled="skill.status === 'learned'"
          @click="emit('action', skill)"
        >
          <span v-if="skill.status === 'learned'" class="i-carbon-checkmark mr-1"></span>
          {{ skill.actionText }}
        </button>
      </div>
    </div>
  </article>
</template>

<style scoped lang="scss">
.skill-card {
  background:
    linear-gradient(145deg, rgba(255, 255, 255, 0.72), rgba(251, 250, 255, 0.54)),
    rgba(255, 255, 255, 0.58);
  box-shadow: 0 12px 32px rgba(110, 94, 160, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.76);

  button:not(:disabled) {
    box-shadow: 0 8px 18px rgba(110, 94, 160, 0.1);
  }
}
</style>
