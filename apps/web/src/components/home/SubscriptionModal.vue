<script setup lang="ts">
import { computed, ref } from 'vue'
import { useEscapeKey } from '../../composables/useEscapeKey'

interface BillingPlan {
  id: string
  title: string
  price: string
  period: string
  desc: string
  badges?: string[]
}

interface BenefitItem {
  label: string
  icon: string
}

interface SubscriptionTier {
  tier: 'pro' | 'plus'
  name: string
  kicker: string
  icon: string
  benefits: BenefitItem[]
  plans: BillingPlan[]
}

const emit = defineEmits<{
  close: []
  subscribe: [plan: BillingPlan & { tier: SubscriptionTier['tier']; tierName: string }]
}>()

const selectedPlanId = ref('pro_yearly')

useEscapeKey(() => emit('close'), { priority: 80 })

const tiers: SubscriptionTier[] = [
  {
    tier: 'pro',
    name: 'SoulMeet Pro',
    kicker: '轻盈进阶',
    icon: 'i-carbon-sparkle',
    benefits: [
      { label: '更多角色', icon: 'i-carbon-face-satisfied' },
      { label: '更长陪伴', icon: 'i-carbon-time' },
      { label: '高级记忆', icon: 'i-carbon-bookmark' },
      { label: '新功能抢先体验', icon: 'i-carbon-rocket' },
    ],
    plans: [
      { id: 'pro_monthly', title: '月度会员', price: '¥28', period: '/ 月', desc: '约 ¥0.93 / 天' },
      { id: 'pro_quarterly', title: '季度会员', price: '¥68', period: '/ 3个月', desc: '约 ¥0.76 / 天', badges: ['省 18%'] },
      { id: 'pro_yearly', title: '年度会员', price: '¥228', period: '/ 年', desc: '约 ¥0.63 / 天', badges: ['最受欢迎', '约省 32%'] },
    ],
  },
  {
    tier: 'plus',
    name: 'SoulMeet Plus',
    kicker: '皇冠限定',
    icon: 'i-carbon-crown',
    benefits: [
      { label: '包含 Pro 全部权益', icon: 'i-carbon-gift' },
      { label: '深度记忆', icon: 'i-carbon-data-vis-4' },
      { label: '专属限定角色', icon: 'i-carbon-star-filled' },
      { label: '更高优先级陪伴', icon: 'i-carbon-favorite-filled' },
    ],
    plans: [
      { id: 'plus_monthly', title: '月度会员', price: '¥48', period: '/ 月', desc: '约 ¥1.60 / 天' },
      { id: 'plus_quarterly', title: '季度会员', price: '¥128', period: '/ 3个月', desc: '约 ¥1.42 / 天', badges: ['省 11%'] },
      { id: 'plus_yearly', title: '年度会员', price: '¥428', period: '/ 年', desc: '约 ¥1.17 / 天', badges: ['超值推荐', '约省 39%'] },
    ],
  },
]

const selectedPlan = computed(() => {
  for (const tier of tiers) {
    const plan = tier.plans.find(item => item.id === selectedPlanId.value)
    if (plan) return { ...plan, tierName: tier.name }
  }
  return null
})

function selectPlan(planId: string) {
  selectedPlanId.value = planId
}

