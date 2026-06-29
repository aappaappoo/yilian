export interface WeatherForecastDayData {
  date: string
  condition: string
  minTemp: string
  maxTemp: string
  rainChance?: string
}

export interface WeatherForecastCardData {
  city: string
  days: number
  forecast: WeatherForecastDayData[]
}

const chineseConditionPattern = /(雷阵雨|雨夹雪|小阵雨|暴雨|大雨|中雨|小雨|轻雨|阵雨|大雪|中雪|小雪|局部多云|多云|晴|阴|雾|霾)/

const englishConditionMap: Array<[RegExp, string]> = [
  [/(thunder|thundery|thunderstorm)/i, '雷阵雨'],
  [/(sleet|freezing rain)/i, '雨夹雪'],
  [/(heavy snow|blizzard)/i, '大雪'],
  [/(moderate snow)/i, '中雪'],
  [/(light snow|snow shower|patchy snow)/i, '小雪'],
  [/(heavy rain|torrential rain)/i, '大雨'],
  [/(moderate rain)/i, '中雨'],
  [/(light rain shower|rain shower|light shower|patchy rain|light rain|drizzle)/i, '小阵雨'],
  [/(overcast)/i, '阴'],
  [/(partly cloudy)/i, '局部多云'],
  [/(cloudy|cloud)/i, '多云'],
  [/(fog|mist)/i, '雾'],
  [/(haze)/i, '霾'],
  [/(clear|sunny)/i, '晴'],
]

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

function firstText(...values: unknown[]): string {
  for (const value of values) {
    const text = textField(value)
    if (text) return text
  }
  return ''
}

function numberField(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  const parsed = Number.parseInt(textField(value), 10)
  return Number.isFinite(parsed) ? parsed : 0
}

function normalizeCondition(value: unknown): string {
  const source = textField(value)
  if (!source) return '天气待确认'
  const chinese = source.match(chineseConditionPattern)?.[1]
  if (chinese) return chinese
  return englishConditionMap.find(([pattern]) => pattern.test(source))?.[1] || '天气待确认'
}

function normalizeTemp(value: unknown): string {
  return textField(value)
    .replace(/\s+/g, '')
    .replace(/摄氏度/g, '')
    .replace(/°C/gi, '')
    .replace(/℃/g, '')
    .replace(/度/g, '')
}

function normalizeForecastDay(value: unknown): WeatherForecastDayData | null {
  const item = asRecord(value)
  if (!item) return null

  const date = textField(item.date)
  const condition = normalizeCondition(firstText(
    item.condition,
    item.dayweather,
    item.dayWeather,
    item.nightweather,
    item.nightWeather,
  ))
  const minTemp = normalizeTemp(firstText(
    item.min_temp,
    item.minTemp,
    item.low_temp,
    item.lowTemp,
    item.nighttemp,
    item.nightTemp,
  ))
  const maxTemp = normalizeTemp(firstText(
    item.max_temp,
    item.maxTemp,
    item.high_temp,
    item.highTemp,
    item.daytemp,
    item.dayTemp,
  ))
  if (!date || !minTemp || !maxTemp) return null

  const rainChance = textField(item.rain_chance ?? item.rainChance)
  return { date, condition, minTemp, maxTemp, rainChance }
}

function normalizeForecastPayload(value: unknown): WeatherForecastCardData | null {
  const root = asRecord(value)
  if (!root) return null

  const forecast = arrayField(root.forecast)
    .map(normalizeForecastDay)
    .filter((item): item is WeatherForecastDayData => !!item)
  if (!forecast.length) return null

  const city = textField(root.city) || '天气预报'
  const days = numberField(root.days) || forecast.length
  return { city, days, forecast }
}

function nestedForecastPayload(root: Record<string, unknown>): unknown {
  const directResult = asRecord(root.result)
  const nestedResult = asRecord(directResult?.result)
  if (Array.isArray(directResult?.forecast)) return directResult
  if (Array.isArray(nestedResult?.forecast)) return nestedResult
  if (Array.isArray(root.forecast)) return root

  for (const card of [...arrayField(root.cards), ...arrayField(directResult?.cards)]) {
    const item = asRecord(card)
    if (textField(item?.type) === 'weather_forecast') {
      return asRecord(item?.fields) || asRecord(item?.artifact)?.result
    }
  }

  for (const entry of arrayField(root.artifacts)) {
    const item = asRecord(entry)
    if (!item) continue
    const artifact = asRecord(item.artifact) || item
    if (textField(artifact.skill_name ?? artifact.skillName) === 'weather.forecast') return artifact.result
  }

  return null
}

export function parseWeatherForecastArtifact(
  artifact: Record<string, unknown> | null | undefined,
): WeatherForecastCardData | null {
  const root = asRecord(artifact)
  if (!root) return null
  return normalizeForecastPayload(nestedForecastPayload(root))
}

export function parseWeatherForecastReply(text: string): WeatherForecastCardData | null {
  const source = (text || '').replace(/\r\n/g, '\n').trim()
  if (!/(未来\s*\d+\s*天.{0,8}天气预报|天气预报)/.test(source)) return null

  const header = source.match(/^([^\s：:，,。；;]{1,12})未来\s*(\d+)\s*天.{0,8}天气预报/)
  const city = header?.[1] || '天气预报'
  const days = Number.parseInt(header?.[2] || '', 10) || 0
  const forecast: WeatherForecastDayData[] = []
  const linePattern = /(\d{4}-\d{2}-\d{2})[：:]\s*([^，,；;\n]+?)\s*[，,]\s*(-?\d+)\s*(?:~|-|到)\s*(-?\d+)\s*(?:°C|℃|摄氏度|度)?(?:[，,]\s*降雨概率约\s*([0-9]{1,3})%)?/gi

  for (const match of source.matchAll(linePattern)) {
    forecast.push({
      date: match[1],
      condition: normalizeCondition(match[2]),
      minTemp: normalizeTemp(match[3]),
      maxTemp: normalizeTemp(match[4]),
      rainChance: match[5] || '',
    })
  }

  if (!forecast.length) return null
  return { city, days: days || forecast.length, forecast }
}

export function parseWeatherForecastCard(
  artifact: Record<string, unknown> | null | undefined,
  text: string,
): WeatherForecastCardData | null {
  return parseWeatherForecastArtifact(artifact) || parseWeatherForecastReply(text)
}
