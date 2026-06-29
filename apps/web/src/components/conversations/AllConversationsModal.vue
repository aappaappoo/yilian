<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useEscapeKey } from '../../composables/useEscapeKey'

interface KeyInfo {
  label: string
  value: string
}

interface RecentMessage {
  role: 'user' | 'assistant'
  name: string
  time: string
  text: string
}

interface ArchiveConversation {
  id: string
  icon: string
  title: string
  time: string
  createdAt: string
  updatedAt?: number
  category: string
  type: string
  rounds: number
  starred: boolean
  summary: string
  detailSummary: string
  keyInfo: KeyInfo[]
  recentMessages: RecentMessage[]
}

const props = defineProps<{
  open: boolean
  botAvatarUrl: string
  conversations?: ArchiveConversation[]
}>()

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
  (e: 'continue', conversationId: string): void
  (e: 'rename', payload: { conversationId: string; title: string }): void
  (e: 'delete', conversationId: string): void
  (e: 'toggleStar', conversationId: string): void
}>()

const searchKeyword = ref('')
const activeFilter = ref('all')
const sortDirection = ref<'desc' | 'asc'>('desc')
const selectedId = ref('travel-fuzhou-beijing')
const mobileDetailOpen = ref(false)
const toastText = ref('')
const confirmDeleteId = ref<string | null>(null)
let toastTimer: ReturnType<typeof setTimeout> | null = null