function handleSubscribe() {
  for (const tier of tiers) {
    const plan = tier.plans.find(item => item.id === selectedPlanId.value)
    if (plan) {
      const payload = { ...plan, tier: tier.tier, tierName: tier.name }
      console.log('[SoulMeet Pro] subscribe plan:', payload)
      emit('subscribe', payload)
      return
    }
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="subscription-modal">
      <div class="subscription-overlay" @click.self="emit('close')">
        <section class="subscription-panel" role="dialog" aria-modal="true" aria-label="SoulMeet Pro 订阅方案">
          <div class="subscription-panel__glow subscription-panel__glow--pink"></div>
          <div class="subscription-panel__glow subscription-panel__glow--violet"></div>
          <div class="subscription-panel__stars" aria-hidden="true">
            <span></span>
            <span></span>
            <span></span>
          </div>
          <button type="button" class="subscription-close" aria-label="关闭订阅弹窗" @click="emit('close')">
            <span class="i-carbon-close"></span>
          </button>

          <header class="subscription-header">
            <div class="subscription-header__copy">
              <span class="subscription-kicker"><span class="i-carbon-star-filled"></span> SoulMeet 订阅</span>
              <h2>选择你的订阅方案</h2>
              <p>解锁更深入的陪伴体验，让每一次相遇都更温柔、更懂你。</p>
            </div>

            <div class="subscription-orbit" aria-hidden="true">
              <span class="subscription-orbit__ring"></span>
              <span class="subscription-orbit__core">
                <span class="i-carbon-favorite-filled"></span>
              </span>
              <span class="subscription-orbit__crown i-carbon-crown"></span>
              <span class="subscription-orbit__spark subscription-orbit__spark--one">✦</span>
              <span class="subscription-orbit__spark subscription-orbit__spark--two">✧</span>
            </div>
          </header>

          <div class="subscription-tiers">
            <section
              v-for="tier in tiers"
              :key="tier.tier"
              class="subscription-tier"
              :class="`subscription-tier--${tier.tier}`"
            >
              <span class="subscription-tier__shine" aria-hidden="true"></span>
              <div class="subscription-tier__head">
                <div class="subscription-tier__title">
                  <span class="subscription-tier__logo">
                    <span class="subscription-tier__logo-glow"></span>
                    <span class="subscription-tier__icon" :class="tier.icon"></span>
                  </span>
                  <div>
                    <p>{{ tier.name }}</p>
                    <span class="subscription-tier__kicker">{{ tier.kicker }}</span>
                  </div>
                </div>
                <div class="subscription-benefits">
                  <span v-for="benefit in tier.benefits" :key="benefit.label" class="subscription-benefit">
                    <span class="subscription-benefits__icon" :class="benefit.icon" aria-hidden="true"></span>
                    {{ benefit.label }}
                  </span>
                </div>
              </div>

              <div class="subscription-plan-grid">
                <button
                  v-for="plan in tier.plans"
                  :key="plan.id"
                  type="button"
                  class="subscription-plan"
                  :class="{
                    'subscription-plan--selected': selectedPlanId === plan.id,
                    'subscription-plan--featured': plan.id.endsWith('yearly'),
                  }"
                  @click="selectPlan(plan.id)"
                >
                  <span v-if="plan.badges?.length" class="subscription-plan__badges">
                    <span v-for="badge in plan.badges" :key="badge">{{ badge }}</span>
                  </span>
                  <span class="subscription-plan__radio" aria-hidden="true"></span>
                  <span class="subscription-plan__content">
                    <span class="subscription-plan__title">{{ plan.title }}</span>
                    <span class="subscription-plan__desc">{{ plan.desc }}</span>
                  </span>
                  <span class="subscription-plan__price">
                    <strong>{{ plan.price }}</strong>
                    <small>{{ plan.period }}</small>
                  </span>
                </button>
              </div>
            </section>
          </div>

          <footer class="subscription-footer">
            <div class="subscription-footer__note">
              <span class="i-carbon-shield"></span>
              <div>
                <strong>{{ selectedPlan ? `已选择 ${selectedPlan.tierName} · ${selectedPlan.title}` : '已选择订阅方案' }}</strong>
                <p>可随时取消，自动续费前提醒</p>
              </div>
            </div>
            <div class="subscription-footer__actions">
              <button type="button" class="subscription-later" @click="emit('close')">稍后再说</button>
              <button type="button" class="subscription-primary" @click="handleSubscribe">
                立即订阅 <span>✦</span>
              </button>
            </div>
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped lang="scss">
.subscription-overlay {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 30px;
  background:
    radial-gradient(circle at 16% 12%, rgba(255, 216, 236, 0.42), transparent 31%),
    radial-gradient(circle at 82% 8%, rgba(219, 229, 255, 0.42), transparent 33%),
    linear-gradient(135deg, rgba(67, 54, 96, 0.3), rgba(145, 96, 150, 0.18));
  backdrop-filter: blur(12px);
}

.subscription-panel {
  position: relative;
  width: min(1100px, calc(100vw - 60px));
  max-height: min(820px, calc(100vh - 60px));
  overflow: hidden auto;
  border: 1px solid rgba(255, 255, 255, 0.72);
  border-radius: 34px;
  padding: 28px;
  color: #4d466e;
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.88), rgba(252, 246, 255, 0.72)),
    radial-gradient(circle at 7% 0%, rgba(255, 236, 247, 0.92), transparent 30%),
    radial-gradient(circle at 92% 0%, rgba(232, 224, 255, 0.9), transparent 34%);
  box-shadow:
    0 28px 90px rgba(83, 64, 124, 0.22),
    0 8px 26px rgba(214, 127, 185, 0.1),
    inset 0 1px 0 rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(26px);
  font-family: var(--soulmeet-font-family);
}

