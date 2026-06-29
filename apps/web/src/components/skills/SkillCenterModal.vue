<script setup lang="ts">
import { computed, ref } from 'vue'
import SkillCard from './SkillCard.vue'
import SkillBundleCard from './SkillBundleCard.vue'
import { AINI_LEARNED_SKILLS, AINI_SKILL_PACKS } from '../../utils/skillCatalog'
import type { SkillBundle, SkillPack } from './types'
import { useEscapeKey } from '../../composables/useEscapeKey'

const props = defineProps<{
  open: boolean
  botAvatarUrl: string
  botDisplayName: string
}>()

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
}>()

const activeCategory = ref('全部技能')
const skillKeyword = ref('')
const toastVisible = ref(false)
let toastTimer: ReturnType<typeof setTimeout> | null = null

const categories = ['全部技能', '生活助理', '旅行出行', '本地探索', '陪伴关系', 'VIP专属']

const learnedSkills = AINI_LEARNED_SKILLS
const skillPacks: SkillPack[] = AINI_SKILL_PACKS

const bundles: SkillBundle[] = [
  {
    id: 'travel-helper',
    title: '旅行助手组合',
    description: '机票查询 + 酒店推荐 + 旅行规划',
    price: '组合学习',
    badge: '推荐',
    icon: '🧳',
  },
  {
    id: 'deep-companion',
    title: '深度陪伴组合',
    description: '私密陪伴 + 纪念日记忆 + 深夜陪伴',
    price: '组合学习',
    badge: '温柔成长',
    icon: '🌙',
  },
]

const filteredSkillPacks = computed(() => {
  const keyword = skillKeyword.value.trim().toLowerCase()
  return skillPacks.filter((skill) => {
    const matchCategory = activeCategory.value === '全部技能'
      || skill.category === activeCategory.value
      || (activeCategory.value === 'VIP专属' && skill.tags.includes('VIP专属'))
    const content = `${skill.title} ${skill.description} ${skill.tags.join(' ')}`.toLowerCase()
    return matchCategory && (!keyword || content.includes(keyword))
  })
})

function showToast() {
  toastVisible.value = true
  if (toastTimer !== null) {
    clearTimeout(toastTimer)
  }
  toastTimer = setTimeout(() => {
    toastVisible.value = false
    toastTimer = null
  }, 1800)
}

function close() {
  emit('update:open', false)
}

useEscapeKey(close, {
  enabled: () => props.open,
  priority: 70,
})
</script>