const defaultConversations = ref<ArchiveConversation[]>([
  {
    id: 'travel-fuzhou-beijing',
    icon: '✈️',
    title: '福州-北京出行规划',
    time: '14:23',
    createdAt: '今天 14:23',
    category: '旅行出行',
    type: '任务对话',
    rounds: 6,
    starred: true,
    summary: '帮我查一下明天福州到北京的车次和机票...',
    detailSummary: '你让 Aini 查询从福州到北京的出行方案，Aini 为你比较了高铁和航班方案，并推荐了合适的出发时间和酒店建议。',
    keyInfo: [
      { label: '出发地', value: '福州' },
      { label: '目的地', value: '北京' },
      { label: '出发时间', value: '明天' },
      { label: '需求', value: '交通 + 酒店 + 景点建议' },
    ],
    recentMessages: [
      { role: 'user', name: '你', time: '14:23', text: '帮我查一下明天福州到北京的车次和机票，顺便推荐一下酒店。' },
      { role: 'assistant', name: 'Aini', time: '14:23', text: '好的！我为你查询了明天从福州到北京的高铁和航班方案，还会推荐几家合适的酒店。' },
    ],
  },
  {
    id: 'beijing-weather',
    icon: '☁️',
    title: '北京天气怎么样？',
    time: '14:10',
    createdAt: '今天 14:10',
    category: '生活助理',
    type: '天气',
    rounds: 4,
    starred: false,
    summary: '北京今天多云，气温12°C，早晚温差较大...',
    detailSummary: '你询问北京天气，Aini 汇总了气温、风力、空气质量，并提醒早晚温差和出门携带外套。',
    keyInfo: [
      { label: '城市', value: '北京' },
      { label: '天气', value: '多云' },
      { label: '气温', value: '12°C' },
      { label: '提醒', value: '早晚温差较大' },
    ],
    recentMessages: [
      { role: 'user', name: '你', time: '14:10', text: '北京天气怎么样？' },
      { role: 'assistant', name: 'Aini', time: '14:10', text: '北京今天多云，气温偏低，早晚建议多穿一件外套。' },
    ],
  },
  {
    id: 'outfit-suggestion',
    icon: '👕',
    title: '穿衣建议',
    time: '14:05',
    createdAt: '今天 14:05',
    category: '生活助理',
    type: '天气穿搭',
    rounds: 3,
    starred: false,
    summary: '建议您携带一件薄外套和长裤，早晚温差...',
    detailSummary: 'Aini 根据当前天气为你推荐了轻便保暖的穿搭，并提醒注意早晚温差。',
    keyInfo: [
      { label: '场景', value: '日常出门' },
      { label: '上装', value: '薄外套' },
      { label: '下装', value: '长裤' },
      { label: '提醒', value: '注意温差' },
    ],
    recentMessages: [
      { role: 'user', name: '你', time: '14:05', text: '今天出门穿什么比较合适？' },
      { role: 'assistant', name: 'Aini', time: '14:05', text: '建议穿长裤，外面搭一件薄外套，既舒服也不容易着凉。' },
    ],
  },
  {
    id: 'hotel-recommend',
    icon: '🏨',
    title: '酒店推荐',
    time: '昨天',
    createdAt: '昨天 18:40',
    category: '旅行出行',
    type: '任务对话',
    rounds: 5,
    starred: true,
    summary: '根据您的行程，我为您推荐了三家酒店...',
    detailSummary: '你让 Aini 根据预算和位置推荐酒店，Aini 结合交通便利度、预算和评价筛选了合适住宿。',
    keyInfo: [
      { label: '位置', value: '北京城区' },
      { label: '预算', value: '中等' },
      { label: '偏好', value: '交通方便' },
      { label: '结果', value: '推荐 3 家' },
    ],
    recentMessages: [
      { role: 'user', name: '你', time: '昨天', text: '帮我推荐一下北京交通方便的酒店。' },
      { role: 'assistant', name: 'Aini', time: '昨天', text: '我为你挑了三家位置比较方便、评价也不错的酒店。' },
    ],
  },
  {
    id: 'spot-recommend',
    icon: '📍',
    title: '景点推荐',
    time: '昨天',
    createdAt: '昨天 16:20',
    category: '旅行出行',
    type: '生活助理',
    rounds: 4,
    starred: false,
    summary: '如果时间充裕，可以去天安门、故宫和颐和园...',
    detailSummary: 'Aini 根据你的行程时间推荐了北京适合游玩的景点，并给出轻松不赶路的安排。',
    keyInfo: [
      { label: '城市', value: '北京' },
      { label: '景点', value: '天安门 / 故宫 / 颐和园' },
      { label: '节奏', value: '轻松游玩' },
      { label: '偏好', value: '经典路线' },
    ],
    recentMessages: [
      { role: 'user', name: '你', time: '昨天', text: '北京有哪些必去景点？' },
      { role: 'assistant', name: 'Aini', time: '昨天', text: '如果第一次去北京，可以优先安排天安门、故宫和颐和园。' },
    ],
  },
  {
    id: 'tired-recently',
    icon: '🌙',
    title: '最近有点累',
    time: '前天',
    createdAt: '前天 22:18',
    category: '情感陪伴',
    type: '私密对话',
    rounds: 8,
    starred: true,
    summary: '你说最近有点累，Aini 陪你慢慢聊了压力和休息...',
    detailSummary: '你向 Aini 表达最近有些疲惫，Aini 陪你梳理了压力来源，并用温柔的方式提醒你休息和照顾自己。',
    keyInfo: [
      { label: '情绪', value: '疲惫' },
      { label: '关系', value: '私密陪伴' },
      { label: '重点', value: '压力与休息' },
      { label: 'Aini 提醒', value: '先好好睡一觉' },
    ],
    recentMessages: [
      { role: 'user', name: '你', time: '前天', text: '最近有点累，感觉什么都不太想做。' },
      { role: 'assistant', name: 'Aini', time: '前天', text: '辛苦啦。先不用勉强自己，我们慢慢把事情放下来一点，好吗？' },
    ],
  },
])

const conversationItems = computed(() => Array.isArray(props.conversations) ? props.conversations : defaultConversations.value)

const filterDefinitions = [
  { id: 'all', icon: 'i-carbon-chat', label: '全部对话' },
  { id: 'today', icon: 'i-carbon-calendar', label: '今天' },
  { id: 'week', icon: 'i-carbon-time', label: '最近 7 天' },
  { id: 'month', icon: 'i-carbon-recently-viewed', label: '最近 30 天' },
  { id: 'starred', icon: 'i-carbon-favorite', label: '收藏对话' },
  { id: 'task', icon: 'i-carbon-task', label: '任务对话' },
  { id: 'emotion', icon: 'i-carbon-face-satisfied', label: '情感陪伴' },
  { id: 'travel', icon: 'i-carbon-map', label: '旅行出行' },
  { id: 'life', icon: 'i-carbon-home', label: '生活助理' },
]

