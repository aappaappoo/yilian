<script setup lang="ts">
import { computed } from 'vue'
import type { PropType } from 'vue'
import type { HealthMetricCardData, HealthMetricPoint } from './healthMetricCard'

const props = defineProps({
  data: { type: Object as PropType<HealthMetricCardData>, required: true },
})

interface ChartPoint {
  item: HealthMetricPoint
  x: number
  y: number
  secondaryY?: number
  value: number
  secondaryValue?: number
  alert: boolean
}

const chartWidth = 340
const chartHeight = 148
const chartPaddingX = 28
const chartPaddingTop = 18
const chartPaddingBottom = 28

const isBloodPressure = computed(() => props.data.metric === 'blood_pressure')
const hasSeries = computed(() => props.data.series.length > 0)
const abnormalCount = computed(() => props.data.series.filter(item => !!item.exceptionType).length)

function formatNumber(value: unknown): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '--'
  return Number.isInteger(value) ? String(value) : value.toFixed(1)
}

function shortDate(value: string): string {
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (match) return `${match[2]}/${match[3]}`
  return value || '今日'
}

function pointMainValue(point: HealthMetricPoint): number | undefined {
  return isBloodPressure.value ? point.systolic : point.value
}

function pointSecondaryValue(point: HealthMetricPoint): number | undefined {
  return isBloodPressure.value ? point.diastolic : undefined
}

const latestPoint = computed(() => props.data.series[props.data.series.length - 1] || null)

const latestDisplay = computed(() => {
  const latest = props.data.summary.latest
  if (latest && typeof latest === 'object') {
    return `${formatNumber(latest.systolic)}/${formatNumber(latest.diastolic)}`
  }
  if (typeof latest === 'number') return formatNumber(latest)
  if (!latestPoint.value) return '--'
  if (isBloodPressure.value) {
    return `${formatNumber(latestPoint.value.systolic)}/${formatNumber(latestPoint.value.diastolic)}`
  }
  return formatNumber(latestPoint.value.value)
})

const statusLabel = computed(() => {
  if (!hasSeries.value) return '暂无记录'
  if (abnormalCount.value) return `${abnormalCount.value}条需留意`
  return '记录平稳'
})

const supportText = computed(() => {
  if (!hasSeries.value) return '这一天暂时没有可展示的数据'
  if (props.data.scope === 'multi_day') return `${props.data.label}多日趋势`
  if (isBloodPressure.value) return '收缩压和舒张压变化'
  return `${props.data.label}变化趋势`
})

const rangeChips = computed(() => {
  const summary = props.data.summary
  if (isBloodPressure.value) {
    return [
      `共 ${summary.count || props.data.series.length} 条`,
      `收缩压 ${formatNumber(summary.systolic?.min)}~${formatNumber(summary.systolic?.max)}`,
      `舒张压 ${formatNumber(summary.diastolic?.min)}~${formatNumber(summary.diastolic?.max)}`,
    ]
  }
  return [
    `共 ${summary.count || props.data.series.length} 条`,
    `最低 ${formatNumber(summary.min)}${props.data.unit}`,
    `最高 ${formatNumber(summary.max)}${props.data.unit}`,
    `平均 ${formatNumber(summary.avg)}${props.data.unit}`,
  ]
})

const chartPoints = computed<ChartPoint[]>(() => {
  const rawValues = props.data.series.flatMap((point) => {
    const main = pointMainValue(point)
    const secondary = pointSecondaryValue(point)
    return [main, secondary].filter((value): value is number => typeof value === 'number' && Number.isFinite(value))
  })
  if (!rawValues.length) return []

  const minValue = Math.min(...rawValues)
  const maxValue = Math.max(...rawValues)
  const range = Math.max(maxValue - minValue, 1)
  const usableWidth = chartWidth - chartPaddingX * 2
  const usableHeight = chartHeight - chartPaddingTop - chartPaddingBottom
  const yForValue = (value: number) => chartPaddingTop + ((maxValue - value) / range) * usableHeight

  const points: ChartPoint[] = []
  props.data.series.forEach((item, index) => {
    const value = pointMainValue(item)
    if (value === undefined) return
    const x = props.data.series.length === 1
      ? chartWidth / 2
      : chartPaddingX + (usableWidth * index) / (props.data.series.length - 1)
    const secondaryValue = pointSecondaryValue(item)
    if (secondaryValue === undefined) {
      points.push({
        item,
        x,
        y: yForValue(value),
        value,
        alert: !!item.exceptionType,
      })
      return
    }
    points.push({
      item,
      x,
      y: yForValue(value),
      secondaryY: yForValue(secondaryValue),
      value,
      secondaryValue,
      alert: !!item.exceptionType,
    })
  })
  return points
})

const primaryLine = computed(() => chartPoints.value.map(point => `${point.x},${point.y}`).join(' '))
const secondaryLine = computed(() => chartPoints.value
  .filter(point => point.secondaryY !== undefined)
  .map(point => `${point.x},${point.secondaryY}`)
  .join(' '))