.subscription-panel::before {
  content: "";
  position: absolute;
  inset: 10px;
  pointer-events: none;
  border: 1px solid rgba(255, 255, 255, 0.52);
  border-radius: 28px;
}

.subscription-panel__glow,
.subscription-tier__shine {
  position: absolute;
  pointer-events: none;
  border-radius: 999px;
}

.subscription-panel__glow--pink {
  right: -44px;
  top: -36px;
  width: 280px;
  height: 210px;
  background: radial-gradient(circle, rgba(255, 196, 228, 0.45), transparent 68%);
}

.subscription-panel__glow--violet {
  left: -86px;
  bottom: 24px;
  width: 310px;
  height: 250px;
  background: radial-gradient(circle, rgba(204, 190, 255, 0.4), transparent 70%);
}

.subscription-panel__stars {
  position: absolute;
  inset: 0;
  pointer-events: none;

  span {
    position: absolute;
    width: 5px;
    height: 5px;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.94);
    box-shadow: 0 0 16px rgba(168, 126, 230, 0.66);
  }

  span:nth-child(1) {
    left: 42%;
    top: 42px;
  }

  span:nth-child(2) {
    right: 31%;
    top: 98px;
    width: 4px;
    height: 4px;
  }

  span:nth-child(3) {
    left: 8%;
    bottom: 96px;
    width: 6px;
    height: 6px;
  }
}

.subscription-close {
  position: absolute;
  top: 20px;
  right: 20px;
  z-index: 4;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border: 1px solid rgba(220, 204, 255, 0.68);
  border-radius: 999px;
  color: #8d7bb3;
  background: rgba(255, 255, 255, 0.64);
  box-shadow: 0 10px 24px rgba(103, 82, 143, 0.08);
  cursor: pointer;
  transition: transform 0.2s ease, background 0.2s ease, color 0.2s ease, box-shadow 0.2s ease;

  &:hover {
    transform: translateY(-1px);
    color: #6b54a8;
    background: rgba(255, 255, 255, 0.9);
    box-shadow: 0 14px 28px rgba(103, 82, 143, 0.12);
  }
}

.subscription-header,
.subscription-tiers,
.subscription-footer {
  position: relative;
  z-index: 1;
}

.subscription-header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 230px;
  gap: 22px;
  align-items: center;
  padding: 4px 46px 24px 4px;
}