const sortLabel = computed(() => sortDirection.value === 'desc' ? '按时间降序' : '按时间升序')
const sortIcon = computed(() => sortDirection.value === 'desc' ? 'i-carbon-chevron-down' : 'i-carbon-chevron-up')
const hasSearchKeyword = computed(() => normalizeSearchText(searchKeyword.value).length > 0)

function normalizeSearchText(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, '')
    .trim()
}

function searchHaystack(item: ArchiveConversation): string {
  const recentText = item.recentMessages
    .map(message => `${message.name}${message.time}${message.text}`)
    .join('')
  const keyInfoText = item.keyInfo
    .map(info => `${info.label}${info.value}`)
    .join('')
  return normalizeSearchText([
    item.title,
    item.summary,
    item.detailSummary,
    item.category,
    item.type,
    item.time,
    item.createdAt,
    keyInfoText,
    recentText,
  ].join(''))
}

function matchesSearchKeyword(item: ArchiveConversation, keyword: string): boolean {
  const normalizedKeyword = normalizeSearchText(keyword)
  if (!normalizedKeyword) return true

  const haystack = searchHaystack(item)
  if (haystack.includes(normalizedKeyword)) return true

  const characters = Array.from(new Set(normalizedKeyword))
  return characters.every(character => haystack.includes(character))
}

function parseClockMinutes(source: string): number {
  const matched = source.match(/(\d{1,2}):(\d{2})/)
  if (!matched) return 0
  return Number(matched[1]) * 60 + Number(matched[2])
}

function conversationTimestamp(item: ArchiveConversation): number {
  if (typeof item.updatedAt === 'number' && Number.isFinite(item.updatedAt)) {
    return item.updatedAt
  }

  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const base = today.getTime()
  const clockMs = parseClockMinutes(`${item.createdAt} ${item.time}`) * 60 * 1000

  if (item.createdAt.startsWith('前天')) return base - 2 * 24 * 60 * 60 * 1000 + clockMs
  if (item.createdAt.startsWith('昨天')) return base - 24 * 60 * 60 * 1000 + clockMs
  if (item.createdAt.startsWith('今天')) return base + clockMs
  return clockMs || base
}

function matchesFilter(item: ArchiveConversation, filterId: string): boolean {
  const timestamp = conversationTimestamp(item)
  const now = Date.now()
  const dayMs = 24 * 60 * 60 * 1000

  return filterId === 'all'
    || (filterId === 'today' && timestamp >= new Date().setHours(0, 0, 0, 0))
    || (filterId === 'week' && now - timestamp <= 7 * dayMs)
    || (filterId === 'month' && now - timestamp <= 30 * dayMs)
    || (filterId === 'starred' && item.starred)
    || (filterId === 'task' && item.type === '任务对话')
    || (filterId === 'emotion' && item.category === '情感陪伴')
    || (filterId === 'travel' && item.category === '旅行出行')
    || (filterId === 'life' && item.category === '生活助理')
}

const filters = computed(() => filterDefinitions.map(filter => ({
  ...filter,
  count: conversationItems.value.filter(item => matchesFilter(item, filter.id)).length,
})))

const filteredConversations = computed(() => {
  return conversationItems.value
    .filter(item => matchesFilter(item, activeFilter.value) && matchesSearchKeyword(item, searchKeyword.value))
    .map((item, index) => ({ item, index }))
    .sort((left, right) => {
      const direction = sortDirection.value === 'desc' ? -1 : 1
      const diff = conversationTimestamp(left.item) - conversationTimestamp(right.item)
      return diff === 0 ? left.index - right.index : diff * direction
    })
    .map(entry => entry.item)
})

const selectedConversation = computed(() => {
  return filteredConversations.value.find(item => item.id === selectedId.value)
    ?? filteredConversations.value[0]
})

watch(filteredConversations, (items) => {
  if (items.length === 0) {
    selectedId.value = ''
    mobileDetailOpen.value = false
    return
  }

  if (!items.some(item => item.id === selectedId.value)) {
    selectedId.value = items[0].id
  }
}, { immediate: true })

watch(() => props.open, (open) => {
  if (open) {
    mobileDetailOpen.value = false
  }
})

