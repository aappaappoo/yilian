<script setup lang="ts">
import { computed } from 'vue'
import type { PropType } from 'vue'
import WeatherMark from './WeatherMark.vue'
import type { WeatherForecastCardData, WeatherForecastDayData } from './weatherForecastCard'

const props = defineProps({
  data: { type: Object as PropType<WeatherForecastCardData>, required: true },
})

interface ChartPoint {
  day: WeatherForecastDayData
  x: number
  highY: number
  lowY: number
  high: number
  low: number
}

const chartWidth = 320
const chartHeight = 136
const chartPaddingX = 28
const chartPaddingTop = 18
const chartPaddingBottom = 26

function dayKind(day: WeatherForecastDayData): string {
  const condition = day.condition
  if (/(雪|雨夹雪)/.test(condition)) return 'snow'
  if (/(雾|霾)/.test(condition)) return 'fog'
  if (/(雷|暴雨|大雨|中雨|小雨|阵雨|雨)/.test(condition)) return 'rain'
  if (/(阴)/.test(condition)) return 'cloudy'
  if (/(云)/.test(condition)) return 'partly'
  return 'sunny'
}

function shortDate(date: string): string {
  return date.slice(5).replace('-', '/')
}

function dateRangeLabel(forecast: WeatherForecastDayData[]): string {
  const first = forecast[0]
  const last = forecast[forecast.length - 1]
  if (!first) return ''
  const start = shortDate(first.date)
  const end = last ? shortDate(last.date) : start
  return start === end ? start : `${start}～${end}`
}

