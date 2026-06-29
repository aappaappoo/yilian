<script setup lang="ts">
import { computed } from 'vue'
import type { PropType } from 'vue'
import WeatherMark from './WeatherMark.vue'
import type { WeatherReplyCardData } from './weatherReplyCard'

const props = defineProps({
  data: { type: Object as PropType<WeatherReplyCardData>, required: true },
})

const temperatureDisplay = computed(() => {
  const normalized = props.data.temp
    .replace(/\s+/g, '')
    .replace(/摄氏度/g, '℃')
    .replace(/°C/gi, '℃')
    .replace(/度/g, '℃')
    .replace(/~/g, '-')
    .replace(/到/g, '-')
  const match = normalized.match(/^(-?\d+(?:-\d+)?)(℃)?$/)
  if (!match) return { value: normalized, unit: '' }
  return { value: match[1], unit: match[2] || '℃' }
})

const weatherKind = computed(() => {
  const condition = props.data.condition
  if (/(雪|雨夹雪)/.test(condition)) return 'snow'
  if (/(雾|霾)/.test(condition)) return 'fog'
  if (/(雷|暴雨|大雨|中雨|小雨|阵雨|雨)/.test(condition)) return 'rain'
  if (/(阴)/.test(condition)) return 'cloudy'
  if (/(云)/.test(condition)) return 'partly'
  return 'sunny'
})

function compactText(value: string): string {
  return value.replace(/[，,。；;\s]/g, '').trim()
}

const noteItems = computed(() => {
  const outfit = props.data.outfit.trim()
  const tip = props.data.tip.trim()
  const items: Array<{ icon: string; label: string; text: string }> = []

  if (outfit) {
    items.push({
      icon: 'i-carbon-clothing-store',
      label: '穿衣',
      text: outfit,
    })
  }

  if (tip && compactText(tip) !== compactText(outfit)) {
    items.push({
      icon: 'i-carbon-cafe',
      label: '提醒',
      text: tip,
    })
  }

  return items
})

const metricItems = computed(() => {
  const items: Array<{ icon: string; text: string }> = []
  if (props.data.humidity) items.push({ icon: 'i-carbon-humidity', text: `湿度 ${props.data.humidity}` })
  if (props.data.wind) items.push({ icon: 'i-carbon-windy', text: props.data.wind })
  return items
})

const careLine = computed(() => {
  const source = `${props.data.condition} ${props.data.tip} ${props.data.outfit}`
  if (/(伞|雷|暴雨|大雨|中雨|小雨|阵雨|雨)/.test(source)) return '出门带伞'
  if (/(雪|冷|保暖|羽绒|厚外套)/.test(source)) return '注意保暖'
  if (/(晒|晴|紫外线)/.test(source)) return '做好防晒'
  if (/(雾|霾|口罩|空气)/.test(source)) return '留意空气'
  if (props.data.outfit.trim()) return props.data.outfit.trim()
  return '照顾好自己的节奏'
})

const topbarLabel = computed(() => {
  const date = props.data.dateRange?.trim()
  return date ? `${props.data.city} ${date}` : props.data.city
})
</script>

<template>
  <article class="weather-reply-card" :class="`weather-reply-card--${weatherKind}`">
    <div class="weather-reply-card__wash" aria-hidden="true"></div>

    <header class="weather-reply-card__topbar">
      <span>{{ topbarLabel }}</span>
      <strong>{{ data.condition }}</strong>
    </header>

    <section class="weather-reply-card__hero">
      <div class="weather-reply-card__main">
        <h3>{{ data.city }}</h3>
        <p class="weather-reply-card__subtitle">今天也要照顾好自己的节奏</p>
        <p class="weather-reply-card__temp">
          <span>{{ temperatureDisplay.value }}</span>
          <em v-if="temperatureDisplay.unit">{{ temperatureDisplay.unit }}</em>
        </p>
      </div>

      <div class="weather-reply-card__visual">
        <WeatherMark class="weather-reply-card__mark" :kind="weatherKind" size="large" />
        <div v-if="metricItems.length" class="weather-reply-card__metrics">
          <span v-for="item in metricItems" :key="item.text">
            <i :class="item.icon"></i>
            {{ item.text }}
          </span>
        </div>
      </div>
    </section>

    <p class="weather-reply-card__care">{{ careLine }}</p>

    <div v-if="noteItems.length" class="weather-reply-card__notes">
      <p v-for="item in noteItems" :key="item.label">
        <span :class="item.icon"></span>
        <span>
          <strong>{{ item.label }}</strong>
          {{ item.text }}
        </span>
      </p>
    </div>
  </article>
</template>

<style scoped>
.weather-reply-card {
  --weather-accent: #8a72d7;
  --weather-accent-deep: #594791;
  --weather-accent-soft: rgba(138, 114, 215, 0.15);
  --weather-ink: #40365f;
  --weather-muted: #8c80aa;
  --weather-bubble: rgba(255, 255, 255, 0.64);
  position: relative;
  overflow: hidden;
  width: min(100%, 238px);
  border: 1px solid rgba(225, 215, 244, 0.72);
  border-radius: 25px;
  background:
    radial-gradient(circle at 78% 24%, rgba(255, 228, 176, 0.42), transparent 18%),
    radial-gradient(circle at 22% 0%, rgba(246, 234, 255, 0.78), transparent 34%),
    linear-gradient(145deg, rgba(255, 255, 255, 0.93), rgba(249, 245, 255, 0.78) 46%, rgba(255, 247, 252, 0.84));
  box-shadow:
    0 18px 48px rgba(94, 75, 132, 0.13),
    inset 0 1px 0 rgba(255, 255, 255, 0.84);
  color: var(--weather-ink);
  padding: 18px;
  backdrop-filter: blur(22px);
}

