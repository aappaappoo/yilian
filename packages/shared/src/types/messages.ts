// 与 Python 后端 DataChannel 消息协议对应

export interface UserTextMessage {
  type: 'user_text'
  text: string
}

export interface UserTextPartialMessage {
  type: 'user_text_partial'
  text: string
}

export interface AssistantTextMessage {
  type: 'assistant_text'
  text: string
  source?: string
  artifact?: Record<string, unknown>
}

export interface AssistantMessageStartMessage {
  type: 'assistant_message_start'
  message_id: string
  source?: string
}

export interface AssistantSourceReference {
  label: string
  url: string
  iconUrl?: string
}

export interface AssistantSourcesMessage {
  type: 'assistant_sources'
  message_id: string
  references: AssistantSourceReference[]
  source?: string
}

export interface ContentBlockStartMessage {
  type: 'content_block_start'
  message_id: string
  block_id: string
  block_type: string
  title?: string
  source?: string
}

export interface ContentBlockDeltaMessage {
  type: 'content_block_delta'
  message_id: string
  block_id: string
  delta: string
}

export interface ContentBlockFinishMessage {
  type: 'content_block_finish'
  message_id: string
  block_id: string
}

export interface AssistantMessageFinishMessage {
  type: 'assistant_message_finish'
  message_id: string
  text?: string
  source?: string
  artifact?: Record<string, unknown>
}

export interface AssistantTextInterruptedMessage {
  type: 'assistant_text_interrupted'
  reason?: string
}

export interface AssistantProcessMessage {
  type: 'assistant_process'
  text: string
}

export interface TaskProgressItemMessage {
  id: string
  name: string
  skill_name?: string
  status: string  // 'queued' | 'running' | 'success' | 'partial_success' | 'failed' | 'cancelled' | 'need_input'
  progress: number
  description: string
  icon?: string
  error_reason?: string
  phase_key?: string    // 阶段唯一标识，如 "fetching_weather"
  phase_label?: string  // 面向用户的阶段描述，如 "请求天气数据源"
  phase_index?: number  // 当前阶段序号（1-based）
  phase_count?: number  // 总阶段数
  attempt?: number      // 重试次数（0=首次，1+=重试）
  retryable?: boolean
  retry_token?: string
  retry_reason?: string
  retry_attempt?: number
  retry_max_attempts?: number
  artifact?: Record<string, unknown>
}

export interface TaskProgressMessage {
  type: 'task_progress'
  title?: string
  status?: string
  summary?: string
  task_count: number
  total_progress: number
  tasks: TaskProgressItemMessage[]
}

export interface EmotionSignalsMessage {
  type: 'emotion_signals'
  sadness: number
  anxiety: number
  anger: number
  label: string
  keywords: string[]
}

export interface NodeChangeMessage {
  type: 'node_change'
  node: string
}

export interface ToolsUpdateMessage {
  type: 'tools_update'
  tools: string[]
}

export type ServerMessage =
  | UserTextMessage
  | UserTextPartialMessage
  | AssistantTextMessage
  | AssistantMessageStartMessage
  | AssistantSourcesMessage
  | ContentBlockStartMessage
  | ContentBlockDeltaMessage
  | ContentBlockFinishMessage
  | AssistantMessageFinishMessage
  | AssistantTextInterruptedMessage
  | AssistantProcessMessage
  | TaskProgressMessage
  | EmotionSignalsMessage
  | NodeChangeMessage
  | ToolsUpdateMessage