function tempNumber(value: string): number {
  const parsed = Number.parseFloat(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function rainLabel(day: WeatherForecastDayData): string {
  const source = day.rainChance?.trim()
  if (!source) return '降雨待定'
  const chance = Number.parseInt(source, 10)
  if (!Number.isFinite(chance)) return '降雨待定'
  if (chance <= 0) return '基本无雨'
  return `降雨概率 ${chance}%`
}

const rainyDays = computed(() => (
  props.data.forecast.filter(day => Number.parseInt(day.rainChance || '0', 10) >= 50).length
))

const showTrendChart = computed(() => props.data.forecast.length > 1)
const singleDay = computed<WeatherForecastDayData | null>(() => props.data.forecast[0] || null)
const cardWeatherKind = computed(() => {
  const rainy = props.data.forecast.find(day => dayKind(day) === 'rain')
  const day = rainy || props.data.forecast[0]
  return day ? dayKind(day) : 'partly'
})
const cardTitle = computed(() => {
  if (!showTrendChart.value) return ''
  return `${props.data.city}未来${props.data.days}天`
})

const topbarMeta = computed(() => {
  if (!showTrendChart.value && singleDay.value) return `${props.data.city} ${shortDate(singleDay.value.date)}`
  const range = dateRangeLabel(props.data.forecast)
  return range ? `${props.data.city} ${range}` : props.data.city
})
const statusLabel = computed(() => {
  if (!showTrendChart.value && singleDay.value) return singleDay.value.condition
  return rainyDays.value ? `${rainyDays.value}天可能有雨` : '整体适合出门'
})
const forecastMoodText = computed(() => {
  if (!showTrendChart.value) return '今天也要照顾好自己的节奏'
  return rainyDays.value ? '这几天记得留意雨具和出行节奏' : '这几天整体适合轻松安排'
})
const singleTemperatureDisplay = computed(() => {
  if (!singleDay.value) return ''
  return `${singleDay.value.minTemp}~${singleDay.value.maxTemp}`
})

const headlineKind = computed(() => {
  const rainy = props.data.forecast.find(day => dayKind(day) === 'rain')
  return rainy ? dayKind(rainy) : cardWeatherKind.value
})

const chartPoints = computed<ChartPoint[]>(() => {
  const days = props.data.forecast
  const highs = days.map(day => tempNumber(day.maxTemp))
  const lows = days.map(day => tempNumber(day.minTemp))
  const maxTemp = Math.max(...highs, ...lows)
  const minTemp = Math.min(...highs, ...lows)
  const tempRange = Math.max(maxTemp - minTemp, 1)
  const usableWidth = chartWidth - chartPaddingX * 2
  const usableHeight = chartHeight - chartPaddingTop - chartPaddingBottom
  const yForTemp = (temp: number) => chartPaddingTop + ((maxTemp - temp) / tempRange) * usableHeight

  return days.map((day, index) => {
    const x = days.length === 1
      ? chartWidth / 2
      : chartPaddingX + (usableWidth * index) / (days.length - 1)
    const high = highs[index]
    const low = lows[index]
    return {
      day,
      x,
      high,
      low,
      highY: yForTemp(high),
      lowY: yForTemp(low),
    }
  })
})

const highLine = computed(() => chartPoints.value.map(point => `${point.x},${point.highY}`).join(' '))
const lowLine = computed(() => chartPoints.value.map(point => `${point.x},${point.lowY}`).join(' '))
const temperatureArea = computed(() => {
  const highPoints = chartPoints.value.map(point => `${point.x},${point.highY}`)
  const lowPoints = [...chartPoints.value].reverse().map(point => `${point.x},${point.lowY}`)
  return [...highPoints, ...lowPoints].join(' ')
})
</script>

<template>
  <article
    class="weather-forecast-card"
    :class="[
      `weather-forecast-card--${cardWeatherKind}`,
      { 'weather-forecast-card--single': !showTrendChart },
    ]"
  >
    <div class="weather-forecast-card__wash" aria-hidden="true"></div>

    <header class="weather-forecast-card__topbar">
      <span>{{ topbarMeta }}</span>
      <strong>{{ statusLabel }}</strong>
    </header>

    <section class="weather-forecast-card__hero">
      <div class="weather-forecast-card__title">
        <h3 v-if="cardTitle">{{ cardTitle }}</h3>
        <p>{{ forecastMoodText }}</p>
        <p v-if="!showTrendChart && singleDay" class="weather-forecast-card__temp">
          <span>{{ singleTemperatureDisplay }}</span>
          <em>℃</em>
        </p>
      </div>

      <div class="weather-forecast-card__visual">
        <WeatherMark class="weather-forecast-card__mark" :kind="headlineKind" size="large" />
      </div>
    </section>

    <section v-if="showTrendChart" class="weather-forecast-card__chart" aria-label="未来几天温度趋势">
      <div class="weather-forecast-card__legend">
        <span><i class="weather-forecast-card__dot weather-forecast-card__dot--high"></i>最高温</span>
        <span><i class="weather-forecast-card__dot weather-forecast-card__dot--low"></i>最低温</span>
      </div>
      <svg
        class="weather-forecast-card__svg"
        :viewBox="`0 0 ${chartWidth} ${chartHeight}`"
        role="img"
      >
        <defs>
          <linearGradient id="forecastArea" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stop-color="#ffa5c8" stop-opacity="0.24" />
            <stop offset="100%" stop-color="#9fb7ff" stop-opacity="0.08" />
          </linearGradient>
        </defs>
        <path class="weather-forecast-card__grid" d="M20 24 H300 M20 68 H300 M20 112 H300" />
        <polygon v-if="chartPoints.length > 1" class="weather-forecast-card__area" :points="temperatureArea" />
        <polyline class="weather-forecast-card__line weather-forecast-card__line--high" :points="highLine" />
        <polyline class="weather-forecast-card__line weather-forecast-card__line--low" :points="lowLine" />
        <g v-for="point in chartPoints" :key="point.day.date">
          <line class="weather-forecast-card__tick" :x1="point.x" :x2="point.x" y1="18" y2="118" />
          <circle class="weather-forecast-card__point weather-forecast-card__point--high" :cx="point.x" :cy="point.highY" r="4.5" />
          <circle class="weather-forecast-card__point weather-forecast-card__point--low" :cx="point.x" :cy="point.lowY" r="4.5" />
          <text class="weather-forecast-card__temp-label weather-forecast-card__temp-label--high" :x="point.x" :y="Math.max(point.highY - 9, 11)" text-anchor="middle">
            {{ point.high }}℃
          </text>
          <text class="weather-forecast-card__temp-label weather-forecast-card__temp-label--low" :x="point.x" :y="Math.min(point.lowY + 16, 132)" text-anchor="middle">
            {{ point.low }}℃
          </text>
        </g>
      </svg>
    </section>

    <section v-if="!showTrendChart && singleDay" class="weather-forecast-card__single">
      <span class="weather-forecast-card__single-rain">
        {{ rainLabel(singleDay) }}
      </span>
    </section>

    <div v-else class="weather-forecast-card__days">
      <section v-for="day in data.forecast" :key="day.date" class="weather-forecast-card__day">
        <WeatherMark class="weather-forecast-card__day-mark" :kind="dayKind(day)" size="tiny" />
        <span class="weather-forecast-card__date">{{ shortDate(day.date) }}</span>
        <strong>{{ day.condition }}</strong>
        <span class="weather-forecast-card__rain">{{ rainLabel(day) }}</span>
      </section>
    </div>
  </article>
</template>

<style scoped>
.weather-forecast-card {
  --weather-accent: #8a72d7;
  --weather-accent-deep: #594791;
  --weather-accent-soft: rgba(138, 114, 215, 0.15);
  --weather-ink: #40365f;
  --weather-muted: #8c80aa;
  --weather-warm: #e16d9c;
  position: relative;
  overflow: hidden;
  border: 1px solid rgba(225, 215, 244, 0.72);
  border-radius: 25px;
  background:
    radial-gradient(circle at 78% 24%, rgba(255, 228, 176, 0.36), transparent 18%),
    radial-gradient(circle at 20% 0%, rgba(246, 234, 255, 0.76), transparent 34%),
    linear-gradient(145deg, rgba(255, 255, 255, 0.93), rgba(249, 245, 255, 0.78) 46%, rgba(255, 247, 252, 0.84));
  box-shadow:
    0 18px 48px rgba(94, 75, 132, 0.13),
    inset 0 1px 0 rgba(255, 255, 255, 0.84);
  color: var(--weather-ink);
  padding: 18px;
  backdrop-filter: blur(22px);
}

.weather-forecast-card--sunny {
  --weather-accent: #f59e0b;
  --weather-accent-deep: #b45309;
  --weather-accent-soft: rgba(245, 158, 11, 0.24);
  --weather-icon: #f59e0b;
  --weather-warm: #db2777;
}

.weather-forecast-card--partly {
  --weather-accent: #8f78df;
  --weather-accent-deep: #6252b5;
  --weather-accent-soft: rgba(143, 120, 223, 0.16);
  --weather-icon: #f59e0b;
  --weather-warm: #d9468f;
}

.weather-forecast-card--cloudy {
  --weather-accent: #64748b;
  --weather-accent-deep: #475569;
  --weather-accent-soft: rgba(100, 116, 139, 0.18);
  --weather-icon: #64748b;
  --weather-warm: #8b5cf6;
}

.weather-forecast-card--rain {
  --weather-accent: #2563eb;
  --weather-accent-deep: #1d4ed8;
  --weather-accent-soft: rgba(37, 99, 235, 0.2);
  --weather-icon: #2563eb;
  --weather-warm: #7c3aed;
}

.weather-forecast-card--snow {
  --weather-accent: #0891b2;
  --weather-accent-deep: #0e7490;
  --weather-accent-soft: rgba(8, 145, 178, 0.18);
  --weather-icon: #0891b2;
  --weather-warm: #7c3aed;
}

.weather-forecast-card--fog {
  --weather-accent: #6b7280;
  --weather-accent-deep: #4b5563;
  --weather-accent-soft: rgba(107, 114, 128, 0.2);
  --weather-icon: #6b7280;
  --weather-warm: #8b5cf6;
}

.weather-forecast-card__wash {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(115deg, var(--weather-accent-soft), transparent 42%),
    linear-gradient(315deg, rgba(255, 220, 236, 0.24), transparent 46%);
  pointer-events: none;
}

.weather-forecast-card--single {
  width: min(100%, 238px);
}

.weather-forecast-card__topbar,
.weather-forecast-card__hero,
.weather-forecast-card__chart,
.weather-forecast-card__single,
.weather-forecast-card__days {
  position: relative;
  z-index: 2;
}

.weather-forecast-card__topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.weather-forecast-card__topbar span {
  min-width: 0;
  overflow: hidden;
  color: #9a90b6;
  font-size: 11px;
  font-weight: 850;
  line-height: 1;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.weather-forecast-card__topbar strong {
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.64);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);
  color: var(--weather-accent-deep);
  font-size: 12px;
  font-weight: 850;
  line-height: 1;
  max-width: 116px;
  overflow: hidden;
  padding: 8px 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.weather-forecast-card__hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 92px;
  gap: 8px;
  margin-top: 14px;
  min-height: 126px;
}