const showSecondaryLine = computed(() => isBloodPressure.value && !!secondaryLine.value)
const labelPoints = computed(() => {
  const points = chartPoints.value
  if (points.length <= 2) return points
  const middle = points[Math.floor(points.length / 2)]
  return [points[0], middle, points[points.length - 1]].filter((point, index, array) => array.indexOf(point) === index)
})

function recordValue(point: HealthMetricPoint): string {
  if (isBloodPressure.value) {
    return `${formatNumber(point.systolic)}/${formatNumber(point.diastolic)} ${props.data.unit}`
  }
  return `${formatNumber(point.value)} ${props.data.unit}`
}
</script>

<template>
  <article class="health-card" :class="`health-card--${data.metric}`">
    <div class="health-card__wash" aria-hidden="true"></div>

    <header class="health-card__topbar">
      <span>{{ shortDate(data.date) }} · {{ data.source }}</span>
      <strong>{{ statusLabel }}</strong>
    </header>

    <section class="health-card__hero">
      <div class="health-card__title">
        <p>{{ data.scope === 'multi_day' ? '趋势图' : '健康记录' }}</p>
        <h3>{{ data.label }}</h3>
        <span>{{ supportText }}</span>
      </div>
      <div class="health-card__latest">
        <span>{{ latestDisplay }}</span>
        <em>{{ data.unit }}</em>
      </div>
    </section>

    <section v-if="chartPoints.length" class="health-card__chart" :aria-label="`${data.label}变化折线图`">
      <div class="health-card__legend">
        <span><i class="health-card__dot health-card__dot--primary"></i>{{ isBloodPressure ? '收缩压' : data.label }}</span>
        <span v-if="showSecondaryLine"><i class="health-card__dot health-card__dot--secondary"></i>舒张压</span>
      </div>

      <svg class="health-card__svg" :viewBox="`0 0 ${chartWidth} ${chartHeight}`" role="img">
        <defs>
          <linearGradient id="healthGlow" x1="0" x2="1" y1="0" y2="1">
            <stop offset="0%" stop-color="#fda4c9" stop-opacity="0.36" />
            <stop offset="100%" stop-color="#b4a7ff" stop-opacity="0.1" />
          </linearGradient>
        </defs>
        <path class="health-card__grid" d="M20 28 H320 M20 74 H320 M20 120 H320" />
        <polyline class="health-card__line health-card__line--primary" :points="primaryLine" />
        <polyline v-if="showSecondaryLine" class="health-card__line health-card__line--secondary" :points="secondaryLine" />
        <g v-for="point in chartPoints" :key="`${point.item.dataTime || point.item.time}-${point.x}`">
          <circle
            class="health-card__point health-card__point--primary"
            :class="{ 'health-card__point--alert': point.alert }"
            :cx="point.x"
            :cy="point.y"
            r="4.4"
          >
            <title>{{ point.item.time }} {{ formatNumber(point.value) }}{{ data.unit }}</title>
          </circle>
          <circle
            v-if="point.secondaryY !== undefined"
            class="health-card__point health-card__point--secondary"
            :class="{ 'health-card__point--alert': point.alert }"
            :cx="point.x"
            :cy="point.secondaryY"
            r="4.1"
          >
            <title>{{ point.item.time }} {{ formatNumber(point.secondaryValue) }}{{ data.unit }}</title>
          </circle>
        </g>
      </svg>

      <div class="health-card__times">
        <span v-for="point in labelPoints" :key="`label-${point.item.dataTime || point.item.time}-${point.x}`">
          {{ point.item.time || '记录' }}
        </span>
      </div>
    </section>

    <section v-else class="health-card__empty">
      暂时没有查到这一天的记录
    </section>

    <section v-if="hasSeries" class="health-card__records" aria-label="健康记录明细">
      <header>
        <strong>{{ data.scope === 'multi_day' ? '每日均值' : '记录明细' }}</strong>
        <span>{{ data.series.length }} 条</span>
      </header>
      <div class="health-card__record-list">
        <div
          v-for="item in data.series"
          :key="item.dataTime || `${item.time}-${recordValue(item)}`"
          class="health-card__record-row"
        >
          <span>{{ item.time || '记录' }}</span>
          <strong>{{ recordValue(item) }}</strong>
          <em>{{ item.exceptionType || '无异常标记' }}</em>
        </div>
      </div>
    </section>

    <footer class="health-card__chips">
      <span v-for="chip in rangeChips" :key="chip">{{ chip }}</span>
    </footer>
  </article>
</template>

<style scoped>
.health-card {
  position: relative;
  overflow: hidden;
  display: grid;
  gap: 14px;
  width: min(100%, 520px);
  padding: 16px;
  border: 1px solid rgba(255, 255, 255, 0.68);
  border-radius: 22px;
  background:
    linear-gradient(145deg, rgba(255, 255, 255, 0.86), rgba(255, 247, 253, 0.68)),
    radial-gradient(circle at 15% 0%, rgba(255, 190, 220, 0.32), transparent 34%),
    radial-gradient(circle at 92% 8%, rgba(188, 176, 255, 0.3), transparent 32%);
  box-shadow: 0 18px 44px rgba(171, 132, 186, 0.18);
  color: #4f3b5c;
}

