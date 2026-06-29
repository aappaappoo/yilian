import { getChatMessageText, type ChatContentBlock, type ChatMessage } from '../composables/useChat'

export interface ConversationAssistantMessage {
  id: string
  time: string
  text: string
  contentBlocks?: ChatContentBlock[]
  hasContent: boolean
  streaming?: boolean
  pending?: ChatMessage['pending']
  source?: string
  artifact?: Record<string, unknown>
}

export interface ConversationRound {
  id: number
  time: string
  userMsg: string
  assistantMsg: string
  assistantPending?: ChatMessage['pending']
  assistantSource?: string
  assistantArtifact?: Record<string, unknown>
  assistantMessages: ConversationAssistantMessage[]
}

function hasReferenceArtifact(artifact?: Record<string, unknown>): boolean {
  const references = artifact?.references
  if (!Array.isArray(references)) return false
  return references.some((item) => {
    if (!item || typeof item !== 'object') return false
    const url = (item as Record<string, unknown>).url
    return typeof url === 'string' && /^https?:\/\//i.test(url)
  })
}

export function buildConversationRounds(
  messages: ChatMessage[],
  formatTime: (date: Date) => string,
): ConversationRound[] {
  const rounds: ConversationRound[] = []
  let roundId = 0
  let currentRound: ConversationRound | null = null

  for (const msg of messages) {
    if (msg.role === 'user') {
      roundId++
      currentRound = {
        id: roundId,
        time: formatTime(msg.timestamp),
        userMsg: msg.text,
        assistantMsg: '',
        assistantPending: undefined,
        assistantSource: undefined,
        assistantArtifact: undefined,
        assistantMessages: [],
      }
      rounds.push(currentRound)
      continue
    }

    if (msg.role === 'assistant' && currentRound) {
      const hasStreamingBlocks = Boolean(msg.streaming && msg.contentBlocks?.length)
      const text = hasStreamingBlocks ? msg.text : getChatMessageText(msg)
      const hasContent = Boolean(
        msg.pending
        || text.trim()
        || msg.contentBlocks?.length
        || hasReferenceArtifact(msg.artifact),
      )
      const assistantMessage: ConversationAssistantMessage = {
        id: msg.id,
        time: formatTime(msg.timestamp),
        text,
        contentBlocks: msg.contentBlocks,
        hasContent,
        streaming: msg.streaming,
        pending: msg.pending,
        source: msg.source,
        artifact: msg.artifact,
      }
      currentRound.assistantMessages.push(assistantMessage)

      currentRound.assistantMsg = text
      currentRound.assistantPending = msg.pending
      currentRound.assistantSource = msg.source
      currentRound.assistantArtifact = msg.artifact
    }
  }

  return rounds
}