.subscription-kicker {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 30px;
  border: 1px solid rgba(255, 255, 255, 0.58);
  border-radius: 999px;
  padding: 0 14px;
  color: #fff;
  background: linear-gradient(90deg, #9b7cf1, #e28bc6);
  box-shadow: 0 12px 24px rgba(169, 119, 222, 0.18);
  font-size: 12px;
  font-weight: 900;
}

.subscription-header__copy {
  h2 {
    margin: 15px 0 0;
    color: #474064;
    font-size: clamp(32px, 3.3vw, 44px);
    font-weight: 900;
    line-height: 1.15;
  }

  p {
    max-width: 630px;
    margin: 11px 0 0;
    color: #756d95;
    font-size: 15px;
    font-weight: 650;
    line-height: 1.9;
  }
}

.subscription-orbit {
  position: relative;
  min-height: 154px;
}

.subscription-orbit__ring {
  position: absolute;
  inset: 22px 0 6px 20px;
  border: 1px solid rgba(255, 255, 255, 0.72);
  border-radius: 999px;
  background:
    radial-gradient(circle at 50% 45%, rgba(255, 255, 255, 0.96), transparent 25%),
    radial-gradient(circle, rgba(226, 213, 255, 0.7), transparent 68%);
  box-shadow: inset 0 0 26px rgba(255, 255, 255, 0.82), 0 18px 38px rgba(151, 109, 218, 0.14);
  transform: rotate(-10deg);
}

.subscription-orbit__core {
  position: absolute;
  right: 48px;
  top: 28px;
  display: grid;
  place-items: center;
  width: 104px;
  height: 104px;
  border: 1px solid rgba(255, 255, 255, 0.74);
  border-radius: 38% 62% 52% 48% / 48% 44% 56% 52%;
  color: rgba(255, 255, 255, 0.92);
  background:
    radial-gradient(circle at 34% 25%, rgba(255, 255, 255, 0.95), transparent 22%),
    linear-gradient(135deg, rgba(255, 173, 218, 0.78), rgba(169, 132, 244, 0.6), rgba(219, 237, 255, 0.62));
  box-shadow: 0 20px 44px rgba(195, 132, 216, 0.2), inset 0 1px 18px rgba(255, 255, 255, 0.75);
  font-size: 42px;
}

.subscription-orbit__crown {
  position: absolute;
  right: 83px;
  top: 54px;
  color: #fff4bd;
  font-size: 32px;
  filter: drop-shadow(0 8px 14px rgba(132, 87, 188, 0.22));
}

.subscription-orbit__spark {
  position: absolute;
  color: #fff;
  text-shadow: 0 0 14px rgba(168, 126, 230, 0.72);
  font-size: 23px;
}

.subscription-orbit__spark--one {
  right: 190px;
  top: 26px;
}

.subscription-orbit__spark--two {
  right: 18px;
  top: 108px;
}

.subscription-tiers {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.subscription-tier {
  position: relative;
  min-width: 0;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.66);
  border-radius: 28px;
  padding: 18px;
  box-shadow: 0 18px 44px rgba(96, 78, 137, 0.11), inset 0 1px 0 rgba(255, 255, 255, 0.78);
}

.subscription-tier--pro {
  background:
    radial-gradient(circle at 92% 0%, rgba(218, 207, 255, 0.7), transparent 32%),
    linear-gradient(150deg, rgba(255, 255, 255, 0.74), rgba(246, 242, 255, 0.56));
}

.subscription-tier--plus {
  background:
    radial-gradient(circle at 92% 0%, rgba(255, 194, 229, 0.76), transparent 34%),
    linear-gradient(150deg, rgba(255, 253, 255, 0.78), rgba(255, 239, 249, 0.58));
}

.subscription-tier__shine {
  top: -72px;
  right: -56px;
  width: 190px;
  height: 190px;
  background: radial-gradient(circle, rgba(255, 255, 255, 0.66), transparent 64%);
}

.subscription-tier__head {
  position: relative;
  z-index: 1;
  display: grid;
  gap: 16px;
}

.subscription-tier__title {
  display: flex;
  align-items: center;
  gap: 13px;

  p {
    margin: 0;
    color: #594a91;
    font-size: 21px;
    font-weight: 900;
    line-height: 1.1;
  }

  .subscription-tier__kicker {
    display: inline-flex;
    margin-top: 6px;
    border-radius: 999px;
    padding: 4px 9px;
    color: #83799e;
    background: rgba(255, 255, 255, 0.58);
    font-size: 11px;
    font-weight: 850;
  }
}

.subscription-tier--plus .subscription-tier__title p {
  color: #bf4f91;
}

.subscription-tier__logo {
  position: relative;
  display: inline-grid;
  place-items: center;
  width: 52px;
  height: 52px;
  flex: 0 0 auto;
  border: 1px solid rgba(255, 255, 255, 0.78);
  border-radius: 20px;
  background:
    radial-gradient(circle at 32% 24%, rgba(255, 255, 255, 0.96), transparent 23%),
    linear-gradient(135deg, rgba(215, 200, 255, 0.98), rgba(248, 244, 255, 0.78));
  box-shadow: 0 16px 30px rgba(112, 82, 198, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.92);
}

.subscription-tier__logo-glow {
  position: absolute;
  inset: -10px;
  border-radius: 24px;
  background: radial-gradient(circle, rgba(125, 88, 225, 0.34), transparent 67%);
}

.subscription-tier__icon {
  position: relative;
  z-index: 1;
  display: inline-grid;
  place-items: center;
  color: #6846c9;
  font-size: 25px;
  filter: drop-shadow(0 5px 9px rgba(93, 60, 185, 0.28));
}

.subscription-tier--plus .subscription-tier__logo {
  background:
    radial-gradient(circle at 32% 24%, rgba(255, 255, 255, 0.96), transparent 25%),
    linear-gradient(135deg, rgba(255, 188, 226, 0.98), rgba(246, 222, 255, 0.78));
  box-shadow: 0 16px 30px rgba(205, 72, 150, 0.22), inset 0 1px 0 rgba(255, 255, 255, 0.92);
}

.subscription-tier--plus .subscription-tier__logo-glow {
  background: radial-gradient(circle, rgba(222, 67, 154, 0.34), transparent 68%);
}

.subscription-tier--plus .subscription-tier__icon {
  color: #c9338d;
  filter: drop-shadow(0 5px 9px rgba(189, 43, 132, 0.3));
}

.subscription-benefits {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 9px;
}

.subscription-benefit {
  display: inline-flex;
  align-items: center;
  min-width: 0;
  gap: 8px;
  min-height: 38px;
  border: 1px solid rgba(255, 255, 255, 0.58);
  border-radius: 16px;
  padding: 0 10px;
  color: #6e668f;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.72), rgba(248, 245, 255, 0.46));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.78);
  font-size: 12px;
  font-weight: 800;
  line-height: 1.2;
}

.subscription-benefits__icon {
  display: inline-grid;
  place-items: center;
  width: 23px;
  height: 23px;
  flex: 0 0 auto;
  border-radius: 999px;
  color: #6846c9;
  background: rgba(224, 214, 255, 0.96);
  box-shadow: 0 5px 12px rgba(105, 72, 204, 0.18);
  font-size: 13px;
}

.subscription-tier--plus .subscription-benefit {
  color: #875979;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.76), rgba(255, 240, 249, 0.52));
}

.subscription-tier--plus .subscription-benefits__icon {
  color: #c9338d;
  background: rgba(255, 211, 236, 0.96);
  box-shadow: 0 5px 12px rgba(201, 51, 141, 0.18);
}

.subscription-plan-grid {
  position: relative;
  z-index: 1;
  display: grid;
  gap: 10px;
  margin-top: 16px;
}

.subscription-plan {
  position: relative;
  display: grid;
  grid-template-columns: 22px minmax(0, 1fr) auto;
  align-items: center;
  gap: 11px;
  min-height: 76px;
  border: 1px solid rgba(226, 214, 255, 0.72);
  border-radius: 20px;
  padding: 14px 15px;
  overflow: hidden;
  text-align: left;
  color: #4c3b7c;
  background:
    linear-gradient(145deg, rgba(255, 255, 255, 0.76), rgba(255, 249, 253, 0.58)),
    rgba(255, 255, 255, 0.58);
  box-shadow: 0 10px 24px rgba(115, 94, 160, 0.07), inset 0 1px 0 rgba(255, 255, 255, 0.78);
  cursor: pointer;
  transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;

  &:hover {
    transform: translateY(-2px);
    background: rgba(255, 255, 255, 0.82);
    box-shadow: 0 15px 30px rgba(115, 94, 160, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.82);
  }
}

.subscription-plan--selected {
  border-color: rgba(133, 99, 232, 0.74);
  background:
    radial-gradient(circle at 96% 2%, rgba(196, 162, 248, 0.26), transparent 40%),
    linear-gradient(145deg, rgba(255, 255, 255, 0.92), rgba(248, 244, 255, 0.66));
  box-shadow:
    0 16px 34px rgba(133, 99, 232, 0.15),
    0 0 0 3px rgba(224, 214, 255, 0.5),
    inset 0 1px 0 rgba(255, 255, 255, 0.9);
}

.subscription-tier--plus .subscription-plan--selected {
  border-color: rgba(229, 91, 164, 0.7);
  background:
    radial-gradient(circle at 96% 2%, rgba(255, 166, 214, 0.28), transparent 41%),
    linear-gradient(145deg, rgba(255, 255, 255, 0.92), rgba(255, 244, 250, 0.68));
  box-shadow:
    0 16px 34px rgba(218, 92, 164, 0.15),
    0 0 0 3px rgba(255, 218, 239, 0.56),
    inset 0 1px 0 rgba(255, 255, 255, 0.9);
}

.subscription-plan__radio {
  position: relative;
  z-index: 1;
  width: 21px;
  height: 21px;
  border: 1px solid rgba(150, 132, 190, 0.48);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.62);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.78);
}

