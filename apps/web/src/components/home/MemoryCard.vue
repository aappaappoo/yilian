<template>
  <section class="memory-card">
    <span class="memory-card__pin">记忆花园</span>
    <h3>最近记忆</h3>
    <div class="memory-list">
      <p>她记得你喜欢安静的聊天方式。</p>
      <p>她记得你最近在关注天气和出行。</p>
    </div>
  </section>
</template>

<style scoped lang="scss">
.memory-card {
  position: relative;
  overflow: hidden;
  border-radius: 26px;
  padding: 18px;
  background:
    radial-gradient(circle at 96% 10%, rgba(255, 216, 234, 0.72), transparent 40%),
    linear-gradient(145deg, rgba(255, 255, 255, 0.72), rgba(255, 247, 253, 0.48));
  border: 1px solid rgba(255, 255, 255, 0.78);
  box-shadow: 0 18px 42px rgba(139, 122, 230, 0.12), inset 0 1px 0 rgba(255, 255, 255, 0.74);
  backdrop-filter: blur(20px);

  &__pin {
    display: inline-flex;
    margin-bottom: 9px;
    border-radius: 999px;
    padding: 5px 10px;
    color: #a074c9;
    background: rgba(255, 255, 255, 0.56);
    font-size: 11px;
    font-weight: 900;
  }

  h3 {
    margin: 0 0 14px;
    color: #4c3b7c;
    font-size: 18px;
    font-weight: 900;
  }
}

.memory-list {
  display: grid;
  gap: 10px;

  p {
    margin: 0;
    border-radius: 17px;
    padding: 12px 13px;
    background: rgba(255, 255, 255, 0.58);
    border: 1px solid rgba(255, 255, 255, 0.62);
    color: #766b98;
    font-size: 13px;
    line-height: 1.5;
  }
}
</style>
