<script setup lang="ts">
import type { PropType } from 'vue'
import { Reading } from '@element-plus/icons-vue'
import type { SkillPackage } from './types'

defineProps({
  skill: { type: Object as PropType<SkillPackage>, required: true },
})

const emit = defineEmits<{
  (e: 'learn', skill: SkillPackage): void
}>()
</script>

<template>
  <article class="skill-package" :class="`is-${skill.tone}`">
    <div class="skill-package__icon">{{ skill.icon }}</div>
    <div class="skill-package__body">
      <h4>{{ skill.title }}</h4>
      <p>{{ skill.description }}</p>
      <span>适合：{{ skill.suitable }}</span>
    </div>
    <button type="button" @click="emit('learn', skill)">
      让她学习
      <el-icon><Reading /></el-icon>
    </button>
  </article>
</template>

<style scoped lang="scss">
.skill-package {
  display: grid;
  grid-template-columns: 46px minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  border-radius: 22px;
  padding: 12px;
  border: 1px solid rgba(255, 255, 255, 0.78);
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.74), rgba(255, 247, 253, 0.5)),
    rgba(255, 255, 255, 0.64);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.76);
  transition: transform 0.2s ease, box-shadow 0.2s ease;

  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 14px 30px rgba(139, 122, 230, 0.12), inset 0 1px 0 rgba(255, 255, 255, 0.82);
  }

  &__icon {
    width: 46px;
    height: 46px;
    border-radius: 17px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 25px;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.82);
  }

  h4 {
    margin: 0;
    color: #3f365c;
    font-size: 14px;
    font-weight: 900;
  }

  p {
    margin: 4px 0 0;
    color: #776c92;
    font-size: 12px;
    line-height: 1.45;
  }

  span {
    display: block;
    margin-top: 4px;
    color: #8b82a8;
    font-size: 11px;
    font-weight: 700;
  }

  button {
    height: 36px;
    border-radius: 999px;
    border: 1px solid rgba(190, 172, 240, 0.76);
    background: rgba(255, 255, 255, 0.78);
    color: #765bd9;
    padding: 0 12px;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    font-weight: 900;
    cursor: pointer;
    white-space: nowrap;
    transition: transform 0.2s ease, background 0.2s ease;

    &:hover {
      transform: translateY(-1px);
      background: #ffffff;
    }
  }
}

.is-green .skill-package__icon {
  background: linear-gradient(135deg, #f0fff4, #d9f7df);
}

.is-blue .skill-package__icon {
  background: linear-gradient(135deg, #eff8ff, #ddebff);
}

.is-pink .skill-package__icon {
  background: linear-gradient(135deg, #fff2fb, #ffd7ea);
}

.is-purple .skill-package__icon {
  background: linear-gradient(135deg, #f5f0ff, #e5dcff);
}
</style>