function close() {
  emit('update:open', false)
  mobileDetailOpen.value = false
}

useEscapeKey(() => {
  if (confirmDeleteId.value) {
    confirmDeleteId.value = null
    return
  }
  close()
}, {
  enabled: () => props.open,
  priority: 72,
})

function showToast(message: string) {
  toastText.value = message
  if (toastTimer !== null) {
    clearTimeout(toastTimer)
  }
  toastTimer = setTimeout(() => {
    toastText.value = ''
    toastTimer = null
  }, 1800)
}

function selectConversation(id: string) {
  selectedId.value = id
  mobileDetailOpen.value = true
}

function toggleSortDirection() {
  sortDirection.value = sortDirection.value === 'desc' ? 'asc' : 'desc'
}

function toggleStar(id: string) {
  if (props.conversations?.length) {
    emit('toggleStar', id)
    return
  }

  const item = defaultConversations.value.find(conversation => conversation.id === id)
  if (item) {
    item.starred = !item.starred
  }
}

function continueConversation() {
  if (!selectedConversation.value) return
  emit('continue', selectedConversation.value.id)
  close()
}

function requestDelete(id: string) {
  confirmDeleteId.value = id
}

function requestRename(item: ArchiveConversation) {
  emit('rename', {
    conversationId: item.id,
    title: item.title,
  })
}

function confirmDelete() {
  const id = confirmDeleteId.value
  if (!id) return
  emit('delete', id)
  if (!props.conversations?.length) {
    defaultConversations.value = defaultConversations.value.filter(item => item.id !== id)
  }
  if (selectedId.value === id) {
    selectedId.value = conversationItems.value[0]?.id ?? ''
    mobileDetailOpen.value = false
  }
  confirmDeleteId.value = null
}
</script>

