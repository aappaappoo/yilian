import type { Ref, ShallowRef } from 'vue'
import type { VRM } from '@pixiv/three-vrm'
import type { CharacterState } from '../../types'

export interface UseAnimationOptions {
  vrm: ShallowRef<VRM | null>
  availableExpressions: Ref<Map<string, string>>
  characterState: Ref<CharacterState>
}

export interface UseAnimationReturn {
  update: (deltaMs: number) => void
  applyIdlePose: () => void
}

const BLINK_DURATION = 200
const MIN_INTERVAL = 3000
const MAX_INTERVAL = 5000

const BASE_IDLE_ROTATIONS: Record<string, { x: number; y: number; z: number }> = {
  spine: { x: 0.02, y: 0, z: 0 },
  chest: { x: 0, y: 0, z: 0 },
  upperChest: { x: 0, y: 0, z: 0 },
  neck: { x: 0, y: 0, z: 0 },
  head: { x: 0, y: 0, z: 0 },
  leftShoulder: { x: 0, y: 0, z: 0.1 },
  rightShoulder: { x: 0, y: 0, z: -0.1 },
  leftUpperArm: { x: 0, y: 0, z: 1.1 },
  rightUpperArm: { x: 0, y: 0, z: -1.1 },
  leftLowerArm: { x: 0, y: 0, z: 0.15 },
  rightLowerArm: { x: 0, y: 0, z: -0.15 },
}

const VISEME_BLACKLIST = new Set(['aa', 'ee', 'ih', 'oh', 'ou'])

function randomInterval(): number {
  return MIN_INTERVAL + Math.random() * (MAX_INTERVAL - MIN_INTERVAL)
}

export function useAnimation(options: UseAnimationOptions): UseAnimationReturn {
  const { vrm, availableExpressions, characterState } = options

  let blinkState: 'waiting' | 'blinking' = 'waiting'
  let blinkElapsed = 0
  let blinkInterval = randomInterval()
  let blinkWaitElapsed = 0

  function applyIdlePose(): void {
    const v = vrm.value
    if (!v) return

    for (const [boneName, rotation] of Object.entries(BASE_IDLE_ROTATIONS)) {
      const node = v.humanoid?.getNormalizedBoneNode(boneName as any)
      if (!node) continue
      node.rotation.x = rotation.x
      node.rotation.y = rotation.y
      node.rotation.z = rotation.z
    }
  }

  function update(deltaMs: number) {
    const v = vrm.value
    if (!v) return

    const state = characterState.value
    const isActive = state === 'idle' || state === 'speaking'
    if (!isActive) return

    const blinkPreset = availableExpressions.value.get('blink')
    if (!blinkPreset || VISEME_BLACKLIST.has(blinkPreset)) return

    if (blinkState === 'waiting') {
      blinkWaitElapsed += deltaMs
      if (blinkWaitElapsed >= blinkInterval) {
        blinkState = 'blinking'
        blinkElapsed = 0
      }
    }

    if (blinkState === 'blinking') {
      blinkElapsed += deltaMs
      const t = Math.min(blinkElapsed / BLINK_DURATION, 1)
      const blinkValue = Math.sin(Math.PI * t)
      v.expressionManager?.setValue(blinkPreset, blinkValue)

      if (blinkElapsed >= BLINK_DURATION) {
        v.expressionManager?.setValue(blinkPreset, 0)
        blinkState = 'waiting'
        blinkWaitElapsed = 0
        blinkInterval = randomInterval()
      }
    }
  }

  return { update, applyIdlePose }
}
