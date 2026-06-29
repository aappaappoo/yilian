<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Bell, Search } from '@element-plus/icons-vue'
import { useSessionStore } from '../stores/session'
import { useAuthStore } from '../stores/auth'
import { apiUrl } from '../utils/api'
import LoginModal from '../components/LoginModal.vue'
import RegisterModal from '../components/RegisterModal.vue'
import SidebarNav from '../components/home/SidebarNav.vue'
import CompanionHero from '../components/home/CompanionHero.vue'
import CompanionCard from '../components/home/CompanionCard.vue'
import SkillPackageCard from '../components/home/SkillPackageCard.vue'
import CompanionProgressCard from '../components/home/CompanionProgressCard.vue'
import MemoryCard from '../components/home/MemoryCard.vue'
import HeroArtTitle from '../components/home/HeroArtTitle.vue'
import SubscriptionModal from '../components/home/SubscriptionModal.vue'
import type { HomeCompanion, SkillPackage } from '../components/home/types'

interface AudienceInfo {
  id: string
  name: string
  description: string
  avatar_url: string
  vrm_url: string
  is_online: boolean
}

const router = useRouter()
const sessionStore = useSessionStore()
const authStore = useAuthStore()

const showLoginModal = ref(false)
const showRegisterModal = ref(false)
const showSubscriptionModal = ref(false)
const loading = ref(true)
const loadError = ref(false)
const audiences = ref<AudienceInfo[]>([])
const skillSectionRef = ref<HTMLElement | null>(null)

const companionProfiles: Record<string, Omit<HomeCompanion, 'image' | 'heroImage' | 'online'>> = {
  Aini: {
    id: 'Aini',
    name: '艾妮',
    displayName: '艾妮',
    subtitle: '温柔治愈系猫耳少女',
    description: '关心老人，温柔亲切，善于倾听',
    tags: ['温柔', '倾听', '陪护'],
    skills: ['天气', '出行', '火车票', '领域问答'],
    relationship: '初识',
    recent: '想陪你聊聊今天的小事',
    mood: '想陪你聊聊今天的小事',
  },
  Chuche: {
    id: 'Chuche',
    name: '初澈',
    displayName: '初澈',
    subtitle: '清冷学姐型陪伴者',
    description: '理性可靠，适合学习陪伴和情绪整理',
    tags: ['理性', '学姐', '可靠'],
    skills: ['学习计划', '知识问答', '时间管理'],
    relationship: '未认识',
    recent: '正在整理新的学习资料',
    mood: '适合安静地一起规划今天',
  },
  Liulan: {
    id: 'Liulan',
    name: '流岚',
    displayName: '流岚',
    subtitle: '活泼元气型陪伴者',
    description: '像小太阳一样存在，适合出行陪伴和日常闲聊',
    tags: ['元气', '出行', '聊天'],
    skills: ['景点推荐', '路线规划', '酒店建议'],
    relationship: '熟悉中',
    recent: '发现了周末好去处',
    mood: '想带你看看新的城市角落',
  },
  Liyin: {
    id: 'Liyin',
    name: '莉音',
    displayName: '莉音',
    subtitle: '安静梦幻型陪伴者',
    description: '适合睡前聊天、情绪安慰和回忆陪伴',
    tags: ['温柔', '睡前', '安慰'],
    skills: ['睡前故事', '情绪陪伴', '回忆聊天'],
    relationship: '已认识',
    recent: '想陪你安静地说晚安',
    mood: '想听你慢慢讲今天',
  },
  Mengli: {
    id: 'Mengli',
    name: '萌莉',
    displayName: '萌莉',
    subtitle: '甜软治愈型陪伴者',
    description: '自由活泼，擅长用轻松语气缓解压力',
    tags: ['甜软', '治愈', '轻松'],
    skills: ['日常闲聊', '情绪安慰', '小计划'],
    relationship: '未认识',
    recent: '准备了一句轻轻的鼓励',
    mood: '想给你一点轻松的能量',
  },
}

