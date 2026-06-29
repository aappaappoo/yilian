export interface WeatherReplyCardData {
  city: string
  temp: string
  condition: string
  outfit: string
  tip: string
  humidity?: string
  wind?: string
  dateRange?: string
}

function cleanMarkdown(text: string): string {
  return text
    .replace(/\*\*/g, '')
    .replace(/[`#>]/g, '')
    .replace(/^[\s-]+/gm, '')
    .replace(/艾妮为您查询了[^，,。；;\s]{1,12}(?=[，,。；;\s]|$)[，,。；;]?\s*/g, '')
    .replace(/(?:艾妮|Aini|我)\s*为[你您](?:查询了|查询|查了|查到|查)[^，,。；;\s]{0,12}(?=[，,。；;\s]|$)[，,。；;]?\s*/gi, '')
    .replace(/\s+/g, ' ')
    .trim()
}

function normalizeCity(raw?: string): string {
  const city = (raw || '')
    .replace(/[：:].*$/, '')
    .replace(/^(今天|明天|后天|现在|当前|当地|这边|附近)/, '')
    .replace(/(今天|明天|后天|现在|当前|当地|这边|附近|天气|的)$/g, '')
    .trim()
  if (!city || city === '的') return '今日天气'
  return city
}

const chineseConditionPattern = /(雷阵雨|雨夹雪|小阵雨|暴雨|大雨|中雨|小雨|轻雨|阵雨|大雪|中雪|小雪|多云|晴|阴|雾|霾)/

const englishConditionMap: Array<[RegExp, string]> = [
  [/(thunder|thundery|thunderstorm)/i, '雷阵雨'],
  [/(sleet|freezing rain)/i, '雨夹雪'],
  [/(heavy snow|blizzard)/i, '大雪'],
  [/(moderate snow)/i, '中雪'],
  [/(light snow|snow shower|patchy snow)/i, '小雪'],
  [/(heavy rain|torrential rain)/i, '大雨'],
  [/(moderate rain)/i, '中雨'],
  [/(light rain|rain shower|light shower|patchy rain|drizzle)/i, '小雨'],
  [/(overcast)/i, '阴'],
  [/(cloudy|cloud)/i, '多云'],
  [/(fog|mist)/i, '雾'],
  [/(haze)/i, '霾'],
  [/(clear|sunny)/i, '晴'],
]

function normalizeCondition(source: string): string | null {
  const chineseCondition = source.match(chineseConditionPattern)?.[1]
  if (chineseCondition) return chineseCondition

  const englishCondition = englishConditionMap.find(([pattern]) => pattern.test(source))
  return englishCondition?.[1] || null
}

function defaultTipForCondition(condition: string): string {
  if (/(雪|雨夹雪)/.test(condition)) {
    return '注意保暖防滑，出门预留一点路上时间。'
  }
  if (/(雷|暴雨|大雨|中雨|小雨|阵雨|雨)/.test(condition)) {
    return '外出记得带伞，路面湿滑时放慢一点。'
  }
  if (/(雾|霾)/.test(condition)) {
    return '能见度可能偏低，出行注意防护和安全。'
  }
  if (/(晴)/.test(condition)) {
    return '阳光比较明亮，长时间在外可以注意防晒。'
  }
  if (/(阴|云)/.test(condition)) {
    return '天气相对温和，出门前留意临近变化。'
  }
  return '天气可能有变化，出门前再留意一下实时情况。'
}

function extractCity(source: string): string {
  const city = source.match(/(?:今天|明天|后天)?([^，,。；;\s：:]{2,18})(?:今天|明天|后天|现在|当前)?(?:的)?天气/)?.[1]
    || source.match(/^([^：:，,。；;\s]{2,18})\s*[：:]/)?.[1]
    || source.match(/([^，,。；;\s：:]{2,18})(?:现在|当前)?(?:气温|温度)/)?.[1]

  return normalizeCity(city)
}

function padDatePart(value: number): string {
  return String(value).padStart(2, '0')
}

function formatMonthDay(date: Date): string {
  return `${padDatePart(date.getMonth() + 1)}/${padDatePart(date.getDate())}`
}

function addDays(date: Date, days: number): Date {
  const next = new Date(date)
  next.setDate(next.getDate() + days)
  return next
}

function normalizeDateLabel(source: string): string {
  const isoDates = Array.from(source.matchAll(/\b\d{4}-(\d{2})-(\d{2})\b/g))
    .map(match => `${match[1]}/${match[2]}`)
  if (isoDates.length > 1) return `${isoDates[0]}～${isoDates[isoDates.length - 1]}`
  if (isoDates.length === 1) return isoDates[0]

  const slashDates = Array.from(source.matchAll(/\b(\d{1,2})[/-](\d{1,2})\b/g))
    .map(match => `${padDatePart(Number(match[1]))}/${padDatePart(Number(match[2]))}`)
  if (slashDates.length > 1) return `${slashDates[0]}～${slashDates[slashDates.length - 1]}`
  if (slashDates.length === 1) return slashDates[0]

  const chineseDate = source.match(/(\d{1,2})\s*月\s*(\d{1,2})\s*日/)
  if (chineseDate) return `${padDatePart(Number(chineseDate[1]))}/${padDatePart(Number(chineseDate[2]))}`

  const today = new Date()
  if (/后天/.test(source)) return formatMonthDay(addDays(today, 2))
  if (/明天/.test(source)) return formatMonthDay(addDays(today, 1))
  if (/今天|当前|现在/.test(source)) return formatMonthDay(today)
  return ''
}

export function parseWeatherReplyCard(text: string): WeatherReplyCardData | null {
  const source = cleanMarkdown(text)
  if (/(未来\s*\d+\s*天.{0,8}天气预报|天气预报.{0,80}\d{4}-\d{2}-\d{2})/.test(source)) return null
  if (!/(天气|气温|温度|多云|晴|雨|雪|阴|摄氏度|℃|°C|湿度|风)/i.test(source)) return null
  if (/(请问|想查|查询).*(哪个|哪座|具体).*(城市|区县|地点|位置)/.test(source)) return null

  const temp = source.match(/(-?\d+\s*(?:到|-|~)\s*-?\d+\s*(?:摄氏度|℃|°C|度)|-?\d+\s*(?:摄氏度|℃|°C|度))/i)?.[1]
  const condition = normalizeCondition(source)
  if (!temp || !condition) return null

  const city = extractCity(source)
  const outfit = source.match(/(?:穿衣建议|穿搭建议|建议)[：:\s]*([^。；;]+)/)?.[1] || '早晚留意温差，出门可以带一件薄外套。'
  const tip = source.match(/(?:温馨提示|提示|小提醒)[：:\s]*([^。；;]+)/)?.[1] || defaultTipForCondition(condition)
  const humidity = source.match(/湿度[：:\s]*([0-9]{1,3}\s*%)/)?.[1]
  const wind = source.match(/((?:东|南|西|北|东北|东南|西北|西南)风\s*\d+\s*(?:级|级左右)?)/)?.[1]
  const dateRange = normalizeDateLabel(source)

  return { city, temp, condition, outfit, tip, humidity, wind, dateRange }
}
