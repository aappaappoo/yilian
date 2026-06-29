import type { SkillPack } from '../components/skills/types'

export type ProgressSkillLogoKind =
  | 'weather'
  | 'train'
  | 'travel'
  | 'food'
  | 'hotel'
  | 'flight'
  | 'time'
  | 'reminder'
  | 'default'

type AiniSkillPack = SkillPack & {
  learnedIcon?: string
  logoKind: ProgressSkillLogoKind
}

export const AINI_SKILL_PACKS: AiniSkillPack[] = [
  {
    id: 'weather-current',
    title: '天气查询',
    description: '查询城市天气，并给出贴心出行提醒',
    category: '生活助理',
    tags: ['已接入', '实时信息'],
    badge: '已掌握',
    priceLabel: '已学习',
    status: 'learned',
    actionText: '已学习',
    icon: '🌦️',
    learnedIcon: 'i-carbon-partly-cloudy',
    logoKind: 'weather',
    accent: 'bg-[radial-gradient(circle_at_20%_20%,rgba(226,218,255,0.62),transparent_50%)]',
  },
  {
    id: 'train-ticket',
    title: '车票查询',
    description: '查询火车、高铁和动车车次信息',
    category: '旅行出行',
    tags: ['已接入', '火车票'],
    badge: '已掌握',
    priceLabel: '已学习',
    status: 'learned',
    actionText: '已学习',
    icon: '🚄',
    learnedIcon: 'i-carbon-train',
    logoKind: 'train',
    accent: 'bg-[radial-gradient(circle_at_20%_20%,rgba(205,230,255,0.62),transparent_50%)]',
  },
  {
    id: 'light-travel-plan',
    title: '轻量旅游规划',
    description: '把景点、美食和住宿建议串成轻量行程',
    category: '旅行出行',
    tags: ['已接入', '轻量攻略'],
    badge: '已掌握',
    priceLabel: '已学习',
    status: 'learned',
    actionText: '已学习',
    icon: '🗺️',
    learnedIcon: 'i-carbon-map',
    logoKind: 'travel',
    accent: 'bg-[radial-gradient(circle_at_20%_20%,rgba(207,239,225,0.56),transparent_50%)]',
  },
  {
    id: 'food-search',
    title: '美食查询',
    description: '按地点查找附近餐厅、小吃和咖啡店',
    category: '本地探索',
    tags: ['已接入', '地图检索'],
    badge: '已掌握',
    priceLabel: '已学习',
    status: 'learned',
    actionText: '已学习',
    icon: '🍜',
    learnedIcon: 'i-carbon-restaurant',
    logoKind: 'food',
    accent: 'bg-[radial-gradient(circle_at_20%_20%,rgba(255,220,236,0.60),transparent_50%)]',
  },
  {
    id: 'lodging-search',
    title: '住宿查询',
    description: '按城市、地标或附近位置查询酒店民宿',
    category: '本地探索',
    tags: ['已接入', '地图检索'],
    badge: '已掌握',
    priceLabel: '已学习',
    status: 'learned',
    actionText: '已学习',
    icon: '🏨',
    learnedIcon: 'i-carbon-hotel',
    logoKind: 'hotel',
    accent: 'bg-[radial-gradient(circle_at_20%_20%,rgba(255,224,188,0.48),transparent_50%)]',
  },
  {
    id: 'attraction-search',
    title: '景点查询',
    description: '查询附近或目的地的景点与位置参考',
    category: '本地探索',
    tags: ['已接入', '地图检索'],
    badge: '已掌握',
    priceLabel: '已学习',
    status: 'learned',
    actionText: '已学习',
    icon: '🎡',
    learnedIcon: 'i-carbon-location-heart',
    logoKind: 'travel',
    accent: 'bg-[radial-gradient(circle_at_20%_20%,rgba(214,236,255,0.58),transparent_50%)]',
  },
  {
    id: 'private-companion',
    title: '私密陪伴',
    description: '更懂情绪与心事的深度聊天',
    category: '陪伴关系',
    tags: ['陪伴向', '需记忆权限'],
    priceLabel: '未学习',
    status: 'paid',
    actionText: '去学习',
    icon: '💗',
    logoKind: 'default',
    accent: 'bg-[radial-gradient(circle_at_22%_22%,rgba(255,197,225,0.58),transparent_48%)]',
  },
  {
    id: 'flight-search',
    title: '机票查询',
    description: '查询航班与机票价格',
    category: '旅行出行',
    tags: ['待接入', '出行'],
    priceLabel: '未学习',
    status: 'member-free',
    actionText: '去学习',
    icon: '✈️',
    logoKind: 'flight',
    accent: 'bg-[radial-gradient(circle_at_20%_20%,rgba(205,230,255,0.62),transparent_50%)]',
  },
  {
    id: 'aini-daily-album',
    title: 'Aini 日常相册',
    description: '解锁虚拟生活照与日常分享',
    category: 'VIP专属',
    tags: ['VIP专属', '陪伴向'],
    priceLabel: '未学习',
    status: 'vip',
    actionText: '让她学习',
    icon: '📷',
    logoKind: 'default',
    accent: 'bg-[radial-gradient(circle_at_20%_20%,rgba(255,220,236,0.60),transparent_50%)]',
  },
]