<template>
  <Teleport to="body">
    <Transition name="archive-modal">
      <div v-if="open" class="archive-overlay fixed inset-0 z-[72] flex items-center justify-center overflow-hidden bg-[#35284d]/24 px-4 py-5 backdrop-blur-[3px] max-md:px-2 max-md:py-2">
        <section
          class="archive-panel relative flex h-[84vh] w-[min(84vw,1320px)] max-w-full overflow-hidden rounded-[28px] border border-white/65 bg-[#fffaff]/74 text-[#403764] shadow-[0_26px_90px_rgba(74,55,118,0.22)] backdrop-blur-2xl max-md:h-[calc(100dvh-16px)] max-md:w-[calc(100vw-16px)] max-md:rounded-[26px]"
          role="dialog"
          aria-modal="true"
          aria-label="全部对话"
        >
          <div class="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_8%_8%,rgba(228,214,255,0.78),transparent_34%),radial-gradient(circle_at_88%_0%,rgba(255,225,240,0.70),transparent_32%),linear-gradient(180deg,rgba(255,255,255,0.42),rgba(247,241,255,0.24))]"></div>

          <div class="relative flex min-h-0 w-full flex-col">
            <header class="shrink-0 px-7 pb-4 pt-7 max-md:px-4 max-md:pb-3 max-md:pt-4">
              <div class="flex items-start justify-between gap-5 max-md:block">
                <div class="flex min-w-0 items-start justify-between gap-3 max-md:w-full">
                  <div class="flex min-w-0 items-start gap-4 max-md:gap-3">
                    <span class="i-carbon-chat-bot mt-1 shrink-0 text-[34px] text-[#8f72ea] max-md:text-[27px]"></span>
                    <div class="min-w-0">
                      <h2 class="archive-title truncate text-[28px] font-semibold leading-tight text-[#43386c] max-md:text-[22px]">记忆花园</h2>
                      <p class="mt-1.5 text-sm text-[#6d658f] max-md:text-[12px] max-md:leading-5">这里收藏着你和 Aini 慢慢留下的对话</p>
                    </div>
                  </div>

                  <button
                    type="button"
                    class="hidden h-10 w-10 shrink-0 items-center justify-center rounded-full border border-white/70 bg-white/70 text-[#6f6594] shadow-sm transition hover:bg-white/90 max-md:inline-flex"
                    aria-label="关闭全部对话"
                    @click="close"
                  >
                    <span class="i-carbon-close text-xl"></span>
                  </button>
                </div>

                <div class="flex min-w-[380px] items-center gap-3 max-md:mt-3 max-md:w-full max-md:min-w-0">
                  <label class="flex h-12 min-w-0 flex-1 items-center gap-2 rounded-full border border-[#e2d5ff]/80 bg-white/55 px-4 text-[#8f84ad] shadow-inner max-md:h-11 max-md:w-full max-md:px-3">
                    <span class="i-carbon-search shrink-0 text-xl max-md:text-lg"></span>
                    <input
                      v-model="searchKeyword"
                      type="search"
                      aria-label="搜索对话记录"
                      class="min-w-0 flex-1 truncate bg-transparent text-sm text-[#514873] outline-none placeholder:text-[#a99fbd] max-md:text-[13px]"
                      placeholder="搜索对话内容、标题或关键词..."
                      @keydown.esc="searchKeyword = ''"
                    >
                  </label>
                  <button
                    type="button"
                    class="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-full border border-white/70 bg-white/64 text-[#6f6594] shadow-sm transition hover:bg-white/88 max-md:hidden"
                    aria-label="关闭全部对话"
                    @click="close"
                  >
                    <span class="i-carbon-close text-2xl max-md:text-xl"></span>
                  </button>
                </div>
              </div>
            </header>

            <div class="relative min-h-0 flex-1 px-5 pb-5 max-md:px-3 max-md:pb-3">
              <div class="archive-content grid h-full min-h-0 grid-cols-[200px_390px_minmax(0,1fr)] overflow-hidden rounded-[24px] border border-white/60 bg-white/34 max-xl:grid-cols-[180px_350px_minmax(0,1fr)] max-md:block max-md:w-full max-md:max-w-full max-md:overflow-x-hidden max-md:overflow-y-auto">
                <aside class="archive-filter-pane border-r border-[#e8e0f7]/80 p-4 max-md:relative max-md:w-full max-md:max-w-full max-md:overflow-hidden max-md:border-r-0 max-md:p-3">
                  <div class="pointer-events-none absolute right-0 top-3 z-10 hidden h-10 w-10 bg-gradient-to-l from-[#fffaff]/95 to-transparent max-md:block"></div>
                  <div class="scrollbar-none flex flex-col gap-2 max-md:w-full max-md:max-w-full max-md:flex-row max-md:gap-2 max-md:overflow-x-auto max-md:overscroll-x-contain max-md:whitespace-nowrap max-md:pb-1">
                    <button
                      v-for="filter in filters"
                      :key="filter.id"
                      type="button"
                      class="flex h-11 shrink-0 items-center gap-2 rounded-2xl px-3 text-sm transition max-md:h-10 max-md:min-w-max max-md:rounded-full max-md:px-3.5 max-md:text-[13px]"
                      :class="activeFilter === filter.id
                        ? 'bg-gradient-to-r from-[#a48af0] to-[#7d62df] text-white shadow-[0_10px_22px_rgba(126,98,223,0.22)]'
                        : 'text-[#675f88] hover:bg-white/58'"
                      @click="activeFilter = filter.id"
                    >
                      <span :class="filter.icon"></span>
                      <span class="min-w-[72px] text-left max-md:min-w-0">{{ filter.label }}</span>
                      <span class="ml-auto text-xs opacity-85 max-md:ml-0">{{ filter.count }}</span>
                    </button>
                  </div>
                </aside>

                <main class="archive-list-pane min-h-0 border-r border-[#e8e0f7]/80 p-4 max-md:border-r-0 max-md:p-3" :class="mobileDetailOpen ? 'max-md:hidden' : ''">
                  <div class="mb-3 flex items-center justify-between px-1">
                    <button
                      type="button"
                      class="inline-flex items-center gap-1 rounded-full px-3 py-1.5 text-sm text-[#6b628a] transition hover:bg-white/58"
                      :aria-label="`切换为${sortDirection === 'desc' ? '按时间升序' : '按时间降序'}`"
                      :title="sortLabel"
                      @click="toggleSortDirection"
                    >
                      {{ sortLabel }}
                      <span :class="sortIcon"></span>
                    </button>
                    <span class="text-xs text-[#9b91b7]">{{ filteredConversations.length }} 条</span>
                  </div>

                  <div v-if="filteredConversations.length" class="space-y-3 overflow-y-auto pr-1 max-md:overflow-visible">
                    <article
                      v-for="item in filteredConversations"
                      :key="item.id"
                      class="archive-item group cursor-pointer rounded-[20px] border p-4 transition duration-200 hover:-translate-y-0.5 hover:border-[#cfbfff]"
                      :class="selectedConversation?.id === item.id
                        ? 'border-[#a990f4] bg-[#f2edff]/70 shadow-[0_12px_28px_rgba(126,98,223,0.13)]'
                        : 'border-white/65 bg-white/52 shadow-[0_8px_22px_rgba(100,78,150,0.08)]'"
                      @click="selectConversation(item.id)"
                    >
                      <div class="min-w-0">
                        <div class="flex items-start gap-2">
                          <h3 class="min-w-0 flex-1 truncate text-[15px] font-semibold text-[#403764]">{{ item.title }}</h3>
                          <span class="shrink-0 text-xs text-[#9b91b7]">{{ item.time }}</span>
                        </div>
                        <p class="mt-2 line-clamp-2 text-[13px] leading-5 text-[#746d94]">{{ item.summary }}</p>
                      </div>
                      <div class="mt-3 flex items-center gap-2">
                        <span class="rounded-lg bg-[#eeeaff]/80 px-2 py-1 text-xs text-[#7d70aa]">{{ item.category }}</span>
                        <span class="rounded-lg bg-[#eeeaff]/80 px-2 py-1 text-xs text-[#7d70aa]">{{ item.type }}</span>
                        <span class="text-xs text-[#8a82a6]">{{ item.rounds }} 轮对话</span>
                        <div class="ml-auto flex shrink-0 items-center gap-1.5">
                          <button
                            class="archive-action-button archive-action-button--rename"
                            aria-label="重命名这段对话"
                            title="重命名"
                            @click.stop="requestRename(item)"
                          >
                            <span class="i-carbon-edit"></span>
                          </button>
                          <button class="archive-action-button archive-action-button--star" :class="item.starred ? 'text-[#f3b63d]' : 'text-[#b8b0cf]'" @click.stop="toggleStar(item.id)">
                            <span :class="item.starred ? 'i-carbon-star-filled' : 'i-carbon-star'"></span>
                          </button>
                        </div>
                      </div>
                    </article>
                  </div>

                  <div v-else class="flex h-[360px] flex-col items-center justify-center text-center">
                    <span class="i-carbon-search text-4xl text-[#c6bddf]"></span>
                    <p class="mt-3 text-sm font-medium text-[#6d638c]">没有找到相关对话</p>
                    <p class="mt-1 text-xs text-[#9b91b7]">换个关键词试试看。</p>
                  </div>
                </main>

                <section class="archive-detail-pane min-h-0 overflow-y-auto p-5 max-md:p-3" :class="mobileDetailOpen ? '' : 'max-md:hidden'">
                  <template v-if="selectedConversation">
                    <div class="mb-4 hidden max-md:flex">
                      <button class="inline-flex items-center gap-1 rounded-full bg-white/62 px-3 py-2 text-sm text-[#675f88]" @click="mobileDetailOpen = false">
                        <span class="i-carbon-chevron-left"></span>
                        返回列表
                      </button>
                    </div>

                    <div class="flex items-start justify-between gap-4">
                      <div class="min-w-0">
                        <h3 class="text-[24px] font-semibold text-[#403764] max-md:text-xl">
                          <span class="mr-2">{{ selectedConversation.icon }}</span>{{ selectedConversation.title }}
                        </h3>
                        <div class="mt-4 flex flex-wrap gap-x-8 gap-y-2 text-sm text-[#756d96]">
                          <span>创建时间：{{ selectedConversation.createdAt }}</span>
                          <span>对话类型：{{ selectedConversation.category }} / {{ selectedConversation.type }}</span>
                          <span>对话轮数：{{ selectedConversation.rounds }}轮</span>
                        </div>
                      </div>
                      <button class="text-2xl" :class="selectedConversation.starred ? 'text-[#f3b63d]' : 'text-[#b8b0cf]'" @click="toggleStar(selectedConversation.id)">
                        <span :class="selectedConversation.starred ? 'i-carbon-star-filled' : 'i-carbon-star'"></span>
                      </button>
                    </div>

                    <div class="mt-6 border-t border-[#e8e0f7]/80 pt-5">
                      <h4 class="text-sm font-semibold text-[#403764]">对话摘要</h4>
                      <p class="mt-3 text-sm leading-7 text-[#6f6790]">{{ selectedConversation.detailSummary }}</p>
                    </div>

                    <div class="archive-info mt-5 rounded-[20px] border border-[#e5ddf3]/85 bg-white/42 p-4">
                      <h4 class="text-sm font-semibold text-[#403764]">关键信息</h4>
                      <div class="mt-4 grid grid-cols-2 gap-3 max-md:grid-cols-1">
                        <div v-for="info in selectedConversation.keyInfo" :key="info.label" class="flex items-center gap-2 text-sm text-[#6d638c]">
                          <span class="i-carbon-location text-[#8f72ea]"></span>
                          <span>{{ info.label }}：{{ info.value }}</span>
                        </div>
                      </div>
                    </div>

                    <div class="mt-5 border-t border-[#e8e0f7]/80 pt-5">
                      <h4 class="text-sm font-semibold text-[#403764]">最近消息</h4>
                      <div class="mt-4 space-y-3">
                        <div v-for="message in selectedConversation.recentMessages" :key="`${message.role}-${message.time}`" class="flex gap-3">
                          <img v-if="message.role === 'assistant'" :src="botAvatarUrl" alt="Aini" class="h-9 w-9 rounded-full">
                          <div v-else class="flex h-9 w-9 items-center justify-center rounded-full bg-[#efeaff] text-sm text-[#7d65d9]">你</div>
                          <div class="min-w-0 flex-1">
                            <p class="text-xs text-[#9b91b7]">{{ message.name }} · {{ message.time }}</p>
                            <p class="mt-1 rounded-2xl bg-white/50 px-4 py-3 text-sm leading-6 text-[#625a82]">{{ message.text }}</p>
                          </div>
                        </div>
                      </div>
                    </div>

                    <div class="mt-6 flex flex-wrap gap-3 max-md:sticky max-md:bottom-0 max-md:-mx-3 max-md:bg-[#fffaff]/80 max-md:px-3 max-md:py-3 max-md:backdrop-blur-xl">
                      <button class="h-11 rounded-full bg-gradient-to-r from-[#a48af0] to-[#7d62df] px-8 text-sm font-semibold text-white shadow-[0_10px_22px_rgba(126,98,223,0.22)] max-md:flex-1" @click="continueConversation">继续对话</button>
                      <button class="h-11 rounded-full border border-[#d9cdf7] bg-white/52 px-5 text-sm text-[#6b5ea0]" @click="toggleStar(selectedConversation.id)">
                        {{ selectedConversation.starred ? '取消收藏' : '收藏' }}
                      </button>
                      <button class="h-11 rounded-full border border-[#d9cdf7] bg-white/52 px-5 text-sm text-[#6b5ea0]" @click="requestRename(selectedConversation)">重命名</button>
                      <button class="h-11 rounded-full border border-[#efb8c5] bg-white/42 px-5 text-sm text-[#d85d78]" @click="requestDelete(selectedConversation.id)">删除</button>
                    </div>
                  </template>

                  <div v-else class="flex h-full flex-col items-center justify-center text-center">
                    <span class="i-carbon-chat text-5xl text-[#c6bddf]"></span>
                    <p class="mt-3 text-sm font-medium text-[#6d638c]">{{ hasSearchKeyword ? '没有找到匹配的对话' : '还没有更多对话' }}</p>
                    <p class="mt-1 text-xs text-[#9b91b7]">{{ hasSearchKeyword ? '换个关键词试试看。' : '和 Aini 多聊聊，这里会慢慢变成你们的专属记忆。' }}</p>
                  </div>
                </section>
              </div>
            </div>
          </div>

          <Transition name="toast">
            <div v-if="toastText" class="absolute bottom-8 left-1/2 z-20 -translate-x-1/2 rounded-full bg-[#3f3568]/84 px-5 py-3 text-sm text-white shadow-[0_12px_28px_rgba(65,53,104,0.22)] backdrop-blur-xl">
              {{ toastText }}
            </div>
          </Transition>

          <div v-if="confirmDeleteId" class="absolute inset-0 z-30 flex items-center justify-center bg-[#40325c]/18 px-4 backdrop-blur-[2px]">
            <div class="confirm-card w-[360px] rounded-[24px] border border-white/70 bg-[#fffaff]/90 p-5 text-center shadow-[0_18px_46px_rgba(72,55,110,0.20)]">
              <p class="text-base font-semibold text-[#443a68]">确定删除这段对话吗？</p>
              <p class="mt-2 text-sm leading-6 text-[#756d96]">删除后将无法恢复。</p>
              <div class="mt-5 flex gap-3">
                <button class="h-10 flex-1 rounded-full bg-white/70 text-sm text-[#6b5ea0]" @click="confirmDeleteId = null">取消</button>
                <button class="h-10 flex-1 rounded-full border border-[#efb8c5] bg-[#fff0f4] text-sm text-[#d85d78]" @click="confirmDelete">确认删除</button>
              </div>
            </div>
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped lang="scss">
.archive-overlay {
  font-family: var(--soulmeet-font-family);
  background:
    radial-gradient(circle at 16% 8%, rgba(255, 215, 234, 0.2), transparent 34%),
    radial-gradient(circle at 84% 4%, rgba(221, 235, 255, 0.22), transparent 36%),
    rgba(63, 54, 92, 0.16);
}

