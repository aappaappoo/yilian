<script setup lang="ts">
import type { PropType } from 'vue'
import { House } from '@element-plus/icons-vue'
import type { HomeCompanion } from './types'

defineProps({
  companion: { type: Object as PropType<HomeCompanion>, required: true },
})

const emit = defineEmits<{
  (e: 'enter', companion: HomeCompanion): void
}>()
</script>

<template>
  <article class="companion-card" @click="emit('enter', companion)">
    <div class="companion-card__image-wrap">
      <img :src="companion.image" :alt="companion.name" class="companion-card__image">
      <span class="favorite">♡</span>
      <span class="online-dot" :class="{ 'is-offline': !companion.online }">
        {{ companion.online ? '在房间里' : '稍后见面' }}
      </span>
    </div>

    <div class="companion-card__body">
      <div class="name-row">
        <h3>{{ companion.displayName }}</h3>
        <span>{{ companion.id }}</span>
      </div>
      <p class="subtitle">{{ companion.subtitle }}</p>
      <p class="desc">{{ companion.description }}</p>

      <div class="tag-row">
        <span v-for="tag in companion.tags.slice(0, 3)" :key="tag">{{ tag }}</span>
      </div>

      <div class="details">
        <p><b>技能：</b>{{ companion.skills.join('、') }}</p>
        <p><b>关系：</b>{{ companion.relationship }}</p>
        <p><b>最近：</b>{{ companion.recent }}</p>
      </div>

      <button type="button" class="meet-button" @click.stop="emit('enter', companion)">
        和她见面
        <el-icon><House /></el-icon>
      </button>
    </div>
  </article>
</template>

<style scoped lang="scss">
.companion-card {
  position: relative;
  overflow: hidden;
  border-radius: 30px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.78), rgba(255, 247, 253, 0.58)),
    rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(255, 255, 255, 0.82);
  box-shadow: 0 18px 42px rgba(139, 122, 230, 0.12), inset 0 1px 0 rgba(255, 255, 255, 0.76);
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  backdrop-filter: blur(18px);

  &::after {
    content: "";
    position: absolute;
    inset: auto 18px 0;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(255, 215, 234, 0.86), transparent);
  }

  &:hover {
    transform: translateY(-6px);
    box-shadow: 0 28px 62px rgba(139, 122, 230, 0.18), inset 0 1px 0 rgba(255, 255, 255, 0.84);

    .companion-card__image {
      transform: scale(1.045);
    }
  }
}

.companion-card__image-wrap {
  position: relative;
  height: 190px;
  overflow: hidden;
  background:
    radial-gradient(circle at 30% 18%, rgba(255, 215, 234, 0.72), transparent 32%),
    linear-gradient(135deg, #fff7fb, #f2f6ff);

  &::after {
    content: "";
    position: absolute;
    inset: 0;
    background: linear-gradient(180deg, transparent 58%, rgba(255, 255, 255, 0.82));
    pointer-events: none;
  }
}

.companion-card__image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center top;
  transition: transform 0.45s ease;
}

.favorite {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #d67eb2;
  font-size: 20px;
  background: rgba(255, 255, 255, 0.76);
  border: 1px solid rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(12px);
}

.online-dot {
  position: absolute;
  left: 12px;
  bottom: 12px;
  z-index: 1;
  border-radius: 999px;
  padding: 7px 10px;
  color: #6f58c5;
  background: rgba(255, 255, 255, 0.74);
  border: 1px solid rgba(255, 255, 255, 0.86);
  font-size: 11px;
  font-weight: 900;
  backdrop-filter: blur(12px);

  &::before {
    content: "";
    display: inline-block;
    width: 7px;
    height: 7px;
    margin-right: 6px;
    border-radius: 999px;
    background: #86d6a4;
    box-shadow: 0 0 0 4px rgba(134, 214, 164, 0.2);
  }

  &.is-offline::before {
    background: #d8ccef;
    box-shadow: 0 0 0 4px rgba(216, 204, 239, 0.24);
  }
}

.companion-card__body {
  padding: 17px;
}

.name-row {
  display: flex;
  align-items: baseline;
  gap: 8px;

  h3 {
    margin: 0;
    color: #3f365c;
    font-size: 20px;
    font-weight: 900;
  }

  span {
    color: #7f739e;
    font-size: 13px;
    font-weight: 800;
  }
}

.subtitle {
  margin: 5px 0 0;
  color: #5d4c89;
  font-size: 13px;
  font-weight: 800;
}

.desc {
  min-height: 40px;
  margin: 9px 0 0;
  color: #7d719c;
  font-size: 12px;
  line-height: 1.65;
}

.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin-top: 12px;

  span {
    border-radius: 999px;
    padding: 5px 9px;
    color: #765bd9;
    background: rgba(241, 237, 255, 0.84);
    border: 1px solid rgba(220, 204, 255, 0.58);
    font-size: 11px;
    font-weight: 800;
  }
}

.details {
  display: grid;
  gap: 6px;
  margin-top: 13px;
  border-radius: 18px;
  padding: 11px;
  background: rgba(255, 255, 255, 0.5);

  p {
    margin: 0;
    color: #7f739e;
    font-size: 12px;
    line-height: 1.45;
  }

  b {
    color: #51456f;
  }
}

.meet-button {
  width: 100%;
  height: 40px;
  margin-top: 15px;
  border: 1px solid rgba(190, 172, 240, 0.82);
  border-radius: 999px;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.9), rgba(255, 245, 252, 0.88));
  color: #765bd9;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 900;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease;

  &:hover {
    transform: translateY(-1px);
    box-shadow: 0 12px 24px rgba(139, 122, 230, 0.13);
  }
}
</style>
