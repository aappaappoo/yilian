<script setup lang="ts">
import type { EmotionState } from '@soulmeet/shared'
import type { CharacterState, ConnectionStatus } from '../types'
import VRMModel from './VRMModel.vue'
import AvatarFallback from './AvatarFallback.vue'

const props = withDefaults(defineProps<{
  emotionState: EmotionState
  connectionStatus: ConnectionStatus
  streamingMessage?: any
  modelUrl?: string
  mini?: boolean
  disabled?: boolean
  modelScale?: number
}>(), {
  mini: false,
  disabled: false,
  modelScale: 1,
})

const emit = defineEmits<{
  (e: 'state-change', state: CharacterState): void
}>()

function handleStateChange(state: CharacterState) {
  emit('state-change', state)
}
</script>

<template>
  <div class="avatar-canvas" :class="{ 'avatar-canvas--mini': mini }">
    <!-- mini 或调试禁用 3D 时直接渲染 fallback，不加载 VRM。 -->
    <AvatarFallback v-if="mini || disabled" :mini="mini" />

    <!-- 桌面端/平板端 3D 渲染 -->
    <VRMModel
      v-else
      :emotion-state="emotionState"
      :connection-status="connectionStatus"
      :streaming-message="streamingMessage"
      :model-url="modelUrl"
      :mini="mini"
      :model-scale="modelScale"
      @state-change="handleStateChange"
    />
  </div>
</template>

<style scoped>
.avatar-canvas {
  width: 100%;
  height: 100%;
  overflow: hidden;
  border-radius: 0.5rem;
  background-color: transparent;
}

.avatar-canvas--mini {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}
</style>