<template>
  <Teleport to="body">
    <Transition name="skill-center">
      <div v-if="props.open" class="skill-center-overlay fixed inset-0 z-[70] flex items-center justify-center bg-[#3f3260]/18 px-4 py-5 backdrop-blur-[2px]">
        <section
          class="skill-center-panel relative flex h-[84vh] w-[min(82vw,1280px)] max-w-[1280px] flex-col overflow-hidden rounded-[28px] border border-white/65 bg-[#fffaff]/72 text-[#403764] shadow-[0_26px_90px_rgba(92,72,140,0.22)] backdrop-blur-2xl max-md:h-[calc(100dvh-20px)] max-md:w-[calc(100vw-20px)] max-md:rounded-[26px]"
          role="dialog"
          aria-modal="true"
          aria-label="Aini 技能中心"
        >
          <div class="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_10%_8%,rgba(255,222,239,0.76),transparent_32%),radial-gradient(circle_at_88%_0%,rgba(218,213,255,0.76),transparent_34%),linear-gradient(180deg,rgba(255,255,255,0.45),rgba(246,239,255,0.28))]"></div>

          <header class="relative shrink-0 px-8 pb-4 pt-8 max-md:px-4 max-md:pb-3 max-md:pt-4">
            <div class="flex items-start justify-between gap-5 max-md:gap-3">
              <div class="min-w-0">
                <div class="flex items-center gap-2">
                  <span class="i-carbon-sparkle text-2xl text-[#9d7ce8]"></span>
                  <h2 class="skill-center-title text-[30px] font-semibold leading-tight text-[#6950d8] max-md:text-[23px]">Aini 技能中心</h2>
                </div>
                <p class="mt-2 text-sm leading-6 text-[#615a86] max-md:text-xs">为她学习新的能力，让陪伴与任务能力持续成长</p>
              </div>

              <div class="flex min-w-[360px] items-center gap-3 max-md:min-w-0 max-md:flex-1">
                <label class="flex h-12 flex-1 items-center gap-2 rounded-full border border-[#e2d5ff]/80 bg-white/50 px-4 text-[#8f84ad] shadow-inner max-md:h-10 max-md:px-3">
                  <input
                    v-model="skillKeyword"
                    class="min-w-0 flex-1 bg-transparent text-sm text-[#514873] outline-none placeholder:text-[#a99fbd]"
                    placeholder="搜索技能名称或关键词..."
                  >
                  <span class="i-carbon-search text-xl"></span>
                </label>
                <button
                  type="button"
                  class="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-full border border-white/70 bg-white/58 text-[#7b719f] shadow-sm transition hover:bg-white/82 max-md:h-10 max-md:w-10"
                  aria-label="关闭技能中心"
                  @click="close"
                >
                  <span class="i-carbon-close text-2xl max-md:text-xl"></span>
                </button>
              </div>
            </div>

            <div class="skill-category-bar scrollbar-none mt-5 flex gap-2 overflow-x-auto rounded-full border border-white/60 bg-white/40 p-2 max-md:mt-4">
              <button
                v-for="category in categories"
                :key="category"
                type="button"
                class="h-10 shrink-0 rounded-full px-5 text-sm font-medium transition max-md:h-9 max-md:px-4 max-md:text-xs"
                :class="activeCategory === category
                  ? 'bg-gradient-to-r from-[#a891f3] to-[#7f64df] text-white shadow-[0_8px_18px_rgba(130,96,220,0.24)]'
                  : 'bg-white/42 text-[#625a83] hover:bg-white/68'"
                @click="activeCategory = category"
              >
                <span v-if="category === 'VIP专属'" class="i-carbon-crown mr-1 align-[-2px] text-[#f0b85a]"></span>
                {{ category }}
              </button>
            </div>
          </header>

          <div class="skill-center-body relative min-h-0 flex-1 overflow-y-auto px-8 pb-5 max-md:px-4">
            <div class="grid gap-5 lg:grid-cols-[268px_minmax(0,1fr)]">
              <aside class="space-y-4">
                <section class="growth-card rounded-[24px] border border-white/65 bg-white/58 p-5 shadow-[0_14px_36px_rgba(124,102,180,0.12)] backdrop-blur-xl">
                  <div class="flex items-center gap-4">
                    <img :src="botAvatarUrl" :alt="`${botDisplayName} avatar`" class="h-[74px] w-[74px] rounded-full border border-white/80 shadow-sm">
                    <div>
                      <p class="text-[26px] font-semibold text-[#7860dc]">Lv.3</p>
                      <p class="mt-1 text-sm text-[#6e6790]">已学习 6/12</p>
                    </div>
                  </div>
                  <div class="mt-5 h-3 overflow-hidden rounded-full bg-[#dfd9ee]">
                    <div class="h-full w-1/2 rounded-full bg-gradient-to-r from-[#9b7cf1] to-[#7e65df]"></div>
                  </div>
                  <p class="mt-3 text-xs text-[#766f96]">只展示当前真实已学习的能力</p>
                  <p class="mt-6 text-sm font-semibold text-[#4f4675]">已学习的技能</p>
                  <div class="mt-3 grid grid-cols-2 gap-2">
                    <span
                      v-for="skill in learnedSkills"
                      :key="skill.label"
                      class="inline-flex h-9 items-center gap-1.5 rounded-xl border border-[#ded4ff]/70 bg-white/48 px-2.5 text-xs text-[#655c87]"
                    >
                      <span :class="skill.icon" class="text-[#9e7ee8]"></span>
                      {{ skill.label }}
                    </span>
                  </div>
                </section>

                <section class="membership-card relative overflow-hidden rounded-[24px] border border-[#f5d9a4]/75 bg-[#fff0c8]/62 p-5 shadow-[0_14px_34px_rgba(182,136,66,0.13)] backdrop-blur-xl">
                  <div class="absolute inset-0 bg-[radial-gradient(circle_at_85%_12%,rgba(255,255,255,0.70),transparent_34%)]"></div>
                  <div class="relative">
                    <div class="flex items-center gap-2">
                      <span class="i-carbon-crown text-2xl text-[#d59a35]"></span>
                      <h3 class="text-lg font-semibold text-[#8a642d]">Aini 成长计划</h3>
                    </div>
                    <p class="mt-3 text-sm leading-6 text-[#806b4c]">为她安排长期学习路线，让陪伴能力慢慢变丰富</p>
                    <button
                      type="button"
                      class="mt-5 inline-flex h-11 w-full items-center justify-center gap-2 rounded-full bg-gradient-to-r from-[#f3c36b] to-[#e5a84c] text-sm font-semibold text-white shadow-[0_10px_22px_rgba(207,145,54,0.23)] transition hover:brightness-105"
                      @click="showToast"
                    >
                      <span class="i-carbon-crown"></span>
                      制定学习计划
                    </button>
                  </div>
                </section>
              </aside>

              <main class="min-w-0">
                <div class="grid grid-cols-3 gap-4 max-xl:grid-cols-2 max-md:grid-cols-1">
                  <SkillCard
                    v-for="skill in filteredSkillPacks"
                    :key="skill.id"
                    :skill="skill"
                    @action="showToast"
                  />
                </div>

                <div v-if="filteredSkillPacks.length === 0" class="flex min-h-[220px] items-center justify-center rounded-[24px] border border-white/60 bg-white/44 text-sm text-[#81779f]">
                  没有找到相关技能，换个关键词试试吧。
                </div>

                <div class="mt-5 grid grid-cols-2 gap-4 max-md:grid-cols-1">
                  <SkillBundleCard
                    v-for="bundle in bundles"
                    :key="bundle.id"
                    :bundle="bundle"
                    @action="showToast"
                  />
                </div>
              </main>
            </div>
          </div>

          <footer class="relative shrink-0 border-t border-white/45 px-8 py-3 max-md:px-4">
            <div class="flex items-center justify-center gap-2 text-xs text-[#80769f]">
              <span class="i-carbon-locked"></span>
              <span>加入学习计划后，她会在陪伴中慢慢掌握新的能力</span>
            </div>
          </footer>

          <Transition name="toast">
            <div
              v-if="toastVisible"
              class="absolute bottom-12 left-1/2 z-10 flex -translate-x-1/2 items-center gap-2 rounded-full border border-white/70 bg-[#3f3568]/82 px-5 py-3 text-sm text-white shadow-[0_12px_28px_rgba(65,53,104,0.22)] backdrop-blur-xl"
            >
              <span class="i-carbon-sparkle"></span>
              <span>已为她加入学习计划</span>
            </div>
          </Transition>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped lang="scss">
