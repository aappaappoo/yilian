export type AudienceType = string

export interface SessionInfo {
  sessionId: string
  audience: AudienceType
  currentNode: string
  connectedAt: string
}

export interface EmotionState {
  sadness: number
  anxiety: number
  anger: number
  label: string
  keywords: string[]
}
