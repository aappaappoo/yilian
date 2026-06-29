<template>
  <section class="progress-card">
    <span class="progress-card__mark">✦</span>
    <h3>你的陪伴进度</h3>
    <div class="progress-list">
      <p><span>陪伴时长</span><b>2h 35m</b></p>
      <p><span>已认识角色</span><b>3 位</b></p>
      <p><span>已解锁技能</span><b>8 个</b></p>
    </div>
  </section>
</template>

<style scoped lang="scss">
.progress-card {
  position: relative;
  overflow: hidden;
  border-radius: 26px;
  padding: 18px;
  background:
    radial-gradient(circle at 94% 6%, rgba(221, 235, 255, 0.72), transparent 34%),
    linear-gradient(145deg, rgba(255, 255, 255, 0.7), rgba(255, 247, 253, 0.5));
  border: 1px solid rgba(255, 255, 255, 0.78);
  box-shadow: 0 18px 42px rgba(139, 122, 230, 0.12), inset 0 1px 0 rgba(255, 255, 255, 0.74);
  backdrop-filter: blur(20px);

  &__mark {
    position: absolute;
    top: 16px;
    right: 18px;
    color: #c9a6ef;
    font-size: 18px;
  }

  h3 {
    margin: 0 0 14px;
    color: #4c3b7c;
    font-size: 18px;
    font-weight: 900;
  }
}

.progress-list {
  display: grid;
  gap: 10px;

  p {
    height: 42px;
    margin: 0;
    padding: 0 13px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-radius: 16px;
    background: rgba(255, 255, 255, 0.58);
    border: 1px solid rgba(255, 255, 255, 0.62);
    color: #7c7198;
    font-size: 13px;
    font-weight: 700;
  }

  b {
    color: #5f49a8;
    font-size: 14px;
  }
}
</style>