.archive-panel {
  border-color: rgba(255, 255, 255, 0.78);
  background:
    radial-gradient(circle at 12% 8%, rgba(255, 247, 253, 0.72), transparent 28%),
    radial-gradient(circle at 88% 0%, rgba(243, 246, 255, 0.78), transparent 30%),
    rgba(247, 246, 251, 0.92);
  box-shadow: 0 28px 76px rgba(93, 80, 140, 0.16), inset 0 1px 0 rgba(255, 255, 255, 0.86);

  :deep(button),
  :deep(input) {
    font-family: inherit;
  }
}

.archive-title {
  color: #4a4a6a;
}

.archive-content {
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.58), rgba(251, 250, 255, 0.42)),
    rgba(255, 255, 255, 0.36);
  box-shadow: 0 12px 36px rgba(110, 94, 160, 0.08), inset 0 1px 0 rgba(255, 255, 255, 0.72);
}

.archive-filter-pane,
.archive-list-pane,
.archive-detail-pane {
  background: rgba(251, 250, 255, 0.34);
  backdrop-filter: blur(18px);
}

.archive-item {
  backdrop-filter: blur(16px);
  box-shadow: 0 8px 22px rgba(110, 94, 160, 0.08), inset 0 1px 0 rgba(255, 255, 255, 0.72);
}

