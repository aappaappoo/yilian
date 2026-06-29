import assert from 'node:assert/strict'
import test from 'node:test'
import { marked } from 'marked'
import {
  extractBotReplyImages,
  extractBotReplyReferencePresentation,
  extractBotReplyReferencesFromArtifact,
  formatBotReplyMarkdown,
  mergeBotReplyReferences,
} from '../src/components/chat/botReplyFormatting.ts'

marked.setOptions({ breaks: true })

function rendersTable(markdown: string): boolean {
  return marked.parse(formatBotReplyMarkdown(markdown)).includes('<table>')
}

test('preserves markdown tables with outer pipes', () => {
  assert.equal(rendersTable([
    '连江美食一日游：',
    '',
    '| 时间 | 安排 | 特色美食 |',
    '| --- | --- | --- |',
    '| 09:00 | 到达连江 | 鱼丸 |',
    '| 12:00 | 午餐 | 锅边糊 |',
  ].join('\n')), true)
})

test('preserves GFM tables without outer pipes', () => {
  assert.equal(rendersTable([
    '连江美食一日游：',
    '',
    '时间 | 安排 | 特色美食',
    '--- | --- | ---',
    '09:00 | 到达连江 | 鱼丸',
    '12:00 | 午餐 | 锅边糊',
  ].join('\n')), true)
})

test('extracts reference links for the read sources disclosure', () => {
  const parsed = extractBotReplyReferencePresentation([
    '厦门是一座很适合慢下来的海边城市。',
    '',
    '**参考链接：**',
    '- [厦门文旅](https://example.com/xiamen)',
    '- https://example.org/weather',
  ].join('\n'))

  assert.equal(parsed.bodyText, '厦门是一座很适合慢下来的海边城市。')
  assert.deepEqual(parsed.references, [
    { label: '厦门文旅', url: 'https://example.com/xiamen' },
    { label: 'example.org', url: 'https://example.org/weather' },
  ])
})

test('removes the trailing reference section from formatted markdown', () => {
  const formatted = formatBotReplyMarkdown([
    '厦门攻略：',
    '',
    '**参考链接：**',
    '- [厦门文旅](https://example.com/xiamen)',
  ].join('\n'))

  assert.equal(formatted.includes('参考链接'), false)
  assert.equal(formatted.includes('https://example.com/xiamen'), false)
})

test('removes trailing reference source headings without urls', () => {
  const formatted = formatBotReplyMarkdown([
    '厦门攻略：',
    '',
    '参考来源',
    '《海滨之城，厦门旅游攻略，玩转厦门必去的10大景点》— 澎湃新闻',
  ].join('\n'))

  assert.equal(formatted.includes('参考来源'), false)
  assert.equal(formatted.includes('澎湃新闻'), false)
})

test('removes inline trailing reference source headings', () => {
  const formatted = formatBotReplyMarkdown([
    '厦门攻略：',
    '',
    '参考来源：《海滨之城，厦门旅游攻略，玩转厦门必去的10大景点》— 澎湃新闻',
  ].join('\n'))

  assert.equal(formatted.includes('参考来源'), false)
  assert.equal(formatted.includes('澎湃新闻'), false)
})

test('removes numbered trailing reference source headings', () => {
  const formatted = formatBotReplyMarkdown([
    '厦门攻略：',
    '',
    '六、参考来源',
    '海滨之城，厦门旅游攻略',
  ].join('\n'))

  assert.equal(formatted.includes('参考来源'), false)
  assert.equal(formatted.includes('海滨之城'), false)
})

test('extracts early web references from artifacts', () => {
  const references = extractBotReplyReferencesFromArtifact({
    tool: 'soul_companion_agent',
    tools_used: ['web_search'],
    references: [
      { label: '厦门文旅', url: 'https://example.com/xiamen' },
    ],
  })

  assert.deepEqual(references, [
    { label: '厦门文旅', url: 'https://example.com/xiamen' },
  ])
})

test('preserves source icons from web artifacts', () => {
  const references = extractBotReplyReferencesFromArtifact({
    tool: 'soul_companion_agent',
    tools_used: ['web_search'],
    web_search: {
      results: [
        {
          title: '厦门文旅',
          url: 'https://example.com/xiamen',
          favicon: 'https://example.com/favicon.ico',
        },
      ],
    },
  })

  assert.deepEqual(references, [
    {
      label: '厦门文旅',
      url: 'https://example.com/xiamen',
      iconUrl: 'https://example.com/favicon.ico',
    },
  ])
})

test('extracts web search preview images with source links', () => {
  const images = extractBotReplyImages({
    tool: 'soul_companion_agent',
    tools_used: ['web_search'],
    web_search: {
      results: [
        {
          title: '中山路骑楼',
          url: 'https://example.com/xiamen-zhongshan',
          image: 'https://cdn.example.com/xiamen-zhongshan.jpg',
        },
      ],
    },
  })

  assert.deepEqual(images, [
    {
      url: 'https://cdn.example.com/xiamen-zhongshan.jpg',
      alt: '中山路骑楼',
      caption: '中山路骑楼',
      sourceUrl: 'https://example.com/xiamen-zhongshan',
      sourceTitle: '中山路骑楼',
    },
  ])
})

test('deduplicates artifact and trailing text references', () => {
  const merged = mergeBotReplyReferences(
    [{ label: '厦门文旅', url: 'https://example.com/xiamen' }],
    [{ label: '重复链接', url: 'https://example.com/xiamen' }],
  )

  assert.deepEqual(merged, [
    { label: '厦门文旅', url: 'https://example.com/xiamen' },
  ])
})