.subscription-plan--selected .subscription-plan__radio {
  border-color: #8467e7;
  background: radial-gradient(circle, #8467e7 0 35%, rgba(255, 255, 255, 0.8) 39%);
}

.subscription-tier--plus .subscription-plan--selected .subscription-plan__radio {
  border-color: #e45ba4;
  background: radial-gradient(circle, #e45ba4 0 35%, rgba(255, 255, 255, 0.8) 39%);
}

.subscription-plan__content,
.subscription-plan__price,
.subscription-plan__title,
.subscription-plan__desc {
  position: relative;
  z-index: 1;
  display: block;
  min-width: 0;
}

.subscription-plan__title {
  color: #554878;
  font-size: 15px;
  font-weight: 900;
}

.subscription-plan__desc {
  margin-top: 5px;
  color: #988fac;
  font-size: 12px;
  font-weight: 750;
}

.subscription-plan__price {
  text-align: right;

  strong {
    color: #644ccc;
    font-size: 28px;
    font-weight: 950;
    letter-spacing: 0;
  }

  small {
    display: block;
    margin-top: 3px;
    color: #716684;
    font-size: 12px;
    font-weight: 800;
  }
}

.subscription-tier--plus .subscription-plan__price strong {
  color: #cf4d97;
}

.subscription-plan__badges {
  position: absolute;
  right: 14px;
  top: 0;
  z-index: 2;
  display: flex;
  gap: 5px;
  transform: translateY(-1px);

  span {
    border-radius: 0 0 9px 9px;
    padding: 4px 8px;
    color: #fff;
    background: linear-gradient(90deg, #9574ef, #c9a2ff);
    box-shadow: 0 8px 16px rgba(143, 109, 226, 0.18);
    font-size: 10px;
    font-weight: 950;
  }
}

.subscription-tier--plus .subscription-plan__badges span {
  background: linear-gradient(90deg, #e85fa7, #ffa3cc);
  box-shadow: 0 8px 16px rgba(224, 95, 168, 0.16);
}

.subscription-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: 18px;
  border: 1px solid rgba(255, 255, 255, 0.62);
  border-radius: 24px;
  padding: 13px 14px 13px 16px;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.64), rgba(250, 245, 255, 0.44));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.78);
}