.weather-reply-card--sunny {
  --weather-accent: #f59e0b;
  --weather-accent-deep: #7d5b1e;
  --weather-accent-soft: rgba(245, 158, 11, 0.2);
}

.weather-reply-card--partly {
  --weather-accent: #8a72d7;
  --weather-accent-deep: #594791;
  --weather-accent-soft: rgba(138, 114, 215, 0.15);
}

.weather-reply-card--cloudy {
  --weather-accent: #64748b;
  --weather-accent-deep: #526078;
  --weather-accent-soft: rgba(100, 116, 139, 0.15);
}

.weather-reply-card--rain {
  --weather-accent: #3b82f6;
  --weather-accent-deep: #355fbb;
  --weather-accent-soft: rgba(59, 130, 246, 0.17);
}

.weather-reply-card--snow {
  --weather-accent: #0891b2;
  --weather-accent-deep: #147284;
  --weather-accent-soft: rgba(8, 145, 178, 0.15);
}

.weather-reply-card--fog {
  --weather-accent: #6b7280;
  --weather-accent-deep: #555c69;
  --weather-accent-soft: rgba(107, 114, 128, 0.15);
}

.weather-reply-card__wash {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(120deg, var(--weather-accent-soft), transparent 42%),
    linear-gradient(315deg, rgba(255, 224, 241, 0.22), transparent 48%);
  pointer-events: none;
}

.weather-reply-card__topbar,
.weather-reply-card__hero,
.weather-reply-card__care,
.weather-reply-card__notes {
  position: relative;
  z-index: 2;
}

.weather-reply-card__topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.weather-reply-card__topbar span {
  color: #9a90b6;
  font-size: 11px;
  font-weight: 850;
  line-height: 1;
}

.weather-reply-card__topbar strong {
  min-width: 0;
  border-radius: 999px;
  background: var(--weather-bubble);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);
  color: var(--weather-accent-deep);
  font-size: 12px;
  font-weight: 850;
  line-height: 1;
  max-width: 96px;
  overflow: hidden;
  padding: 8px 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.weather-reply-card__hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 92px;
  gap: 6px;
  margin-top: 14px;
  min-height: 128px;
}

.weather-reply-card__main {
  min-width: 0;
}

.weather-reply-card__main h3 {
  margin: 0;
  overflow: hidden;
  color: var(--weather-ink);
  font-size: 20px;
  font-weight: 900;
  line-height: 1.18;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.weather-reply-card__subtitle {
  max-width: 118px;
  margin: 8px 0 0;
  color: #776d96;
  font-size: 13px;
  font-weight: 650;
  line-height: 1.55;
}

.weather-reply-card__temp span {
  display: inline-block;
  color: #6950c7;
  font-size: 44px;
  font-weight: 900;
  letter-spacing: 0;
  line-height: 0.96;
}

.weather-reply-card__temp em {
  align-self: flex-start;
  margin-top: 8px;
  color: #8d80bd;
  font-size: 15px;
  font-weight: 850;
  font-style: normal;
  line-height: 1;
}

.weather-reply-card__temp {
  display: inline-flex;
  align-items: flex-start;
  flex: 0 0 auto;
  gap: 3px;
  margin: 18px 0 0;
  white-space: nowrap;
}

.weather-reply-card__visual {
  display: flex;
  align-items: center;
  flex-direction: column;
  justify-content: flex-start;
  padding-top: 12px;
}

.weather-reply-card__mark {
  margin-right: -7px;
}

.weather-reply-card__metrics {
  display: grid;
  gap: 5px;
  justify-items: center;
  margin-top: 2px;
  max-width: 96px;
}

.weather-reply-card__metrics span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.62);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.76);
  color: #746897;
  font-size: 11px;
  font-weight: 800;
  line-height: 1;
  padding: 6px 9px;
  white-space: nowrap;
}

.weather-reply-card__metrics i {
  color: var(--weather-accent);
  font-style: normal;
  font-size: 12px;
}

.weather-reply-card__care {
  min-height: 42px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 4px 0 12px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.58);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.74),
    0 10px 22px rgba(128, 104, 170, 0.08);
  color: #70658d;
  font-size: 13px;
  font-weight: 850;
  line-height: 1.2;
  padding: 9px 12px;
  text-align: center;
}

.weather-reply-card__notes {
  display: grid;
  gap: 8px;
}

.weather-reply-card__notes p {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin: 0;
  border: 1px solid rgba(255, 255, 255, 0.64);
  border-radius: 16px;
  background:
    linear-gradient(145deg, rgba(255, 255, 255, 0.68), rgba(255, 255, 255, 0.34));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.68);
  color: #5d527e;
  font-size: 12px;
  font-weight: 650;
  line-height: 1.62;
  padding: 10px 11px;
}

.weather-reply-card__notes span:first-child {
  flex: 0 0 auto;
  margin-top: 4px;
  color: var(--weather-accent);
  font-size: 14px;
}

.weather-reply-card__notes strong {
  margin-right: 4px;
  color: #5b4f80;
  font-size: 11px;
  font-weight: 850;
}

@media (max-width: 420px) {
  .weather-reply-card {
    border-radius: 23px;
    padding: 16px;
  }

  .weather-reply-card__hero {
    grid-template-columns: minmax(0, 1fr) 86px;
  }

  .weather-reply-card__mark {
    transform: scale(0.92);
    transform-origin: top right;
  }

  .weather-reply-card__temp span {
    font-size: 40px;
  }
}

@media (max-width: 360px) {
  .weather-reply-card {
    width: 100%;
  }

  .weather-reply-card__hero {
    grid-template-columns: 1fr;
  }

  .weather-reply-card__visual {
    align-items: flex-start;
    padding-top: 0;
  }
}
</style>