const companionImageMap: Record<string, string> = {
  Aini: '/img/audiences/Aini.png',
  Chuche: '/img/audiences/Chuche.jpg',
  Liulan: '/img/audiences/Liulan.jpg',
  Liyin: '/img/audiences/Liyin.png',
  Mengli: '/img/audiences/Mengli.jpg',
  Qingyu: '/img/audiences/Qingyu.jpg',
  Xingche: '/img/audiences/Xingche.jpg',
  Xueli: '/img/audiences/Xueli.jpg',
  Youyao: '/img/audiences/Youyao.jpg',
  Yuxian: '/img/audiences/Yuxian.jpg',
}

const skillPackages: SkillPackage[] = [
  {
    id: 'care',
    title: '生活照顾包',
    icon: '🌿',
    description: '天气、穿衣建议、用药提醒、作息提醒',
    suitable: 'Aini、Liyin',
    tone: 'green',
  },
  {
    id: 'travel',
    title: '出行规划包',
    icon: '🧳',
    description: '火车票、酒店、景点、路线规划',
    suitable: 'Aini、流岚',
    tone: 'blue',
  },
  {
    id: 'emotion',
    title: '情绪陪伴包',
    icon: '💗',
    description: '倾听、安慰、睡前故事、回忆聊天',
    suitable: '全部角色',
    tone: 'pink',
  },
  {
    id: 'knowledge',
    title: '知识问答包',
    icon: '📖',
    description: '政策、养老、长护险、补贴申请',
    suitable: 'Aini',
    tone: 'purple',
  },
]

const staticFallbackAudiences: AudienceInfo[] = Object.values(companionProfiles).map(profile => ({
  id: profile.id,
  name: profile.name,
  description: profile.description,
  avatar_url: companionImageMap[profile.id] || '/k1.png',
  vrm_url: '',
  is_online: true,
}))

const companions = computed<HomeCompanion[]>(() => {
  const source = audiences.value.length ? audiences.value : staticFallbackAudiences
  const merged = source.map((audience) => {
    const profile = companionProfiles[audience.id] ?? {
      id: audience.id,
      name: audience.name,
      displayName: audience.name,
      subtitle: '新的陪伴者',
      description: audience.description || '正在学习如何更好地陪伴你',
      tags: ['陪伴', '聊天', '成长'],
      skills: ['日常闲聊', '情绪陪伴'],
      relationship: '未认识',
      recent: '正在等待与你见面',
      mood: '想认识你',
    }
    const image = companionImageMap[audience.id] || audience.avatar_url || '/k1.png'
    return {
      ...profile,
      image,
      heroImage: image,
      online: audience.is_online,
    }
  })
  return merged.sort((a, b) => (a.id === 'Aini' ? -1 : b.id === 'Aini' ? 1 : 0))
})

const featuredCompanion = computed(() => companions.value[0] ?? null)
const displayCompanions = computed(() => companions.value.slice(0, 5))

function openLogin() {
  showRegisterModal.value = false
  showLoginModal.value = true
}

function openRegister() {
  showLoginModal.value = false
  showRegisterModal.value = true
}

function closeModals() {
  showLoginModal.value = false
  showRegisterModal.value = false
}

function openSubscription() {
  showSubscriptionModal.value = true
}

function closeSubscription() {
  showSubscriptionModal.value = false
}

function enterCompanion(companion: HomeCompanion) {
  const audience = audiences.value.find(item => item.id === companion.id)
  sessionStore.setAudience(companion.id, audience?.vrm_url || '')
  router.push(`/chat/${companion.id}`)
}