.archive-action-button {
  display: inline-flex;
  width: 30px;
  height: 30px;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(226, 214, 248, 0.82);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.54);
  color: #8c7ab6;
  font-size: 16px;
  transition: background 0.18s ease, color 0.18s ease, transform 0.18s ease;
}

.archive-action-button:hover {
  transform: translateY(-1px);
}

.archive-action-button--rename:hover {
  background: rgba(245, 239, 255, 0.9);
  color: #7d62df;
}

.archive-action-button--star {
  font-size: 18px;
}

.archive-info,
.confirm-card {
  background:
    linear-gradient(145deg, rgba(255, 255, 255, 0.7), rgba(251, 250, 255, 0.52)),
    rgba(255, 255, 255, 0.46);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.72);
}

.archive-panel :deep(button[class*="from-[#a48af0]"]) {
  background: linear-gradient(90deg, #efe9ff, #ddd3ff) !important;
  color: #6e5ec4 !important;
  box-shadow: 0 10px 22px rgba(110, 94, 160, 0.12) !important;
}

.scrollbar-none {
  scrollbar-width: none;
}

.scrollbar-none::-webkit-scrollbar {
  display: none;
}

.archive-modal-enter-active,
.archive-modal-leave-active {
  transition: opacity 0.24s ease, transform 0.28s ease;
}

.archive-modal-enter-from,
.archive-modal-leave-to {
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
