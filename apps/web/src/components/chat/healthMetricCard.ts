export type HealthMetricKey = 'heart_rate' | 'blood_pressure' | 'blood_oxygen' | 'temperature'

export interface HealthMetricPoint {
  time: string
  dataTime?: string
  value?: number
  systolic?: number
  diastolic?: number
  exceptionType?: string
}

interface HealthMetricRange {
  min?: number
  max?: number
  avg?: number
}

export interface HealthMetricSummary {
  count: number
  latest?: number | {
    systolic?: number
    diastolic?: number
  }
  min?: number
  max?: number
  avg?: number
  systolic?: HealthMetricRange
  diastolic?: HealthMetricRange
}

export interface HealthMetricCardData {
  metric: HealthMetricKey
  label: string
  unit: string
  date: string
  scope?: 'single_day' | 'multi_day'
  source: string
  summary: HealthMetricSummary
  series: HealthMetricPoint[]
}

const healthMetricKeys = new Set<HealthMetricKey>([
  'heart_rate',
  'blood_pressure',
  'blood_oxygen',
  'temperature',
])

const metricLabelMap: Record<HealthMetricKey, string> = {
  heart_rate: '心率',
  blood_pressure: '血压',
  blood_oxygen: '血氧',
  temperature: '体温',
}

const metricUnitMap: Record<HealthMetricKey, string> = {
  heart_rate: 'bpm',
  blood_pressure: 'mmHg',
  blood_oxygen: '%',
  temperature: '℃',
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

function arrayField(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function textField(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function numberField(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  const parsed = Number.parseFloat(textField(value))
  return Number.isFinite(parsed) ? parsed : undefined
}

function normalizeMetric(value: unknown): HealthMetricKey | '' {
  const metric = textField(value) as HealthMetricKey
  return healthMetricKeys.has(metric) ? metric : ''
}

function inferMetricFromLabel(value: unknown): HealthMetricKey | '' {
  const label = textField(value)
  if (/血压/.test(label)) return 'blood_pressure'
  if (/血氧/.test(label)) return 'blood_oxygen'
  if (/体温/.test(label)) return 'temperature'
  if (/心率/.test(label)) return 'heart_rate'
  return ''
}

function normalizeRange(value: unknown): HealthMetricRange {
  const root = asRecord(value)
  if (!root) return {}
  return {
    min: numberField(root.min),
    max: numberField(root.max),
    avg: numberField(root.avg),
  }
}

function normalizeSummary(value: unknown, series: HealthMetricPoint[], metric: HealthMetricKey): HealthMetricSummary {
  const root = asRecord(value)
  const latestRaw = root?.latest
  const latestRecord = asRecord(latestRaw)
  const latest = latestRecord
    ? {
        systolic: numberField(latestRecord.systolic),
        diastolic: numberField(latestRecord.diastolic),
      }
    : numberField(latestRaw)

  return {
    count: numberField(root?.count) ?? series.length,
    latest,
    min: numberField(root?.min),
    max: numberField(root?.max),
    avg: numberField(root?.avg),
    systolic: metric === 'blood_pressure' ? normalizeRange(root?.systolic) : undefined,
    diastolic: metric === 'blood_pressure' ? normalizeRange(root?.diastolic) : undefined,
  }
}

function dateLabel(value: string): string {
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  return match ? `${match[2]}/${match[3]}` : value
}

function dateRangeLabel(values: string[]): string {
  const dates = [...new Set(values.filter(Boolean))].sort()
  if (!dates.length) return ''
  const first = dateLabel(dates[0])
  const last = dateLabel(dates[dates.length - 1])
  return first === last ? first : `${first}~${last}`
}

function normalizePoint(value: unknown, metric: HealthMetricKey): HealthMetricPoint | null {
  const item = asRecord(value)
  if (!item) return null

  const dataTime = textField(item.dataTime)
  const time = textField(item.time) || dataTime.match(/(\d{1,2}:\d{2})/)?.[1] || dataTime.slice(-5)
  const exceptionType = textField(item.exceptionType)

  if (metric === 'blood_pressure') {
    const systolic = numberField(item.systolic)
    const diastolic = numberField(item.diastolic)
    if (systolic === undefined || diastolic === undefined) return null
    return { time, dataTime, systolic, diastolic, exceptionType }
  }

  const pointValue = numberField(item.value)
  if (pointValue === undefined) return null
  return { time, dataTime, value: pointValue, exceptionType }
}

function normalizeHealthMetricPayload(value: unknown): HealthMetricCardData | null {
  const root = asRecord(value)
  if (!root) return null

  const metric = normalizeMetric(root.metric) || inferMetricFromLabel(root.label)
  if (!metric) return null

  const series = arrayField(root.series)
    .map(item => normalizePoint(item, metric))
    .filter((item): item is HealthMetricPoint => !!item)

  const label = textField(root.label) || metricLabelMap[metric]
  const unit = textField(root.unit) || metricUnitMap[metric]
  const date = textField(root.date) || textField(root.dayTime)
  const source = textField(root.source) || '易联健康'
  return {
    metric,
    label,
    unit,
    date,
    scope: 'single_day',
    source,
    summary: normalizeSummary(root.summary, series, metric),
    series,
  }
}

function healthMetricPayloads(root: Record<string, unknown>): HealthMetricCardData[] {
  const payloads: HealthMetricCardData[] = []

  const addPayload = (value: unknown) => {
    const payload = normalizeHealthMetricPayload(value)
    if (payload) payloads.push(payload)
  }

  addPayload(root.health_metric)

  const directResult = asRecord(root.result)
  addPayload(directResult?.health_metric)

  const nestedResult = asRecord(directResult?.result)
  addPayload(nestedResult?.health_metric)

  for (const entry of arrayField(root.tool_results)) {
    const item = asRecord(entry)
    const result = asRecord(item?.result)
    addPayload(result?.health_metric)
  }

  for (const card of [...arrayField(root.cards), ...arrayField(directResult?.cards)]) {
    const item = asRecord(card)
    if (!item) continue
    if (textField(item.type) === 'health_metric') {
      addPayload(asRecord(item.fields) || asRecord(item.artifact)?.result)
    }
  }

  for (const entry of arrayField(root.artifacts)) {
    const item = asRecord(entry)
    const artifact = asRecord(item?.artifact) || item
    if (textField(artifact?.type) === 'health_metric') addPayload(artifact)
    addPayload(artifact?.health_metric)
  }

  const seen = new Set<string>()
  return payloads.filter((payload) => {
    const key = `${payload.metric}:${payload.date}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function latestForPayload(payload: HealthMetricCardData): HealthMetricSummary['latest'] {
  const latest = payload.summary.latest
  if (latest !== undefined) return latest
  const point = payload.series[payload.series.length - 1]
  if (!point) return undefined
  if (payload.metric === 'blood_pressure') {
    return { systolic: point.systolic, diastolic: point.diastolic }
  }
  return point.value
}

function averageValue(payload: HealthMetricCardData, key: 'value' | 'systolic' | 'diastolic'): number | undefined {
  if (key === 'value') return payload.summary.avg
  const range = key === 'systolic' ? payload.summary.systolic : payload.summary.diastolic
  if (range?.avg !== undefined) return range.avg
  const values = payload.series
    .map(point => numberField(point[key]))
    .filter((value): value is number => value !== undefined)
  if (!values.length) return undefined
  return Math.round((values.reduce((sum, value) => sum + value, 0) / values.length) * 10) / 10
}

function combineMultiDayHealthMetric(payloads: HealthMetricCardData[]): HealthMetricCardData | null {
  if (payloads.length < 2) return null
  const metric = payloads[0].metric
  if (!payloads.every(payload => payload.metric === metric)) return null

  const dates = [...new Set(payloads.map(payload => payload.date).filter(Boolean))].sort()
  if (dates.length < 2) return null

  const ordered = [...payloads].sort((left, right) => left.date.localeCompare(right.date))
  const label = payloads[0].label || metricLabelMap[metric]
  const unit = payloads[0].unit || metricUnitMap[metric]
  const source = payloads[0].source || '易联健康'
  const series = ordered
    .map((payload): HealthMetricPoint | null => {
      const abnormalCount = payload.series.filter(point => !!point.exceptionType).length
      const exceptionType = abnormalCount ? `${abnormalCount}条需留意` : ''
      if (metric === 'blood_pressure') {
        const systolic = averageValue(payload, 'systolic')
        const diastolic = averageValue(payload, 'diastolic')
        if (systolic === undefined || diastolic === undefined) return null
        return {
          time: dateLabel(payload.date),
          dataTime: payload.date,
          systolic,
          diastolic,
          exceptionType,
        }
      }
      const value = averageValue(payload, 'value')
      if (value === undefined) return null
      return {
        time: dateLabel(payload.date),
        dataTime: payload.date,
        value,
        exceptionType,
      }
    })
    .filter((point): point is HealthMetricPoint => !!point)
  if (series.length < 2) return null

  const latest = latestForPayload(ordered[ordered.length - 1])
  const values = series
    .flatMap((point) => {
      if (metric === 'blood_pressure') return [point.systolic, point.diastolic]
      return [point.value]
    })
    .filter((value): value is number => value !== undefined)

  const summary: HealthMetricSummary = {
    count: ordered.reduce((sum, payload) => sum + (payload.summary.count || payload.series.length), 0),
    latest,
  }
  if (metric === 'blood_pressure') {
    const systolicValues = series.map(point => point.systolic).filter((value): value is number => value !== undefined)
    const diastolicValues = series.map(point => point.diastolic).filter((value): value is number => value !== undefined)
    summary.systolic = {
      min: Math.min(...systolicValues),
      max: Math.max(...systolicValues),
      avg: Math.round((systolicValues.reduce((sum, value) => sum + value, 0) / systolicValues.length) * 10) / 10,
    }
    summary.diastolic = {
      min: Math.min(...diastolicValues),
      max: Math.max(...diastolicValues),
      avg: Math.round((diastolicValues.reduce((sum, value) => sum + value, 0) / diastolicValues.length) * 10) / 10,
    }
  }
  else if (values.length) {
    summary.min = Math.min(...values)
    summary.max = Math.max(...values)
    summary.avg = Math.round((values.reduce((sum, value) => sum + value, 0) / values.length) * 10) / 10
  }

  return {
    metric,
    label,
    unit,
    date: dateRangeLabel(dates),
    scope: 'multi_day',
    source,
    summary,
    series,
  }
}

export function parseHealthMetricCard(
  artifact: Record<string, unknown> | null | undefined,
): HealthMetricCardData | null {
  const root = asRecord(artifact)
  if (!root) return null
  return combineMultiDayHealthMetric(healthMetricPayloads(root))
}