export const AINI_LEARNED_SKILLS = AINI_SKILL_PACKS
  .filter(skill => skill.status === 'learned')
  .map(skill => ({
    label: skill.title,
    icon: skill.learnedIcon || 'i-carbon-checkmark',
  }))

const EXACT_SKILL_ALIASES: Record<string, string> = {
  global_weather: 'weather-current',
  aini_weather: 'weather-current',
  realtime_weather: 'weather-current',
  weather_query: 'weather-current',
  weather_current: 'weather-current',
  'weather.current': 'weather-current',
  天气查询: 'weather-current',
  实时天气查询: 'weather-current',

  aini_train_ticket: 'train-ticket',
  train_ticket: 'train-ticket',
  train_ticket_query: 'train-ticket',
  'train_ticket.query': 'train-ticket',
  车票查询: 'train-ticket',
  车次查询: 'train-ticket',
  火车票查询: 'train-ticket',

  aini_travel_itinerary: 'light-travel-plan',
  travel_itinerary: 'light-travel-plan',
  'travel_itinerary.plan': 'light-travel-plan',
  itinerary_compose: 'light-travel-plan',
  'itinerary.compose': 'light-travel-plan',
  light_travel_plan: 'light-travel-plan',
  轻量旅游规划: 'light-travel-plan',
  轻量旅游攻略: 'light-travel-plan',
  旅游规划: 'light-travel-plan',

  food_search: 'food-search',
  local_search_poi: 'food-search',
  'local_search.poi': 'food-search',
  美食查询: 'food-search',
  美食推荐: 'food-search',
  餐厅查询: 'food-search',
  餐厅推荐: 'food-search',

  lodging_search: 'lodging-search',
  hotel_search: 'lodging-search',
  hotel_availability: 'lodging-search',
  'hotel.availability': 'lodging-search',
  住宿查询: 'lodging-search',
  酒店查询: 'lodging-search',
  酒店推荐: 'lodging-search',

  attraction_search: 'attraction-search',
  scenic_spot_search: 'attraction-search',
  scenic_detail: 'attraction-search',
  'scenic.detail': 'attraction-search',
  景点查询: 'attraction-search',
  景点推荐: 'attraction-search',
  景点搜索: 'attraction-search',

  flight: 'flight-search',
  flight_search: 'flight-search',
  机票查询: 'flight-search',
  航班查询: 'flight-search',
}

