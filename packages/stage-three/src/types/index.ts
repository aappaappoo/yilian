import type { EmotionState } from '@soulmeet/shared'
import type { VRM } from '@pixiv/three-vrm'

// ─── CharacterState ───────────────────────────────────
export type CharacterState =
  | 'loading'
  | 'idle'
  | 'speaking'
  | 'error'
  | 'fallback'
  | 'listening'   // 预留
  | 'thinking'    // 预留

// ─── 组件 Props ─────────────────────────────────────
export type ConnectionStatus = 'idle' | 'connecting' | 'connected' | 'disconnected' | 'error'

export interface AvatarCanvasProps {
  emotionState: EmotionState
  connectionStatus: ConnectionStatus
  modelUrl?: string
  mini?: boolean
  disabled?: boolean
  modelScale?: number
}

// ─── 表情系统 ─────────────────────────────────────────
export interface ExpressionTarget {
  name: string    // 业务表情名（happy / sad / ...）
  value: number   // 目标权重 0~1
}

export interface ExpressionTransition {
  from: Map<string, number>   // VRM preset → 当前权重
  to: Map<string, number>     // VRM preset → 目标权重
  elapsed: number             // 已过渡时间 ms
  duration: number            // 总过渡时间 ms (400)
}

// ─── VRM 加载 ─────────────────────────────────────────
export interface VRMLoadResult {
  vrm: VRM
  availableExpressions: Map<string, string>  // businessName → vrmPreset
  hasBlinkSupport: boolean
  hasHumanoid: boolean
}

export interface VRMValidationWarning {
  type: 'missing_expression' | 'missing_blink' | 'missing_viseme'
  name: string
  message: string
}