.weather-forecast-card__title {
  display: flex;
  min-width: 0;
  flex-direction: column;
}

.weather-forecast-card__title h3 {
  margin: 0;
  overflow: hidden;
  color: var(--weather-ink);
  font-size: 20px;
  font-weight: 900;
  line-height: 1.18;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.weather-forecast-card__title p:not(.weather-forecast-card__temp) {
  max-width: 128px;
  margin: 8px 0 0;
  color: #776d96;
  font-size: 13px;
  font-weight: 650;
  line-height: 1.55;
}

.weather-forecast-card--single .weather-forecast-card__title p:not(.weather-forecast-card__temp) {
  margin-top: 0;
}

.weather-forecast-card__temp {
  display: inline-flex;
  align-items: flex-start;
  gap: 3px;
  margin: 18px 0 0;
  white-space: nowrap;
}

.weather-forecast-card__temp span {
  color: #6950c7;
  font-size: 38px;
  font-weight: 900;
  letter-spacing: 0;
  line-height: 0.96;
}

.weather-forecast-card__temp em {
  margin-top: 8px;
  color: #8d80bd;
  font-size: 15px;
  font-style: normal;
  font-weight: 850;
  line-height: 1;
}

.weather-forecast-card__visual {
  display: flex;
  align-items: center;
  flex-direction: column;
  padding-top: 12px;
}

.weather-forecast-card__mark {
  margin-right: -7px;
}

.weather-forecast-card__chart {
  border: 1px solid rgba(255, 255, 255, 0.68);
  border-radius: 18px;
  background:
    linear-gradient(145deg, rgba(255, 255, 255, 0.68), rgba(255, 255, 255, 0.34)),
    rgba(247, 244, 255, 0.42);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.72);
  margin-top: -2px;
  padding: 11px 10px 6px;
}