.subscription-footer__note {
  display: flex;
  align-items: center;
  gap: 11px;
  min-width: 0;
  color: #756b95;

  > span {
    position: relative;
    display: inline-grid;
    place-items: center;
    width: 42px;
    height: 42px;
    flex: 0 0 auto;
    border: 1px solid rgba(255, 255, 255, 0.72);
    border-radius: 16px;
    color: #fff;
    background:
      radial-gradient(circle at 32% 24%, rgba(255, 255, 255, 0.9), transparent 24%),
      linear-gradient(135deg, #8061df, #d85aa5);
    box-shadow:
      0 12px 24px rgba(129, 91, 214, 0.2),
      0 0 0 4px rgba(229, 213, 255, 0.38),
      inset 0 1px 0 rgba(255, 255, 255, 0.5);
    font-size: 18px;

    &::after {
      content: "";
      position: absolute;
      inset: -8px;
      z-index: -1;
      border-radius: 20px;
      background: radial-gradient(circle, rgba(216, 90, 165, 0.22), transparent 68%);
    }
  }

  strong {
    display: block;
    color: #554b76;
    font-size: 13px;
    font-weight: 900;
  }

  p {
    margin: 4px 0 0;
    color: #8e86a2;
    font-size: 12px;
    font-weight: 750;
  }
}

.subscription-footer__actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  flex: 0 0 auto;
}