const AUXILIARY_SKILLS: Record<string, { title: string, logoKind: ProgressSkillLogoKind, icon?: string }> = {
  'current_time.query': { title: '向光校时', logoKind: 'time', icon: 'i-carbon-time' },
  current_time: { title: '向光校时', logoKind: 'time', icon: 'i-carbon-time' },
  global_reminder: { title: '提醒设置', logoKind: 'reminder', icon: 'i-carbon-reminder' },
  reminder: { title: '提醒设置', logoKind: 'reminder', icon: 'i-carbon-reminder' },
  global_knowledge_query: { title: '领域问答', logoKind: 'default', icon: 'i-carbon-notebook-reference' },
  aini_domain_qa: { title: '领域问答', logoKind: 'default', icon: 'i-carbon-notebook-reference' },
  weather_forecast: { title: '天气预报', logoKind: 'weather', icon: 'i-carbon-rain-heavy' },
  'weather.forecast': { title: '天气预报', logoKind: 'weather', icon: 'i-carbon-rain-heavy' },
  place_resolve: { title: '地点解析', logoKind: 'travel', icon: 'i-carbon-location' },
  'place.resolve': { title: '地点解析', logoKind: 'travel', icon: 'i-carbon-location' },
  poi_detail: { title: '地点详情', logoKind: 'travel', icon: 'i-carbon-information' },
  'poi.detail': { title: '地点详情', logoKind: 'travel', icon: 'i-carbon-information' },
  poi_rank: { title: '推荐排序', logoKind: 'travel', icon: 'i-carbon-list-numbered' },
  'poi.rank': { title: '推荐排序', logoKind: 'travel', icon: 'i-carbon-list-numbered' },
  rail_station_resolve: { title: '车站解析', logoKind: 'train', icon: 'i-carbon-train-profile' },
  'rail.station_resolve': { title: '车站解析', logoKind: 'train', icon: 'i-carbon-train-profile' },
  rail_schedule: { title: '火车时刻', logoKind: 'train', icon: 'i-carbon-train' },
  'rail.schedule': { title: '火车时刻', logoKind: 'train', icon: 'i-carbon-train' },
  rail_availability: { title: '余票查询', logoKind: 'train', icon: 'i-carbon-ticket' },
  'rail.availability': { title: '余票查询', logoKind: 'train', icon: 'i-carbon-ticket' },
  conversation_interpreter: { title: '理解需求', logoKind: 'default', icon: 'i-carbon-in-progress' },
  task_group: { title: '任务结果', logoKind: 'default', icon: 'i-carbon-workflow-automation' },
  multi_task: { title: '组合任务', logoKind: 'default', icon: 'i-carbon-workflow-automation' },
}

function normalizeAlias(value: string): string {
  return value.trim().toLowerCase().replace(/[-\s]+/g, '_')
}

function skillById(id: string): AiniSkillPack | undefined {
  return AINI_SKILL_PACKS.find(skill => skill.id === id)
}

function matchSkillId(signature: string): string | undefined {
  const normalized = normalizeAlias(signature)
  const exact = EXACT_SKILL_ALIASES[normalized]
  if (exact) return exact

  if (/(酒店|住宿|民宿|宾馆|hotel|stay|lodging)/i.test(signature)) return 'lodging-search'
  if (/(餐厅|美食|饭店|小吃|咖啡|food|restaurant|cafe)/i.test(signature)) return 'food-search'
  if (/(景点|好玩|地标|游玩|scenic|attraction)/i.test(signature)) return 'attraction-search'
  if (/(攻略|行程|旅行规划|旅游规划|itinerary|travel[_\s-]?itinerary|trip[_\s-]?plan)/i.test(signature)) return 'light-travel-plan'
  if (/(车次|车票|火车|高铁|动车|train|ticket)/i.test(signature)) return 'train-ticket'
  if (/(天气|气温|温度|weather|穿衣|下雨|晴|多云)/i.test(signature)) return 'weather-current'
  if (/(航班|飞机|机票|flight|air)/i.test(signature)) return 'flight-search'
  return undefined
}

export function resolveProgressSkillLog(
  input: {
    rawName?: string
    skillName?: string
    description?: string
    icon?: string
    status?: string
  },
  fallbackIndex = 0,
): { title: string, logoKind: ProgressSkillLogoKind, icon?: string, canonicalId?: string } {
  const description = input.status === 'need_input' ? '' : input.description
  const parts = [input.skillName, input.rawName, description, input.icon]
    .filter(Boolean)
    .map(value => String(value))
  const signature = parts.join(' ')
  const auxiliary = AUXILIARY_SKILLS[normalizeAlias(input.skillName || input.rawName || '')]
  if (auxiliary) return { ...auxiliary, icon: input.icon || auxiliary.icon }

  const skillId = matchSkillId(signature)
  const skill = skillId ? skillById(skillId) : undefined
  if (skill) {
    return {
      title: skill.title,
      logoKind: skill.logoKind,
      icon: input.icon || skill.learnedIcon || skill.icon,
      canonicalId: skill.id,
    }
  }

  const rawName = (input.rawName || '').trim()
  return {
    title: rawName || `任务 ${fallbackIndex + 1}`,
    logoKind: 'default',
    icon: input.icon,
  }
}