function scrollToSkills() {
  skillSectionRef.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function handleLearnSkill(skill: SkillPackage) {
  ElMessage({
    message: `已为她加入「${skill.title}」学习计划`,
    type: 'success',
    plain: true,
  })
}

function handleSubscribe(plan: { id: string; title: string; tierName: string }) {
  console.log('[SoulMeet Pro] selected subscription:', plan)
  ElMessage({
    message: `已选择「${plan.tierName} ${plan.title}」`,
    type: 'success',
    plain: true,
  })
}

onMounted(async () => {
  authStore.fetchMe()

  try {
    const resp = await fetch(apiUrl('/api/audiences'))
    if (resp.ok) {
      const data = await resp.json() as AudienceInfo[]
      audiences.value = data.map(audience => ({
        ...audience,
        avatar_url: audience.avatar_url ? apiUrl(audience.avatar_url) : '',
        vrm_url: audience.vrm_url ? apiUrl(audience.vrm_url) : '',
      }))
    } else {
      loadError.value = true
    }
  } catch (error) {
    console.error('Failed to load audiences:', error)
    loadError.value = true
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="companion-lobby">
    <div class="lobby-atmosphere" aria-hidden="true">
      <span class="glow glow-pink"></span>
      <span class="glow glow-blue"></span>
      <span class="glow glow-violet"></span>
    </div>
    <SidebarNav />

    <main class="lobby-main">
      <header class="lobby-topbar">
        <div class="topbar-spacer"></div>
        <el-input
          class="lobby-search"
          placeholder="寻找角色、技能或陪伴方式..."
          :prefix-icon="Search"
        />
        <div class="topbar-actions">
          <button type="button" class="pro-button" @click="openSubscription">订阅</button>
          <button type="button" class="bell-button" aria-label="通知">
            <el-icon><Bell /></el-icon>
          </button>
          <template v-if="authStore.isLoggedIn">
            <button type="button" class="account-button" aria-label="当前登录用户">
              {{ authStore.user?.displayName || authStore.user?.username }}
            </button>
          </template>
          <template v-else>
            <button type="button" class="account-button" @click="openLogin">登录</button>
            <button type="button" class="register-button" @click="openRegister">注册</button>
          </template>
        </div>
      </header>

      <div class="lobby-grid">
        <section class="center-column">
          <div class="lobby-title">
            <div>
              <HeroArtTitle />
              <p class="hero-subtitle">选择一位角色，进入她的房间。她会记得你，也可以学习新的技能包。</p>
            </div>
          </div>

          <div v-if="loading" class="state-card">正在整理陪伴大厅...</div>
          <div v-else-if="loadError && companions.length === 0" class="state-card">暂时没有加载到角色，请稍后重试。</div>
          <template v-else-if="featuredCompanion">
            <CompanionHero
              :companion="featuredCompanion"
              @enter="enterCompanion"
              @view-skills="scrollToSkills"
            />

            <section class="companions-section">
              <div class="section-heading">
                <div>
                  <h2>陪伴者们</h2>
                  <p>选择你的陪伴者</p>
                </div>
                <span>每位角色都能慢慢学习新的能力</span>
              </div>

              <div class="companion-grid">
                <CompanionCard
                  v-for="companion in displayCompanions"
                  :key="companion.id"
                  :companion="companion"
                  @enter="enterCompanion"
                />
              </div>
            </section>
          </template>
        </section>

        <aside class="right-rail">
          <section class="status-card">
            <span class="status-card__tag">今日小纸条</span>
            <h3>今日状态</h3>
            <p>艾妮今天想听你说说最近开心的小事。</p>
          </section>

          <CompanionProgressCard />
          <MemoryCard />

          <section ref="skillSectionRef" class="skill-panel">
            <div class="skill-panel__head">
              <h3>让她学会新的事</h3>
              <p>技能会成为她陪伴你的新方式</p>
            </div>
            <div class="skill-list">
              <SkillPackageCard
                v-for="skill in skillPackages"
                :key="skill.id"
                :skill="skill"
                @learn="handleLearnSkill"
              />
            </div>
          </section>
        </aside>
      </div>
    </main>

    <LoginModal v-if="showLoginModal" @close="closeModals" @switch-to-register="openRegister" />
    <RegisterModal v-if="showRegisterModal" @close="closeModals" @switch-to-login="openLogin" />
    <SubscriptionModal
      v-if="showSubscriptionModal"
      @close="closeSubscription"
      @subscribe="handleSubscribe"
    />
  </div>
</template>

<style scoped lang="scss">
.companion-lobby {
  position: relative;
  min-height: 100vh;
  display: flex;
  color: #3f365c;
  background:
    linear-gradient(rgba(255, 255, 255, 0.16) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.14) 1px, transparent 1px),
    radial-gradient(circle at 18% 6%, rgba(255, 216, 234, 0.8), transparent 30%),
    radial-gradient(circle at 74% 0%, rgba(221, 235, 255, 0.76), transparent 32%),
    radial-gradient(circle at 42% 98%, rgba(232, 218, 255, 0.78), transparent 28%),
    linear-gradient(135deg, #f8f3ff 0%, #fff7fb 48%, #f3f6ff 100%);
  background-size: 48px 48px, 48px 48px, auto, auto, auto, auto;
  overflow: hidden;
  font-family: var(--soulmeet-font-family);
}

.lobby-atmosphere {
  position: fixed;
  inset: 0;
  pointer-events: none;
  overflow: hidden;
  z-index: 0;
}

.glow {
  position: absolute;
  border-radius: 999px;
  filter: blur(6px);
  opacity: 0.72;
}

.glow-pink {
  width: 360px;
  height: 360px;
  left: 250px;
  top: 90px;
  background: radial-gradient(circle, rgba(255, 215, 234, 0.54), transparent 66%);
}

.glow-blue {
  width: 420px;
  height: 420px;
  right: 250px;
  top: 24px;
  background: radial-gradient(circle, rgba(221, 235, 255, 0.62), transparent 68%);
}

.glow-violet {
  width: 340px;
  height: 340px;
  right: 54px;
  bottom: 90px;
  background: radial-gradient(circle, rgba(213, 197, 255, 0.48), transparent 70%);
}

.lobby-main {
  position: relative;
  z-index: 1;
  min-width: 0;
  flex: 1;
  height: 100vh;
  padding: 26px 32px 36px;
  overflow-y: auto;
}

.lobby-topbar {
  display: grid;
  grid-template-columns: 1fr minmax(300px, 430px) auto;
  align-items: center;
  gap: 16px;
  margin-bottom: 30px;
}

.lobby-search {
  :deep(.el-input__wrapper) {
    height: 44px;
    border-radius: 999px;
    border: 1px solid rgba(226, 211, 255, 0.7);
    background: rgba(255, 255, 255, 0.54);
    box-shadow: 0 14px 34px rgba(139, 122, 230, 0.07), inset 0 1px 0 rgba(255, 255, 255, 0.78);
    backdrop-filter: blur(18px);
    padding: 0 18px;
  }

  :deep(.el-input__inner) {
    color: #766b98;
    font-weight: 600;
  }
}

.topbar-actions {
  justify-self: end;
  display: flex;
  align-items: center;
  gap: 9px;
}

.pro-button,
.bell-button,
.account-button,
.register-button {
  height: 44px;
  border-radius: 999px;
  border: 1px solid rgba(220, 204, 255, 0.78);
  background: rgba(255, 255, 255, 0.58);
  color: #6f5ba8;
  font-size: 13px;
  font-weight: 800;
  cursor: pointer;
  backdrop-filter: blur(14px);
  transition: transform 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;

  &:hover {
    transform: translateY(-1px);
    box-shadow: 0 12px 26px rgba(139, 122, 230, 0.12);
  }
}

.pro-button {
  padding: 0 16px;
  color: #765bd9;
  background: rgba(255, 255, 255, 0.7);
}

.bell-button {
  width: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.account-button,
.register-button {
  padding: 0 15px;
}

.register-button {
  color: #fff;
  border: 0;
  background: linear-gradient(135deg, #9c8cf0, #d9a9ff);
  box-shadow: 0 12px 28px rgba(156, 140, 240, 0.24);
}

.lobby-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 28px;
  align-items: start;
}

.center-column {
  min-width: 0;
}

.lobby-title {
  position: relative;
  isolation: isolate;
  max-width: 980px;
  margin: 8px 0 30px;
  padding: 4px 0 32px 0;

  &::before {
    content: "";
    position: absolute;
    left: -70px;
    top: -44px;
    z-index: -2;
    width: 270px;
    height: 270px;
    border-radius: 999px;
    background:
      radial-gradient(circle at 42% 40%, rgba(255, 236, 248, 0.9), transparent 32%),
      radial-gradient(circle, rgba(255, 205, 232, 0.48), transparent 72%);
    filter: blur(11px);
    pointer-events: none;
  }

  .hero-subtitle {
    max-width: 650px;
    margin: 20px 0 0 108px;
    color: #8b82a8;
    font-size: 15px;
    line-height: 1.9;
    font-weight: 600;
  }
}

.state-card {
  border-radius: 28px;
  padding: 48px;
  color: #8b82a8;
  text-align: center;
  background: rgba(255, 255, 255, 0.58);
  border: 1px solid rgba(255, 255, 255, 0.78);
}

.companions-section {
  margin-top: 26px;
  padding: 22px;
  border-radius: 34px;
  background: rgba(255, 255, 255, 0.26);
  border: 1px solid rgba(255, 255, 255, 0.52);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.58);
}

.section-heading {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 14px;

  h2 {
    margin: 0;
    color: #4c3b7c;
    font-size: 26px;
    font-weight: 900;
  }

  p,
  span {
    margin: 4px 0 0;
    color: #8b82a8;
    font-size: 13px;
    font-weight: 700;
  }
}

.companion-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 18px;
}

.right-rail {
  position: sticky;
  top: 26px;
  display: grid;
  gap: 14px;
}

.status-card,
.skill-panel {
  position: relative;
  overflow: hidden;
  border-radius: 26px;
  padding: 18px;
  background:
    radial-gradient(circle at 92% 12%, rgba(255, 216, 234, 0.78), transparent 38%),
    linear-gradient(145deg, rgba(255, 255, 255, 0.72), rgba(255, 247, 253, 0.46));
  border: 1px solid rgba(255, 255, 255, 0.78);
  box-shadow: 0 18px 42px rgba(139, 122, 230, 0.12), inset 0 1px 0 rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(20px);
}

.status-card {
  min-height: 136px;

  &::after {
    content: "";
    position: absolute;
    right: -28px;
    bottom: -36px;
    width: 116px;
    height: 116px;
    border-radius: 999px;
    background: radial-gradient(circle, rgba(221, 235, 255, 0.8), transparent 70%);
  }

  &__tag {
    position: relative;
    z-index: 1;
    display: inline-flex;
    margin-bottom: 10px;
    border-radius: 999px;
    padding: 5px 10px;
    color: #a074c9;
    background: rgba(255, 255, 255, 0.62);
    font-size: 11px;
    font-weight: 900;
  }

  h3 {
    position: relative;
    z-index: 1;
    margin: 0;
    color: #4c3b7c;
    font-size: 18px;
    font-weight: 900;
  }

  p {
    position: relative;
    z-index: 1;
    margin: 14px 0 0;
    color: #6f638c;
    font-size: 14px;
    line-height: 1.7;
    font-weight: 700;
  }
}

.skill-panel {
  scroll-margin-top: 24px;
}

.skill-panel__head {
  h3 {
    margin: 0;
    color: #4c3b7c;
    font-size: 18px;
    font-weight: 900;
  }

  p {
    margin: 6px 0 0;
    color: #8b82a8;
    font-size: 12px;
    font-weight: 700;
  }
}

.skill-list {
  display: grid;
  gap: 10px;
  margin-top: 14px;
}

@media (max-width: 1500px) {
  .companion-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 1280px) {
  .companion-lobby {
    overflow: auto;
  }

  .lobby-main {
    height: auto;
    min-height: 100vh;
  }

  .lobby-grid {
    grid-template-columns: 1fr;
  }

  .right-rail {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 980px) {
  .lobby-topbar {
    grid-template-columns: 1fr;
  }

  .topbar-spacer {
    display: none;
  }

  .topbar-actions {
    justify-self: start;
  }

  .companion-grid,
  .right-rail {
    grid-template-columns: 1fr;
  }

  .lobby-title {
    max-width: 100%;
    margin-top: 18px;
    padding-bottom: 22px;

    &::after {
      left: 30px;
      bottom: 90px;
      width: min(560px, 92%);
    }

    .hero-subtitle {
      margin-left: 0;
      font-size: 14px;
    }
  }
}
</style>