.subscription-primary,
.subscription-later {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 46px;
  border-radius: 999px;
  font-size: 14px;
  font-weight: 900;
  cursor: pointer;
  transition: transform 0.2s ease, filter 0.2s ease, background 0.2s ease, color 0.2s ease, box-shadow 0.2s ease;
}

.subscription-primary {
  gap: 8px;
  min-width: 190px;
  border: 0;
  color: #fff;
  background: linear-gradient(90deg, #8567e7, #d95aa3, #a878f0);
  box-shadow: 0 16px 34px rgba(169, 99, 216, 0.24);

  &:hover {
    transform: translateY(-1px);
    filter: brightness(1.03);
    box-shadow: 0 19px 38px rgba(169, 99, 216, 0.3);
  }
}

.subscription-later {
  min-width: 116px;
  border: 1px solid rgba(218, 204, 246, 0.72);
  color: #8a79ad;
  background: rgba(255, 255, 255, 0.6);

  &:hover {
    color: #6f5ba8;
    background: rgba(255, 255, 255, 0.86);
  }
}

.subscription-modal-enter-active,
.subscription-modal-leave-active {
  transition: opacity 0.22s ease;

  .subscription-panel {
    transition: transform 0.24s ease, opacity 0.22s ease;
  }
}

.subscription-modal-enter-from,
.subscription-modal-leave-to {
  opacity: 0;

  .subscription-panel {
    opacity: 0;
    transform: translateY(12px) scale(0.985);
  }
}

@media (max-width: 980px) {
  .subscription-overlay {
    padding: 14px;
  }

  .subscription-panel {
    width: calc(100vw - 28px);
    max-height: calc(100dvh - 28px);
    border-radius: 28px;
    padding: 22px 16px 18px;
  }

  .subscription-panel::before,
  .subscription-orbit {
    display: none;
  }

  .subscription-header {
    grid-template-columns: 1fr;
    padding: 0 44px 18px 0;
  }

  .subscription-header__copy h2 {
    font-size: 30px;
  }

  .subscription-tiers {
    grid-template-columns: 1fr;
  }

  .subscription-footer {
    align-items: stretch;
    flex-direction: column;
  }

  .subscription-footer__actions {
    width: 100%;
  }

  .subscription-primary,
  .subscription-later {
    flex: 1 1 0;
    min-width: 0;
  }
}

@media (max-width: 560px) {
  .subscription-benefits {
    grid-template-columns: 1fr;
  }

  .subscription-plan {
    grid-template-columns: 22px minmax(0, 1fr);
  }

  .subscription-plan__price {
    grid-column: 2;
    text-align: left;
  }

  .subscription-plan__badges {
    right: 12px;
  }

  .subscription-footer__actions {
    flex-direction: column-reverse;
  }

  .subscription-primary,
  .subscription-later {
    width: 100%;
  }
}
</style>
