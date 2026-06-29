<script setup lang="ts">
import type { PropType } from 'vue'
import { House, CollectionTag, Star, Sunny, UserFilled } from '@element-plus/icons-vue'
import type { HomeCompanion } from './types'

defineProps({
  companion: { type: Object as PropType<HomeCompanion>, required: true },
})

const emit = defineEmits<{
  (e: 'enter', companion: HomeCompanion): void
  (e: 'viewSkills'): void
}>()
</script>

<template>
  <section class="companion-hero">
    <div class="companion-hero__ambient" aria-hidden="true"></div>
    <div class="companion-hero__image-panel">
      <span class="scene-label">Sakura room</span>
      <img :src="companion.heroImage" :alt="companion.name" class="companion-hero__image">
    </div>

    <div class="companion-hero__content">
      <span class="hero-badge">
        <el-icon><Sunny /></el-icon>
        今日陪伴
      </span>
      <h2>{{ companion.displayName }} <span>{{ companion.id }}</span></h2>
      <h3>{{ companion.subtitle }}</h3>
      <p class="hero-desc">
        她今天在樱花庭院等你。擅长倾听、生活提醒、天气穿衣、出行规划。
      </p>

      <div class="hero-meta">
        <p>
          <el-icon><UserFilled /></el-icon>
          关系状态：{{ companion.relationship }}
        </p>
        <p>
          <el-icon><CollectionTag /></el-icon>
          已学习技能：{{ companion.skills.length }} 个
        </p>
        <p>
          <el-icon><Star /></el-icon>
          今日心情：{{ companion.mood }}
        </p>
      </div>

      <div class="hero-actions">
        <button type="button" class="hero-primary" @click="emit('enter', companion)">
          <el-icon><House /></el-icon>
          进入她的房间
        </button>
        <button type="button" class="hero-secondary" @click="emit('viewSkills')">
          <el-icon><CollectionTag /></el-icon>
          查看技能包
        </button>
      </div>

      <div class="hero-whisper">
        <span></span>
        她会带着今天学会的事，慢慢靠近你的生活。
      </div>
    </div>
  </section>
</template>

<style scoped lang="scss">
.companion-hero {
  position: relative;
  min-height: 376px;
  display: grid;
  grid-template-columns: minmax(0, 1.22fr) minmax(360px, 0.78fr);
  overflow: hidden;
  border-radius: 38px;
  border: 1px solid rgba(255, 255, 255, 0.82);
  background:
    radial-gradient(circle at 8% 8%, rgba(255, 215, 234, 0.78), transparent 26%),
    linear-gradient(115deg, rgba(255, 255, 255, 0.2), rgba(255, 255, 255, 0.78)),
    rgba(255, 255, 255, 0.56);
  box-shadow: 0 30px 76px rgba(139, 122, 230, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(22px);

  &::before {
    content: "";
    position: absolute;
    inset: 14px;
    border-radius: 30px;
    border: 1px solid rgba(255, 255, 255, 0.36);
    pointer-events: none;
    z-index: 2;
  }
}

.companion-hero__ambient {
  position: absolute;
  right: 19%;
  top: 11%;
  width: 160px;
  height: 160px;
  border-radius: 999px;
  background: radial-gradient(circle, rgba(255, 215, 234, 0.5), transparent 70%);
  filter: blur(2px);
  pointer-events: none;
  z-index: 1;
}

.companion-hero__image-panel {
  position: relative;
  min-height: 376px;
  overflow: hidden;
  background:
    radial-gradient(circle at 26% 18%, rgba(255, 230, 241, 0.92), transparent 22%),
    radial-gradient(circle at 70% 74%, rgba(221, 235, 255, 0.72), transparent 32%),
    linear-gradient(135deg, #fff7fb, #f4eeff);

  &::after {
    content: "";
    position: absolute;
    inset: 0;
    background:
      linear-gradient(90deg, transparent 58%, rgba(255, 255, 255, 0.66) 100%),
      linear-gradient(180deg, transparent 55%, rgba(255, 247, 251, 0.5) 100%),
      radial-gradient(circle at 20% 16%, rgba(255, 216, 234, 0.34), transparent 32%);
    pointer-events: none;
  }
}

.scene-label {
  position: absolute;
  left: 24px;
  top: 24px;
  z-index: 3;
  border-radius: 999px;
  padding: 8px 13px;
  color: rgba(95, 73, 168, 0.76);
  background: rgba(255, 255, 255, 0.58);
  border: 1px solid rgba(255, 255, 255, 0.78);
  font-size: 12px;
  font-weight: 900;
  backdrop-filter: blur(12px);
}

.companion-hero__image {
  width: 100%;
  height: 100%;
  min-height: 376px;
  object-fit: cover;
  object-position: center top;
  display: block;
  filter: saturate(1.04) contrast(0.98);
}

.companion-hero__content {
  position: relative;
  z-index: 3;
  padding: 34px 36px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  color: #3f365c;
}

.hero-badge {
  width: fit-content;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  border-radius: 999px;
  padding: 8px 14px;
  color: #765bd9;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.82), rgba(251, 242, 255, 0.66));
  border: 1px solid rgba(220, 204, 255, 0.86);
  font-size: 13px;
  font-weight: 800;
}

h2 {
  margin: 22px 0 0;
  font-size: clamp(40px, 4vw, 58px);
  line-height: 1.05;
  color: #4c3b7c;
  font-weight: 900;

  span {
    color: #8b82a8;
    font-size: 25px;
    font-weight: 700;
  }
}

h3 {
  margin: 12px 0 0;
  color: #5d4c89;
  font-size: 18px;
}

.hero-desc {
  max-width: 440px;
  margin: 16px 0 0;
  color: #6c6387;
  font-size: 15px;
  line-height: 1.8;
}

.hero-meta {
  display: grid;
  gap: 10px;
  margin-top: 22px;

  p {
    margin: 0;
    display: flex;
    align-items: center;
    gap: 10px;
    min-height: 38px;
    border-radius: 16px;
    padding: 0 12px;
    background: rgba(255, 255, 255, 0.46);
    color: #665b88;
    font-size: 14px;
    font-weight: 700;
  }

  :deep(.el-icon) {
    color: #8b7ae6;
    font-size: 17px;
  }
}

.hero-actions {
  display: flex;
  gap: 14px;
  margin-top: 30px;
}

.hero-primary,
.hero-secondary {
  height: 48px;
  border-radius: 999px;
  padding: 0 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  font-weight: 800;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease;

  &:hover {
    transform: translateY(-2px);
  }
}

.hero-primary {
  border: 0;
  color: #fff;
  background: linear-gradient(135deg, #8b7ae6, #c59dff 58%, #ffbddd);
  box-shadow: 0 16px 34px rgba(139, 122, 230, 0.28);
}

.hero-secondary {
  color: #765bd9;
  background: rgba(255, 255, 255, 0.56);
  border: 1px solid rgba(190, 172, 240, 0.86);
}

.hero-whisper {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 18px;
  color: #8b82a8;
  font-size: 12px;
  font-weight: 800;

  span {
    width: 34px;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(139, 122, 230, 0.58));
  }
}

@media (max-width: 1320px) {
  .companion-hero {
    grid-template-columns: 1fr;
  }

  .companion-hero__image-panel {
    min-height: 320px;
  }
}
</style>
