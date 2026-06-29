<script setup lang="ts">
import { HomeFilled, User, Memo, Star, MagicStick, Setting } from '@element-plus/icons-vue'

const navItems = [
  { label: '今日陪伴', icon: HomeFilled, active: true },
  { label: '陪伴者们', icon: User },
  { label: '记忆花园', icon: Memo },
  { label: '技能包', icon: Star },
  { label: '我的空间', icon: MagicStick },
]
</script>

<template>
  <aside class="sidebar-nav">
    <div>
      <div class="brand">
        <span class="brand__mark">
          <img src="/favicon-512.png" alt="SoulMeet" class="brand__icon">
        </span>
        <div>
          <p class="brand__name">SoulMeet</p>
          <p class="brand__sub">遇见懂你的陪伴</p>
        </div>
      </div>

      <nav class="nav-list">
        <button
          v-for="item in navItems"
          :key="item.label"
          type="button"
          class="nav-item"
          :class="{ 'is-active': item.active }"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </button>
      </nav>
    </div>

    <section class="comfort-record">
      <div class="comfort-record__decor">☾</div>
      <p class="comfort-record__label">今天已被陪伴</p>
      <p class="comfort-record__time">2h 35m</p>
      <button type="button" class="comfort-record__button">
        调整陪伴偏好
        <el-icon><Setting /></el-icon>
      </button>
    </section>
  </aside>
</template>

<style scoped lang="scss">
.sidebar-nav {
  width: 220px;
  min-width: 220px;
  min-height: 100vh;
  padding: 26px 18px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.74), rgba(255, 247, 253, 0.48));
  border-right: 1px solid rgba(220, 204, 255, 0.54);
  backdrop-filter: blur(22px);
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 32px;

  &__mark {
    width: 66px;
    height: 66px;
    flex: 0 0 66px;
    display: grid;
    place-items: center;
  }

  &__icon {
    width: 66px;
    height: 66px;
    display: block;
    object-fit: contain;
  }

  &__name {
    margin: 0;
    color: #5c4a9e;
    font-size: 23px;
    font-weight: 800;
    line-height: 1;
    letter-spacing: 0;
  }

  &__sub {
    margin: 5px 0 0;
    color: #8b82a8;
    font-size: 12px;
  }
}

.nav-list {
  display: grid;
  gap: 12px;
}

.nav-item {
  height: 54px;
  width: 100%;
  border: 1px solid transparent;
  border-radius: 18px;
  background: transparent;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 0 16px;
  color: #766b98;
  font-size: 15px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.2s ease;

  :deep(.el-icon) {
    font-size: 20px;
  }

  &:hover {
    background: rgba(255, 255, 255, 0.52);
    border-color: rgba(216, 205, 246, 0.72);
  }

  &.is-active {
    color: #765bd9;
    background: rgba(255, 255, 255, 0.72);
    border-color: rgba(216, 205, 246, 0.88);
    box-shadow: 0 14px 34px rgba(139, 122, 230, 0.14);
  }
}

.comfort-record {
  position: relative;
  overflow: hidden;
  border-radius: 26px;
  padding: 22px 18px 18px;
  background:
    radial-gradient(circle at 18% 12%, rgba(255, 216, 234, 0.96), transparent 38%),
    radial-gradient(circle at 92% 12%, rgba(221, 235, 255, 0.94), transparent 34%),
    rgba(255, 255, 255, 0.62);
  border: 1px solid rgba(255, 255, 255, 0.72);
  box-shadow: 0 20px 46px rgba(139, 122, 230, 0.16);

  &__decor {
    color: #c5a2ff;
    font-size: 30px;
    line-height: 1;
  }

  &__label {
    margin: 14px 0 0;
    color: #8b82a8;
    font-size: 13px;
    font-weight: 700;
  }

  &__time {
    margin: 8px 0 18px;
    color: #5f49a8;
    font-size: 32px;
    font-weight: 800;
  }

  &__button {
    width: 100%;
    height: 44px;
    border: 1px solid rgba(190, 172, 240, 0.72);
    border-radius: 16px;
    background: rgba(255, 255, 255, 0.64);
    color: #6f58c5;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    font-size: 13px;
    font-weight: 800;
    cursor: pointer;
  }
}
</style>