.weather-forecast-card__legend {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  color: #857ba5;
  font-size: 11px;
  font-weight: 700;
}

.weather-forecast-card__legend span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.weather-forecast-card__dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
}

.weather-forecast-card__dot--high {
  background: var(--weather-warm);
}

.weather-forecast-card__dot--low {
  background: var(--weather-accent);
}

.weather-forecast-card__svg {
  display: block;
  width: 100%;
  height: 150px;
  overflow: visible;
}

.weather-forecast-card__grid,
.weather-forecast-card__tick {
  stroke: rgba(147, 134, 180, 0.16);
  stroke-width: 1;
}

.weather-forecast-card__tick {
  stroke-dasharray: 3 7;
}

.weather-forecast-card__area {
  fill: url("#forecastArea");
}

.weather-forecast-card__line {
  fill: none;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 3.5;
}

.weather-forecast-card__line--high {
  stroke: var(--weather-warm);
}

.weather-forecast-card__line--low {
  stroke: var(--weather-accent);
}

.weather-forecast-card__point {
  stroke: rgba(255, 255, 255, 0.95);
  stroke-width: 2.2;
}

.weather-forecast-card__point--high {
  fill: var(--weather-warm);
}

.weather-forecast-card__point--low {
  fill: var(--weather-accent);
}

.weather-forecast-card__temp-label {
  fill: #675d86;
  font-size: 11px;
  font-weight: 700;
}

.weather-forecast-card__temp-label--high {
  fill: #bd638a;
}

.weather-forecast-card__temp-label--low {
  fill: var(--weather-accent-deep);
}

.weather-forecast-card__days {
  display: flex;
  gap: 9px;
  margin-top: 12px;
  overflow-x: auto;
  padding-bottom: 2px;
}

.weather-forecast-card__day {
  min-width: 88px;
  border: 1px solid rgba(255, 255, 255, 0.72);
  border-radius: 17px;
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.58), rgba(255, 255, 255, 0.36));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.72);
  display: flex;
  align-items: center;
  flex: 1 0 0;
  flex-direction: column;
  gap: 5px;
  padding: 10px 8px;
  text-align: center;
}

.weather-forecast-card__date {
  color: #7e749f;
  font-size: 12px;
}

.weather-forecast-card__day strong {
  color: #514873;
  font-size: 12px;
  line-height: 1.2;
}

.weather-forecast-card__rain {
  color: #9b90b8;
  font-size: 11px;
  line-height: 1.25;
}

.weather-forecast-card__single {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 42px;
  margin-top: 4px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.58);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.74),
    0 10px 22px rgba(128, 104, 170, 0.08);
  padding: 9px 12px;
}

.weather-forecast-card__single-rain {
  color: #70658d;
  font-size: 13px;
  font-weight: 800;
  line-height: 1.2;
  text-align: center;
}

@media (max-width: 520px) {
  .weather-forecast-card {
    border-radius: 23px;
    padding: 14px;
  }

  .weather-forecast-card__hero {
    grid-template-columns: minmax(0, 1fr) 86px;
  }

  .weather-forecast-card__svg {
    height: 132px;
  }

  .weather-forecast-card__mark {
    transform: scale(0.92);
    transform-origin: top right;
  }
}
</style>