.skill-center-overlay {
  font-family: var(--soulmeet-font-family);
  background:
    radial-gradient(circle at 16% 8%, rgba(255, 215, 234, 0.2), transparent 34%),
    radial-gradient(circle at 84% 2%, rgba(221, 235, 255, 0.22), transparent 36%),
    rgba(63, 54, 92, 0.16);
}

.skill-center-panel {
  border-color: rgba(255, 255, 255, 0.78);
  background:
    radial-gradient(circle at 12% 8%, rgba(255, 247, 253, 0.72), transparent 28%),
    radial-gradient(circle at 88% 0%, rgba(243, 246, 255, 0.78), transparent 30%),
    rgba(247, 246, 251, 0.92);
  box-shadow: 0 28px 76px rgba(93, 80, 140, 0.16), inset 0 1px 0 rgba(255, 255, 255, 0.86);

  :deep(input::placeholder) {
    color: #a99fbd;
  }

  :deep(button) {
    font-family: inherit;
    letter-spacing: 0;
  }

  :deep(input) {
    font-family: inherit;
  }
}

.skill-center-title {
  color: #4a4a6a;
}

.skill-category-bar {
  background: rgba(255, 255, 255, 0.5);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.72);
}

.skill-category-bar :deep(button[class*="from-[#a891f3]"]) {
  background: linear-gradient(90deg, #efe9ff, #ddd3ff) !important;
  color: #6e5ec4 !important;
  box-shadow: 0 10px 22px rgba(110, 94, 160, 0.12) !important;
}

.skill-center-body {
  background: transparent;
}

.growth-card,
.membership-card {
  box-shadow: 0 12px 36px rgba(110, 94, 160, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.76);
}

.growth-card {
  background:
    radial-gradient(circle at 92% 10%, rgba(221, 235, 255, 0.46), transparent 36%),
    rgba(251, 250, 255, 0.62);
}

.membership-card {
  background:
    radial-gradient(circle at 88% 12%, rgba(255, 255, 255, 0.7), transparent 34%),
    linear-gradient(135deg, rgba(255, 250, 238, 0.66), rgba(255, 247, 253, 0.58));
}

.scrollbar-none {
  scrollbar-width: none;
}

.scrollbar-none::-webkit-scrollbar {
  display: none;
}

.skill-center-enter-active,
.skill-center-leave-active {
  transition: opacity 0.24s ease, transform 0.28s ease;
}

.skill-center-enter-from,
.skill-center-leave-to {
  opacity: 0;
  transform: scale(0.985);
}

.toast-enter-active,
.toast-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translate(-50%, 8px);
}
</style>
