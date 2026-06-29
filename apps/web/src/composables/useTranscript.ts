// Usage: pass the RTCDataChannel instance from useWebRTC's `dataChannel` ref.
// Example: const { committed, pending } = useTranscript(dataChannel.value!)
import { ref, onBeforeUnmount } from 'vue'

export function useTranscript(dc: RTCDataChannel, opts: { debug?: boolean } = {}) {
  const committed = ref<string>('')   // 已定稿（final 累积）
  const pending   = ref<string>('')   // 当前 partial，可被覆盖

  const onMessage = (e: MessageEvent) => {
    let msg: any
    try { msg = JSON.parse(typeof e.data === 'string' ? e.data : '') } catch { return }
    if (!msg || typeof msg.type !== 'string') return

    switch (msg.type) {
      case 'user_text_partial':
        // 整段替换 pending，制造"实时改写"的视觉效果
        pending.value = msg.text ?? ''
        if (opts.debug) console.debug('[useTranscript] partial:', msg.text)
        break
      case 'user_text':
        // 定稿：append 到 committed，清空 pending
        if (msg.text) {
          committed.value += (committed.value ? '\n' : '') + msg.text
        }
        pending.value = ''
        if (opts.debug) console.debug('[useTranscript] final:', msg.text)
        break
      case 'user_text_correct':
        // 预留：LLM 后纠结果替换最后一句 final（本 PR 暂不实现产生方）
        if (msg.text) {
          committed.value = replaceLastLine(committed.value, msg.text)
        }
        if (opts.debug) console.debug('[useTranscript] correct:', msg.text)
        break
    }
  }

  dc.addEventListener('message', onMessage)
  onBeforeUnmount(() => dc.removeEventListener('message', onMessage))

  return { committed, pending }
}

function replaceLastLine(s: string, replacement: string): string {
  const i = s.lastIndexOf('\n')
  return i < 0 ? replacement : s.slice(0, i + 1) + replacement
}