.health-card--blood_pressure {
  background:
    linear-gradient(145deg, rgba(255, 255, 255, 0.88), rgba(253, 247, 255, 0.72)),
    radial-gradient(circle at 12% 0%, rgba(246, 176, 204, 0.28), transparent 35%),
    radial-gradient(circle at 96% 8%, rgba(151, 190, 255, 0.24), transparent 32%);
}

.health-card__wash {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: linear-gradient(105deg, rgba(255, 255, 255, 0.4), transparent 34%, rgba(255, 255, 255, 0.18));
}

.health-card__topbar,
.health-card__hero,
.health-card__chart,
.health-card__empty,
.health-card__records,
.health-card__chips {
  position: relative;
}

.health-card__topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 12px;
  color: rgba(79, 59, 92, 0.68);
}

.health-card__topbar strong {
  flex: 0 0 auto;
  padding: 5px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.6);
  color: #8a5ba6;
  font-size: 12px;
  font-weight: 700;
}

.health-card__hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
}

.health-card__title {
  min-width: 0;
}

.health-card__title p,
.health-card__title span {
  margin: 0;
  font-size: 12px;
  color: rgba(79, 59, 92, 0.62);
}

.health-card__title h3 {
  margin: 4px 0 5px;
  color: #4a3358;
  font-size: 24px;
  font-weight: 800;
  letter-spacing: 0;
}

.health-card__latest {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: baseline;
  gap: 5px;
  padding: 10px 13px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.62);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.72);
}

.health-card__latest span {
  color: #d85f9d;
  font-size: 25px;
  font-weight: 800;
  line-height: 1;
}

.health-card__latest em {
  color: rgba(79, 59, 92, 0.62);
  font-size: 12px;
  font-style: normal;
  font-weight: 700;
}

.health-card__chart {
  display: grid;
  gap: 7px;
}

.health-card__legend {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  color: rgba(79, 59, 92, 0.66);
  font-size: 12px;
}

.health-card__legend span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.health-card__dot {
  width: 7px;
  height: 7px;
  border-radius: 999px;
}

.health-card__dot--primary {
  background: #e66aa8;
}

.health-card__dot--secondary {
  background: #8ea1ff;
}

.health-card__svg {
  width: 100%;
  height: auto;
  overflow: visible;
}

.health-card__grid {
  fill: none;
  stroke: rgba(141, 104, 159, 0.12);
  stroke-width: 1;
}

.health-card__line {
  fill: none;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 3.6;
}

.health-card__line--primary {
  stroke: #e66aa8;
  filter: drop-shadow(0 5px 10px rgba(230, 106, 168, 0.18));
}

.health-card__line--secondary {
  stroke: #8ea1ff;
  filter: drop-shadow(0 5px 10px rgba(142, 161, 255, 0.16));
}

.health-card__point {
  stroke: rgba(255, 255, 255, 0.92);
  stroke-width: 2.2;
}

.health-card__point--primary {
  fill: #e66aa8;
}

.health-card__point--secondary {
  fill: #8ea1ff;
}

.health-card__point--alert {
  stroke: #fff1a6;
}

.health-card__times {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  color: rgba(79, 59, 92, 0.58);
  font-size: 11px;
}

.health-card__empty {
  padding: 18px 12px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.56);
  color: rgba(79, 59, 92, 0.66);
  text-align: center;
}

.health-card__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.health-card__records {
  display: grid;
  gap: 8px;
  padding: 10px;
  border: 1px solid rgba(255, 255, 255, 0.58);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.42);
}

.health-card__records header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: rgba(79, 59, 92, 0.7);
  font-size: 12px;
}

.health-card__records header strong {
  color: #5a416b;
  font-weight: 750;
}

.health-card__record-list {
  display: grid;
  max-height: 176px;
  overflow: auto;
  padding-right: 2px;
  gap: 6px;
  overscroll-behavior: contain;
}

.health-card__record-row {
  display: grid;
  grid-template-columns: minmax(42px, 0.7fr) minmax(82px, 1fr) minmax(68px, 1fr);
  align-items: center;
  gap: 8px;
  min-height: 32px;
  padding: 6px 8px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.56);
  color: rgba(79, 59, 92, 0.66);
  font-size: 12px;
}

.health-card__record-row strong {
  color: #5a416b;
  font-weight: 760;
}

.health-card__record-row em {
  color: rgba(126, 91, 151, 0.68);
  font-style: normal;
  text-align: right;
}

.health-card__chips span {
  padding: 7px 10px;
  border: 1px solid rgba(255, 255, 255, 0.62);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.54);
  color: rgba(79, 59, 92, 0.76);
  font-size: 12px;
  font-weight: 650;
}

@media (max-width: 520px) {
  .health-card {
    padding: 14px;
    border-radius: 20px;
  }

  .health-card__hero {
    align-items: stretch;
    flex-direction: column;
  }

  .health-card__latest {
    align-self: flex-start;
  }

  .health-card__record-row {
    grid-template-columns: minmax(38px, 0.6fr) minmax(76px, 1fr);
  }

  .health-card__record-row em {
    grid-column: 1 / -1;
    text-align: left;
  }
}
</style>
