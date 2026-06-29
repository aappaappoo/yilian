export interface BotReplyImage {
  url: string
  alt: string
  caption: string
  sourceUrl?: string
  sourceTitle?: string
}

const IMAGE_LIMIT = 6
const REFERENCE_LIMIT = 12
const MARKDOWN_LINK_PATTERN = /\[([^\]\n]{1,160})\]\((https?:\/\/[^\s)]+)\)/g
const BARE_URL_PATTERN = /https?:\/\/[^\s<>\])）"'，。；;、]+/g
const REFERENCE_HEADING_PATTERN = /^\s*(?:#{1,6}\s*)?(?:\*\*)?\s*(?:(?:第\s*)?(?:[一二三四五六七八九十百\d]+)\s*[、.．)：:]\s*)?(?:\*\*)?\s*(?:参考链接|参考资料|参考来源|参考网页|参考文献|引用链接|引用来源|资料来源|来源链接|信息来源)\s*(?:\*\*)?\s*(?:[：:].*)?$/

export interface BotReplyReference {
  label: string
  url: string
  iconUrl?: string
}

export interface BotReplyReferencePresentation {
  bodyText: string
  references: BotReplyReference[]
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

function stringField(source: Record<string, unknown> | null, key: string): string {
  const value = source?.[key]
  return typeof value === 'string' ? value.trim() : ''
}

function referenceLabelForUrl(url: string): string {
  const host = url
    .replace(/^https?:\/\//i, '')
    .replace(/^www\./i, '')
    .split('/', 1)[0]
    .toLowerCase()
  const known: Record<string, string> = {
    'gov.cn': '中国政府网',
    'cctv.com': '央视网',
    'news.cctv.com': '央视网',
    'nhsa.gov.cn': '国家医保局',
    '12306.cn': '12306',
    'kyfw.12306.cn': '12306',
  }
  return known[host] || host || '参考链接'
}

function appendReference(
  references: BotReplyReference[],
  seen: Set<string>,
  label: string,
  url: string,
  iconUrl = '',
): void {
  const cleanUrl = url.trim().replace(/[.,，。；;、]+$/, '')
  if (!cleanUrl || seen.has(cleanUrl)) return
  seen.add(cleanUrl)
  const cleanIconUrl = iconUrl.trim()
  const safeIconUrl = cleanIconUrl && isSafeImageUrl(cleanIconUrl) ? cleanIconUrl : ''
  references.push({
    label: label.replace(/[[\]]/g, '').trim() || referenceLabelForUrl(cleanUrl),
    url: cleanUrl,
    ...(safeIconUrl ? { iconUrl: safeIconUrl } : {}),
  })
}

function collectReferencesFromText(text: string): BotReplyReference[] {
  const references: BotReplyReference[] = []
  const seen = new Set<string>()

  for (const match of text.matchAll(MARKDOWN_LINK_PATTERN)) {
    appendReference(references, seen, match[1] || '', match[2] || '')
  }
  for (const match of text.matchAll(BARE_URL_PATTERN)) {
    appendReference(references, seen, referenceLabelForUrl(match[0] || ''), match[0] || '')
  }

  return references
}

function hasWebReferenceArtifact(artifact?: Record<string, unknown> | null): boolean {
  if (!artifact) return false
  if (Array.isArray(artifact.references)) return true
  const tools = Array.isArray(artifact.tools_used)
    ? artifact.tools_used.map(item => String(item)).join(',')
    : ''
  const sourceText = [
    artifact.tool,
    artifact.source,
    tools,
  ].filter(Boolean).join(' ')
  return /web_(?:search|extract)/i.test(sourceText)
}

function iconUrlFromRecord(record: Record<string, unknown>): string {
  const direct = stringField(record, 'favicon')
    || stringField(record, 'faviconUrl')
    || stringField(record, 'favicon_url')
    || stringField(record, 'icon')
    || stringField(record, 'iconUrl')
    || stringField(record, 'icon_url')
    || stringField(record, 'siteIcon')
    || stringField(record, 'site_icon')
    || stringField(record, 'logo')
    || stringField(record, 'logoUrl')
    || stringField(record, 'logo_url')
  return direct && isSafeImageUrl(direct) ? direct : ''
}

function collectReferencesFromArtifactValue(
  value: unknown,
  references: BotReplyReference[],
  seen: Set<string>,
  depth = 0,
): void {
  if (references.length >= REFERENCE_LIMIT || depth > 8) return
  if (Array.isArray(value)) {
    for (const item of value) {
      collectReferencesFromArtifactValue(item, references, seen, depth + 1)
      if (references.length >= REFERENCE_LIMIT) return
    }
    return
  }

  const record = asRecord(value)
  if (!record) return

  const rawUrl = stringField(record, 'url')
  if (rawUrl && /^https?:\/\//i.test(rawUrl)) {
    const label = stringField(record, 'title')
      || stringField(record, 'name')
      || stringField(record, 'label')
      || stringField(record, 'source')
    appendReference(references, seen, label, rawUrl, iconUrlFromRecord(record))
  }

  for (const [key, child] of Object.entries(record)) {
    if (references.length >= REFERENCE_LIMIT) return
    if (/^(content|text|description|markdown|raw|trace|logs|messages|prompt|diagnostics)$/i.test(key)) continue
    if (child && typeof child === 'object') {
      collectReferencesFromArtifactValue(child, references, seen, depth + 1)
    }
  }
}

export function extractBotReplyReferencesFromArtifact(
  artifact?: Record<string, unknown> | null,
): BotReplyReference[] {
  if (!hasWebReferenceArtifact(artifact)) return []
  const references: BotReplyReference[] = []
  collectReferencesFromArtifactValue(artifact, references, new Set<string>())
  return references
}

export function mergeBotReplyReferences(...groups: BotReplyReference[][]): BotReplyReference[] {
  const references: BotReplyReference[] = []
  const seen = new Set<string>()
  for (const group of groups) {
    for (const reference of group) {
      if (references.length >= REFERENCE_LIMIT) return references
      appendReference(references, seen, reference.label, reference.url, reference.iconUrl)
    }
  }
  return references
}

export function extractBotReplyReferencePresentation(text: string): BotReplyReferencePresentation {
  const source = (text || '').replace(/\r\n/g, '\n').trim()
  if (!source) return { bodyText: '', references: [] }

  const lines = source.split('\n')
  const firstReferenceIndex = lines.findIndex(line => REFERENCE_HEADING_PATTERN.test(line.trim()))
  if (firstReferenceIndex < 0) return { bodyText: source, references: [] }

  const bodyText = lines.slice(0, firstReferenceIndex).join('\n').trim()
  const referenceText = lines.slice(firstReferenceIndex).join('\n')
  const references = collectReferencesFromText(referenceText)
  return { bodyText, references }
}

function isSafeImageUrl(url: string): boolean {
  return /^https?:\/\//i.test(url) || /^data:image\//i.test(url) || url.startsWith('/')
}

function isLikelyImageUrl(url: string): boolean {
  if (/^data:image\//i.test(url)) return true
  const cleanUrl = url.split(/[?#]/, 1)[0]
  return /\.(?:avif|bmp|gif|jpe?g|png|svg|webp)$/i.test(cleanUrl)
}

function imageUrlFromRecord(record: Record<string, unknown>): string {
  const direct = stringField(record, 'photo')
    || stringField(record, 'photoUrl')
    || stringField(record, 'image')
    || stringField(record, 'imageUrl')
    || stringField(record, 'thumbnail')
    || stringField(record, 'thumbnailUrl')
  if (direct && isSafeImageUrl(direct)) return direct

  const genericUrl = stringField(record, 'url')
  if (genericUrl && isSafeImageUrl(genericUrl) && isLikelyImageUrl(genericUrl)) return genericUrl

  const photos = record.photos
  if (Array.isArray(photos)) {
    for (const item of photos) {
      const photo = asRecord(item)
      const url = stringField(photo, 'url') || stringField(photo, 'photo') || stringField(photo, 'image')
      if (url && isSafeImageUrl(url)) return url
    }
  }

  return ''
}

function imageLabelFromRecord(record: Record<string, unknown>): string {
  return stringField(record, 'name')
    || stringField(record, 'title')
    || stringField(record, 'label')
    || stringField(record, 'address')
    || 'Aini 找到的图片'
}

function collectImagesFromValue(
  value: unknown,
  images: BotReplyImage[],
  seen: Set<string>,
  depth = 0,
): void {
  if (images.length >= IMAGE_LIMIT || depth > 8) return
  if (Array.isArray(value)) {
    for (const item of value) {
      collectImagesFromValue(item, images, seen, depth + 1)
      if (images.length >= IMAGE_LIMIT) return
    }
    return
  }

  const record = asRecord(value)
  if (!record) return

  const url = imageUrlFromRecord(record)
  if (url && !seen.has(url)) {
    const label = imageLabelFromRecord(record)
    const sourceUrl = stringField(record, 'sourceUrl') || stringField(record, 'url')
    seen.add(url)
    images.push({
      url,
      alt: label,
      caption: label,
      sourceUrl: /^https?:\/\//i.test(sourceUrl) ? sourceUrl : undefined,
      sourceTitle: label,
    })
  }

  for (const [key, child] of Object.entries(record)) {
    if (images.length >= IMAGE_LIMIT) return
    if (/^(raw|trace|logs|messages|prompt|diagnostics)$/i.test(key)) continue
    if (child && typeof child === 'object') {
      collectImagesFromValue(child, images, seen, depth + 1)
    }
  }
}

export function extractBotReplyImages(artifact?: Record<string, unknown> | null): BotReplyImage[] {
  if (!artifact) return []
  const images: BotReplyImage[] = []
  collectImagesFromValue(artifact, images, new Set<string>())
  return images
}

function boldKnownLabel(line: string): string {
  const match = line.match(/^(来源|首选|建议|老人出行判断|穿衣建议|出行建议|温馨提醒|提醒|注意|小结|结论)[：:]\s*(.+)$/)
  if (match) return `**${match[1]}**：${match[2]}`
  if (line.startsWith('建议')) {
    return `**建议**：${line.slice(2).replace(/^[:：]?\s*/, '')}`
  }
  return line
}

function formatIntroLine(line: string): string {
  const weather = line.match(/^(.+?天气预报)(?:如下)?[：:]\s*$/)
  if (weather) return `**${weather[1]}**`
  const found = line.match(/^(我(?:为您|为你|帮您|帮你)?查到.+?)[：:]\s*$/)
  if (found) return `**${found[1]}**`
  const train = line.match(/^(我查到\s*.+?车次.+?)[：:]\s*$/)
  if (train) return `**${train[1]}**`
  return boldKnownLabel(line)
}

function formatSemicolonDetail(piece: string): string {
  const source = piece.trim()
  const labelMatch = source.match(/^(评分|人均\/参考价|人均|参考价|距离|营业\/开放|营业时间|开放时间|地址|电话|类型|特色|标签)[：:]?\s*(.+)$/)
  if (labelMatch) return `   - **${labelMatch[1]}**：${labelMatch[2]}`

  const compactMatch = source.match(/^(评分|距离)(.+)$/)
  if (compactMatch) return `   - **${compactMatch[1]}**：${compactMatch[2]}`

  const costMatch = source.match(/^(人均\/参考价|人均|参考价)(.+)$/)
  if (costMatch) return `   - **${costMatch[1]}**：${costMatch[2]}`

  if (/(路|街|巷|号|区|县|镇|村|楼|层|广场|中心|商场|店)/.test(source)) {
    return `   - **地址**：${source}`
  }

  return `   - **特色**：${source}`
}

function formatNumberedLine(line: string): string {
  const match = line.match(/^(\d+)[.、]\s*(.+)$/)
  if (!match) return line

  const index = match[1]
  const body = match[2].trim()
  const pieces = body.split(/[；;]/).map(item => item.trim()).filter(Boolean)
  if (pieces.length > 1) {
    const [title, ...details] = pieces
    return [
      `${index}. **${title}**`,
      ...details.map(formatSemicolonDetail),
    ].join('\n')
  }

  const colon = body.match(/^([^：:]{1,28})[：:]\s*(.+)$/)
  if (colon) return `${index}. **${colon[1]}**：${colon[2]}`
  return `${index}. ${body}`
}

function formatBulletLine(line: string): string {
  const match = line.match(/^[-*]\s+(.+)$/)
  if (!match) return line
  const body = match[1].trim()
  const date = body.match(/^(\d{4}-\d{2}-\d{2})[：:]\s*(.+)$/)
  if (date) return `- **${date[1]}**：${date[2]}`
  return `- ${boldKnownLabel(body)}`
}

function getMarkdownTableCells(line: string): string[] | null {
  const trimmed = line.trim()
  if (!trimmed.includes('|')) return null

  const cells = trimmed
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map(cell => cell.trim())

  if (cells.length < 2 || cells.every(cell => !cell)) return null
  return cells
}

function isLikelyMarkdownTableRow(line: string): boolean {
  return getMarkdownTableCells(line) !== null
}

function isMarkdownTableDelimiter(line: string): boolean {
  const cells = getMarkdownTableCells(line)
  return Boolean(cells?.every(cell => /^:?-{3,}:?$/.test(cell)))
}

function collectMarkdownTableLineIndexes(lines: string[]): Set<number> {
  const tableIndexes = new Set<number>()

  for (let index = 0; index < lines.length - 1; index++) {
    if (!isLikelyMarkdownTableRow(lines[index]) || !isMarkdownTableDelimiter(lines[index + 1])) {
      continue
    }

    tableIndexes.add(index)
    tableIndexes.add(index + 1)

    let rowIndex = index + 2
    while (rowIndex < lines.length && isLikelyMarkdownTableRow(lines[rowIndex])) {
      tableIndexes.add(rowIndex)
      rowIndex += 1
    }

    index = rowIndex - 1
  }

  return tableIndexes
}

export function formatBotReplyMarkdown(text: string): string {
  const source = extractBotReplyReferencePresentation(text).bodyText
  if (!source) return ''

  const lines = source
    .split('\n')
    .map(line => line.trim())
    .filter(Boolean)
  const tableLineIndexes = collectMarkdownTableLineIndexes(lines)

  const formatted = lines.map((line, index) => {
    if (tableLineIndexes.has(index)) {
      return { text: line, isTable: true }
    }

    if (/^[-*]\s+/.test(line)) {
      return { text: formatBulletLine(line), isTable: false }
    } else if (/^\d+[.、]\s+/.test(line)) {
      return { text: formatNumberedLine(line), isTable: false }
    }

    return { text: formatIntroLine(line), isTable: false }
  })

  return formatted.reduce((result, item, index) => {
    if (index === 0) return item.text
    const previous = formatted[index - 1]
    const separator = previous.isTable && item.isTable ? '\n' : '\n\n'
    return `${result}${separator}${item.text}`
  }, '')
}
