import { watch, type Ref, type ShallowRef } from 'vue'
import type { VRM } from '@pixiv/three-vrm'
import { EMOTION_FALLBACK_LABEL, EMOTION_STATE_HOLD_MS, type EmotionState } from '@soulmeet/shared'
import type { CharacterState } from '../../types'

type BoneName =
  | 'hips'
  | 'spine'
  | 'chest'
  | 'upperChest'
  | 'neck'
  | 'head'
  | 'leftShoulder'
  | 'rightShoulder'
  | 'leftUpperArm'
  | 'rightUpperArm'
  | 'leftLowerArm'
  | 'rightLowerArm'

interface Rotation {
  x?: number
  y?: number
  z?: number
}

interface Translation {
  x?: number
  y?: number
  z?: number
}

interface BonePose {
  rotation?: Rotation
  position?: Translation
}

interface PoseValues {
  rotation: { x: number; y: number; z: number }
  position: { x: number; y: number; z: number }
}

interface MotionScales {
  speed: number
  amplitude: number
  breath: number
  tremble: number
}

type OneShotKind = 'joyBurst' | 'surpriseBack' | 'urgentSignal'

interface EmotionMotionProfile {
  pose: Partial<Record<BoneName, BonePose>>
  scales: MotionScales
  oneShot?: OneShotKind
}

export interface UseEmotionMotionOptions {
  vrm: ShallowRef<VRM | null>
  emotionState: Ref<EmotionState>
  characterState: Ref<CharacterState>
}

export interface UseEmotionMotionReturn {
  update: (deltaMs: number) => void
}

const TRACKED_BONES: BoneName[] = [
  'hips',
  'spine',
  'chest',
  'upperChest',
  'neck',
  'head',
  'leftShoulder',
  'rightShoulder',
  'leftUpperArm',
  'rightUpperArm',
  'leftLowerArm',
  'rightLowerArm',
]

const BASE_POSE: Record<BoneName, PoseValues> = {
  hips: { rotation: { x: 0, y: 0, z: 0 }, position: { x: 0, y: 0, z: 0 } },
  spine: { rotation: { x: 0.02, y: 0, z: 0 }, position: { x: 0, y: 0, z: 0 } },
  chest: { rotation: { x: 0, y: 0, z: 0 }, position: { x: 0, y: 0, z: 0 } },
  upperChest: { rotation: { x: 0, y: 0, z: 0 }, position: { x: 0, y: 0, z: 0 } },
  neck: { rotation: { x: 0, y: 0, z: 0 }, position: { x: 0, y: 0, z: 0 } },
  head: { rotation: { x: 0, y: 0, z: 0 }, position: { x: 0, y: 0, z: 0 } },
  leftShoulder: { rotation: { x: 0, y: 0, z: 0.1 }, position: { x: 0, y: 0, z: 0 } },
  rightShoulder: { rotation: { x: 0, y: 0, z: -0.1 }, position: { x: 0, y: 0, z: 0 } },
  leftUpperArm: { rotation: { x: 0, y: 0, z: 1.1 }, position: { x: 0, y: 0, z: 0 } },
  rightUpperArm: { rotation: { x: 0, y: 0, z: -1.1 }, position: { x: 0, y: 0, z: 0 } },
  leftLowerArm: { rotation: { x: 0, y: 0, z: 0.15 }, position: { x: 0, y: 0, z: 0 } },
  rightLowerArm: { rotation: { x: 0, y: 0, z: -0.15 }, position: { x: 0, y: 0, z: 0 } },
}

const EMOTION_MOTION_MAP: Record<string, EmotionMotionProfile> = {
  neutral: {
    pose: {},
    scales: { speed: 0.8, amplitude: 0.75, breath: 1, tremble: 0 },
  },
  中性: {
    pose: {},
    scales: { speed: 0.8, amplitude: 0.75, breath: 1, tremble: 0 },
  },
  happy: {
    pose: {
      spine: { rotation: { x: -0.025 } },
      chest: { rotation: { x: -0.035 } },
      head: { rotation: { x: -0.03, z: 0.03 } },
      leftShoulder: { rotation: { x: -0.03, z: -0.08 } },
      rightShoulder: { rotation: { x: -0.03, z: 0.08 } },
      leftUpperArm: { rotation: { x: -0.1, y: -0.04, z: -0.1 } },
      rightUpperArm: { rotation: { x: -0.1, y: 0.04, z: 0.1 } },
    },
    scales: { speed: 1.2, amplitude: 1.25, breath: 1.12, tremble: 0 },
  },
  开心: {
    pose: {
      spine: { rotation: { x: -0.025 } },
      chest: { rotation: { x: -0.035 } },
      head: { rotation: { x: -0.03, z: 0.03 } },
      leftShoulder: { rotation: { x: -0.03, z: -0.08 } },
      rightShoulder: { rotation: { x: -0.03, z: 0.08 } },
      leftUpperArm: { rotation: { x: -0.1, y: -0.04, z: -0.1 } },
      rightUpperArm: { rotation: { x: -0.1, y: 0.04, z: 0.1 } },
    },
    scales: { speed: 1.2, amplitude: 1.25, breath: 1.12, tremble: 0 },
  },
  joy: {
    pose: {
      spine: { rotation: { x: -0.04 } },
      chest: { rotation: { x: -0.05 } },
      head: { rotation: { x: -0.045, z: -0.04 } },
      leftShoulder: { rotation: { x: -0.06, z: -0.16 } },
      rightShoulder: { rotation: { x: -0.06, z: 0.16 } },
      leftUpperArm: { rotation: { x: -0.22, y: -0.1, z: -0.26 } },
      rightUpperArm: { rotation: { x: -0.22, y: 0.1, z: 0.26 } },
      leftLowerArm: { rotation: { x: -0.12, z: -0.08 } },
      rightLowerArm: { rotation: { x: -0.12, z: 0.08 } },
    },
    scales: { speed: 1.55, amplitude: 1.5, breath: 1.25, tremble: 0 },
    oneShot: 'joyBurst',
  },
  喜悦: {
    pose: {
      spine: { rotation: { x: -0.04 } },
      chest: { rotation: { x: -0.05 } },
      head: { rotation: { x: -0.045, z: -0.04 } },
      leftShoulder: { rotation: { x: -0.06, z: -0.16 } },
      rightShoulder: { rotation: { x: -0.06, z: 0.16 } },
      leftUpperArm: { rotation: { x: -0.22, y: -0.1, z: -0.26 } },
      rightUpperArm: { rotation: { x: -0.22, y: 0.1, z: 0.26 } },
      leftLowerArm: { rotation: { x: -0.12, z: -0.08 } },
      rightLowerArm: { rotation: { x: -0.12, z: 0.08 } },
    },
    scales: { speed: 1.55, amplitude: 1.5, breath: 1.25, tremble: 0 },
    oneShot: 'joyBurst',
  },
  calm: {
    pose: {
      spine: { rotation: { x: 0.015 } },
      head: { rotation: { x: 0.025, z: 0.02 } },
      leftShoulder: { rotation: { z: -0.02 } },
      rightShoulder: { rotation: { z: 0.02 } },
    },
    scales: { speed: 0.45, amplitude: 0.42, breath: 0.75, tremble: 0 },
  },
  平静: {
    pose: {
      spine: { rotation: { x: 0.015 } },
      head: { rotation: { x: 0.025, z: 0.02 } },
      leftShoulder: { rotation: { z: -0.02 } },
      rightShoulder: { rotation: { z: 0.02 } },
    },
    scales: { speed: 0.45, amplitude: 0.42, breath: 0.75, tremble: 0 },
  },
  relaxed: {
    pose: {
      hips: { position: { x: 0.01 } },
      spine: { rotation: { x: 0.03, z: 0.02 } },
      head: { rotation: { x: 0.035, z: -0.045 } },
      leftShoulder: { rotation: { x: 0.035, z: -0.06 } },
      rightShoulder: { rotation: { x: 0.035, z: 0.06 } },
      leftUpperArm: { rotation: { x: 0.045, z: 0.04 } },
      rightUpperArm: { rotation: { x: 0.045, z: -0.04 } },
    },
    scales: { speed: 0.55, amplitude: 0.55, breath: 0.9, tremble: 0 },
  },
  放松: {
    pose: {
      hips: { position: { x: 0.01 } },
      spine: { rotation: { x: 0.03, z: 0.02 } },
      head: { rotation: { x: 0.035, z: -0.045 } },
      leftShoulder: { rotation: { x: 0.035, z: -0.06 } },
      rightShoulder: { rotation: { x: 0.035, z: 0.06 } },
      leftUpperArm: { rotation: { x: 0.045, z: 0.04 } },
      rightUpperArm: { rotation: { x: 0.045, z: -0.04 } },
    },
    scales: { speed: 0.55, amplitude: 0.55, breath: 0.9, tremble: 0 },
  },
  sad: {
    pose: {
      spine: { rotation: { x: 0.09 } },
      chest: { rotation: { x: 0.055 } },
      neck: { rotation: { x: 0.04 } },
      head: { rotation: { x: 0.13, z: -0.035 } },
      leftShoulder: { rotation: { x: 0.055, z: 0.1 } },
      rightShoulder: { rotation: { x: 0.055, z: -0.1 } },
      leftUpperArm: { rotation: { x: 0.08, y: 0.03, z: 0.1 } },
      rightUpperArm: { rotation: { x: 0.08, y: -0.03, z: -0.1 } },
    },
    scales: { speed: 0.42, amplitude: 0.35, breath: 0.72, tremble: 0 },
  },
  伤心: {
    pose: {
      spine: { rotation: { x: 0.09 } },
      chest: { rotation: { x: 0.055 } },
      neck: { rotation: { x: 0.04 } },
      head: { rotation: { x: 0.13, z: -0.035 } },
      leftShoulder: { rotation: { x: 0.055, z: 0.1 } },
      rightShoulder: { rotation: { x: 0.055, z: -0.1 } },
      leftUpperArm: { rotation: { x: 0.08, y: 0.03, z: 0.1 } },
      rightUpperArm: { rotation: { x: 0.08, y: -0.03, z: -0.1 } },
    },
    scales: { speed: 0.42, amplitude: 0.35, breath: 0.72, tremble: 0 },
  },
  sorrow: {
    pose: {
      spine: { rotation: { x: 0.13 } },
      chest: { rotation: { x: 0.08 } },
      neck: { rotation: { x: 0.06 } },
      head: { rotation: { x: 0.18, z: 0.045 } },
      leftShoulder: { rotation: { x: 0.075, z: 0.14 } },
      rightShoulder: { rotation: { x: 0.075, z: -0.14 } },
      leftUpperArm: { rotation: { x: 0.12, y: 0.04, z: 0.14 } },
      rightUpperArm: { rotation: { x: 0.12, y: -0.04, z: -0.14 } },
    },
    scales: { speed: 0.28, amplitude: 0.2, breath: 0.62, tremble: 0 },
  },
  哀伤: {
    pose: {
      spine: { rotation: { x: 0.13 } },
      chest: { rotation: { x: 0.08 } },
      neck: { rotation: { x: 0.06 } },
      head: { rotation: { x: 0.18, z: 0.045 } },
      leftShoulder: { rotation: { x: 0.075, z: 0.14 } },
      rightShoulder: { rotation: { x: 0.075, z: -0.14 } },
      leftUpperArm: { rotation: { x: 0.12, y: 0.04, z: 0.14 } },
      rightUpperArm: { rotation: { x: 0.12, y: -0.04, z: -0.14 } },
    },
    scales: { speed: 0.28, amplitude: 0.2, breath: 0.62, tremble: 0 },
  },
  missing_someone: {
    pose: {
      spine: { rotation: { x: 0.08, z: -0.02 } },
      chest: { rotation: { x: 0.05 } },
      head: { rotation: { x: 0.1, y: -0.04, z: 0.055 } },
      leftShoulder: { rotation: { x: 0.02, y: -0.015, z: -0.03 } },
      leftUpperArm: { rotation: { x: 0.035, y: -0.04, z: -0.08 } },
      leftLowerArm: { rotation: { x: 0.02, z: -0.03 } },
      rightShoulder: { rotation: { x: -0.02, z: -0.22 } },
      rightUpperArm: { rotation: { x: -0.22, y: -0.18, z: -0.34 } },
      rightLowerArm: { rotation: { x: -0.2, y: -0.06, z: -0.12 } },
    },
    scales: { speed: 0.38, amplitude: 0.28, breath: 0.74, tremble: 0 },
  },
  想念: {
    pose: {
      spine: { rotation: { x: 0.08, z: -0.02 } },
      chest: { rotation: { x: 0.05 } },
      head: { rotation: { x: 0.1, y: -0.04, z: 0.055 } },
      leftShoulder: { rotation: { x: 0.02, y: -0.015, z: -0.03 } },
      leftUpperArm: { rotation: { x: 0.035, y: -0.04, z: -0.08 } },
      leftLowerArm: { rotation: { x: 0.02, z: -0.03 } },
      rightShoulder: { rotation: { x: -0.02, z: -0.22 } },
      rightUpperArm: { rotation: { x: -0.22, y: -0.18, z: -0.34 } },
      rightLowerArm: { rotation: { x: -0.2, y: -0.06, z: -0.12 } },
    },
    scales: { speed: 0.38, amplitude: 0.28, breath: 0.74, tremble: 0 },
  },
  想恋: {
    pose: {
      spine: { rotation: { x: 0.08, z: -0.02 } },
      chest: { rotation: { x: 0.05 } },
      head: { rotation: { x: 0.1, y: -0.04, z: 0.055 } },
      leftShoulder: { rotation: { x: 0.02, y: -0.015, z: -0.03 } },
      leftUpperArm: { rotation: { x: 0.035, y: -0.04, z: -0.08 } },
      leftLowerArm: { rotation: { x: 0.02, z: -0.03 } },
      rightShoulder: { rotation: { x: -0.02, z: -0.22 } },
      rightUpperArm: { rotation: { x: -0.22, y: -0.18, z: -0.34 } },
      rightLowerArm: { rotation: { x: -0.2, y: -0.06, z: -0.12 } },
    },
    scales: { speed: 0.38, amplitude: 0.28, breath: 0.74, tremble: 0 },
  },
  lonely: {
    pose: {
      spine: { rotation: { x: 0.1, z: 0.025 } },
      chest: { rotation: { x: 0.065 } },
      neck: { rotation: { x: 0.045 } },
      head: { rotation: { x: 0.14, y: 0.035, z: -0.065 } },
      leftShoulder: { rotation: { x: 0.045, y: -0.01, z: 0.06 } },
      rightShoulder: { rotation: { x: 0.055, y: 0.01, z: -0.08 } },
      leftUpperArm: { rotation: { x: 0.07, y: -0.025, z: 0.04 } },
      rightUpperArm: { rotation: { x: 0.08, y: 0.025, z: -0.06 } },
      leftLowerArm: { rotation: { x: 0.05, z: 0.02 } },
      rightLowerArm: { rotation: { x: 0.05, z: -0.03 } },
    },
    scales: { speed: 0.25, amplitude: 0.18, breath: 0.68, tremble: 0 },
  },
  孤独: {
    pose: {
      spine: { rotation: { x: 0.1, z: 0.025 } },
      chest: { rotation: { x: 0.065 } },
      neck: { rotation: { x: 0.045 } },
      head: { rotation: { x: 0.14, y: 0.035, z: -0.065 } },
      leftShoulder: { rotation: { x: 0.045, y: -0.01, z: 0.06 } },
      rightShoulder: { rotation: { x: 0.055, y: 0.01, z: -0.08 } },
      leftUpperArm: { rotation: { x: 0.07, y: -0.025, z: 0.04 } },
      rightUpperArm: { rotation: { x: 0.08, y: 0.025, z: -0.06 } },
      leftLowerArm: { rotation: { x: 0.05, z: 0.02 } },
      rightLowerArm: { rotation: { x: 0.05, z: -0.03 } },
    },
    scales: { speed: 0.25, amplitude: 0.18, breath: 0.68, tremble: 0 },
  },
  孤单: {
    pose: {
      spine: { rotation: { x: 0.1, z: 0.025 } },
      chest: { rotation: { x: 0.065 } },
      neck: { rotation: { x: 0.045 } },
      head: { rotation: { x: 0.14, y: 0.035, z: -0.065 } },
      leftShoulder: { rotation: { x: 0.045, y: -0.01, z: 0.06 } },
      rightShoulder: { rotation: { x: 0.055, y: 0.01, z: -0.08 } },
      leftUpperArm: { rotation: { x: 0.07, y: -0.025, z: 0.04 } },
      rightUpperArm: { rotation: { x: 0.08, y: 0.025, z: -0.06 } },
      leftLowerArm: { rotation: { x: 0.05, z: 0.02 } },
      rightLowerArm: { rotation: { x: 0.05, z: -0.03 } },
    },
    scales: { speed: 0.25, amplitude: 0.18, breath: 0.68, tremble: 0 },
  },
  anxious: {
    pose: {
      spine: { rotation: { x: 0.035, y: -0.015 } },
      chest: { rotation: { x: 0.025 } },
      head: { rotation: { x: -0.015, y: -0.035, z: 0.025 } },
      leftShoulder: { rotation: { x: -0.04, z: 0.12 } },
      rightShoulder: { rotation: { x: -0.04, z: -0.12 } },
      leftUpperArm: { rotation: { x: 0.05, y: 0.04, z: 0.12 } },
      rightUpperArm: { rotation: { x: 0.05, y: -0.04, z: -0.12 } },
    },
    scales: { speed: 2.2, amplitude: 0.7, breath: 1.45, tremble: 0.016 },
  },
  焦虑: {
    pose: {
      spine: { rotation: { x: 0.035, y: -0.015 } },
      chest: { rotation: { x: 0.025 } },
      head: { rotation: { x: -0.015, y: -0.035, z: 0.025 } },
      leftShoulder: { rotation: { x: -0.04, z: 0.12 } },
      rightShoulder: { rotation: { x: -0.04, z: -0.12 } },
      leftUpperArm: { rotation: { x: 0.05, y: 0.04, z: 0.12 } },
      rightUpperArm: { rotation: { x: 0.05, y: -0.04, z: -0.12 } },
    },
    scales: { speed: 2.2, amplitude: 0.7, breath: 1.45, tremble: 0.016 },
  },
  angry: {
    pose: {
      spine: { rotation: { x: -0.04 } },
      chest: { rotation: { x: -0.055 } },
      neck: { rotation: { x: 0.025 } },
      head: { rotation: { x: 0.05, y: 0.015 } },
      leftShoulder: { rotation: { x: -0.08, z: 0.05 } },
      rightShoulder: { rotation: { x: -0.08, z: -0.05 } },
      leftUpperArm: { rotation: { x: -0.06, y: 0.07 } },
      rightUpperArm: { rotation: { x: -0.06, y: -0.07 } },
      leftLowerArm: { rotation: { x: -0.1, z: 0.04 } },
      rightLowerArm: { rotation: { x: -0.1, z: -0.04 } },
    },
    scales: { speed: 1.55, amplitude: 0.5, breath: 1.25, tremble: 0.008 },
  },
  生气: {
    pose: {
      spine: { rotation: { x: -0.04 } },
      chest: { rotation: { x: -0.055 } },
      neck: { rotation: { x: 0.025 } },
      head: { rotation: { x: 0.05, y: 0.015 } },
      leftShoulder: { rotation: { x: -0.08, z: 0.05 } },
      rightShoulder: { rotation: { x: -0.08, z: -0.05 } },
      leftUpperArm: { rotation: { x: -0.06, y: 0.07 } },
      rightUpperArm: { rotation: { x: -0.06, y: -0.07 } },
      leftLowerArm: { rotation: { x: -0.1, z: 0.04 } },
      rightLowerArm: { rotation: { x: -0.1, z: -0.04 } },
    },
    scales: { speed: 1.55, amplitude: 0.5, breath: 1.25, tremble: 0.008 },
  },
  surprise: {
    pose: {
      hips: { position: { z: -0.01 } },
      spine: { rotation: { x: -0.08 } },
      chest: { rotation: { x: -0.065 } },
      neck: { rotation: { x: -0.03 } },
      head: { rotation: { x: -0.09, z: 0.02 } },
      leftShoulder: { rotation: { x: -0.08, z: -0.16 } },
      rightShoulder: { rotation: { x: -0.08, z: 0.16 } },
      leftUpperArm: { rotation: { x: -0.24, y: -0.08, z: -0.24 } },
      rightUpperArm: { rotation: { x: -0.24, y: 0.08, z: 0.24 } },
    },
    scales: { speed: 1.25, amplitude: 1.1, breath: 1.35, tremble: 0.004 },
    oneShot: 'surpriseBack',
  },
  惊讶: {
    pose: {
      hips: { position: { z: -0.01 } },
      spine: { rotation: { x: -0.08 } },
      chest: { rotation: { x: -0.065 } },
      neck: { rotation: { x: -0.03 } },
      head: { rotation: { x: -0.09, z: 0.02 } },
      leftShoulder: { rotation: { x: -0.08, z: -0.16 } },
      rightShoulder: { rotation: { x: -0.08, z: 0.16 } },
      leftUpperArm: { rotation: { x: -0.24, y: -0.08, z: -0.24 } },
      rightUpperArm: { rotation: { x: -0.24, y: 0.08, z: 0.24 } },
    },
    scales: { speed: 1.25, amplitude: 1.1, breath: 1.35, tremble: 0.004 },
    oneShot: 'surpriseBack',
  },
  urgent: {
    pose: {
      spine: { rotation: { x: -0.045, y: 0.02 } },
      chest: { rotation: { x: -0.035 } },
      head: { rotation: { x: 0.02, y: 0.055, z: -0.02 } },
      leftShoulder: { rotation: { x: -0.06, z: 0.04 } },
      rightShoulder: { rotation: { x: -0.12, z: 0.18 } },
      rightUpperArm: { rotation: { x: -0.24, y: 0.08, z: 0.28 } },
      rightLowerArm: { rotation: { x: -0.18, z: 0.1 } },
    },
    scales: { speed: 2.45, amplitude: 0.9, breath: 1.55, tremble: 0.018 },
    oneShot: 'urgentSignal',
  },
  紧急: {
    pose: {
      spine: { rotation: { x: -0.045, y: 0.02 } },
      chest: { rotation: { x: -0.035 } },
      head: { rotation: { x: 0.02, y: 0.055, z: -0.02 } },
      leftShoulder: { rotation: { x: -0.06, z: 0.04 } },
      rightShoulder: { rotation: { x: -0.12, z: 0.18 } },
      rightUpperArm: { rotation: { x: -0.24, y: 0.08, z: 0.28 } },
      rightLowerArm: { rotation: { x: -0.18, z: 0.1 } },
    },
    scales: { speed: 2.45, amplitude: 0.9, breath: 1.55, tremble: 0.018 },
    oneShot: 'urgentSignal',
  },
}

const FALLBACK_MOTION = EMOTION_MOTION_MAP[EMOTION_FALLBACK_LABEL] ?? EMOTION_MOTION_MAP.calm

function emptyPose(): PoseValues {
  return {
    rotation: { x: 0, y: 0, z: 0 },
    position: { x: 0, y: 0, z: 0 },
  }
}

function lerp(current: number, target: number, factor: number): number {
  return current + (target - current) * factor
}

function smoothFactor(deltaMs: number, speed: number): number {
  return 1 - Math.pow(0.9, (deltaMs / 16.67) * speed)
}

function resolveProfile(emotion: EmotionState): EmotionMotionProfile {
  const label = emotion.label?.trim()
  if (label && EMOTION_MOTION_MAP[label]) return EMOTION_MOTION_MAP[label]
  const lowerLabel = label?.toLowerCase()
  if (lowerLabel && EMOTION_MOTION_MAP[lowerLabel]) return EMOTION_MOTION_MAP[lowerLabel]

  const numericFields = [
    { key: 'sad' as const, value: emotion.sadness },
    { key: 'anxious' as const, value: emotion.anxiety },
    { key: 'angry' as const, value: emotion.anger },
  ]
  const strongest = numericFields.reduce((a, b) => (a.value >= b.value ? a : b))
  if (strongest.value > 0.1) return EMOTION_MOTION_MAP[strongest.key]

  return EMOTION_MOTION_MAP.neutral
}

export function useEmotionMotion(options: UseEmotionMotionOptions): UseEmotionMotionReturn {
  const { vrm, emotionState, characterState } = options

  const currentPose = new Map<BoneName, PoseValues>()
  const baseHipsPosition = { x: 0, y: 0, z: 0 }

  let elapsed = 0
  let motionElapsed = 0
  let activeProfile = resolveProfile(emotionState.value)
  let oneShotElapsed = Number.POSITIVE_INFINITY

  function currentFor(boneName: BoneName): PoseValues {
    let pose = currentPose.get(boneName)
    if (!pose) {
      pose = emptyPose()
      currentPose.set(boneName, pose)
    }
    return pose
  }

  function targetFor(profile: EmotionMotionProfile, boneName: BoneName): PoseValues {
    const target = profile.pose[boneName]
    return {
      rotation: {
        x: target?.rotation?.x ?? 0,
        y: target?.rotation?.y ?? 0,
        z: target?.rotation?.z ?? 0,
      },
      position: {
        x: target?.position?.x ?? 0,
        y: target?.position?.y ?? 0,
        z: target?.position?.z ?? 0,
      },
    }
  }

  function updateCurrentPose(profile: EmotionMotionProfile, deltaMs: number): void {
    const factor = smoothFactor(deltaMs, profile.scales.speed)
    for (const boneName of TRACKED_BONES) {
      const current = currentFor(boneName)
      const target = targetFor(profile, boneName)
      current.rotation.x = lerp(current.rotation.x, target.rotation.x, factor)
      current.rotation.y = lerp(current.rotation.y, target.rotation.y, factor)
      current.rotation.z = lerp(current.rotation.z, target.rotation.z, factor)
      current.position.x = lerp(current.position.x, target.position.x, factor)
      current.position.y = lerp(current.position.y, target.position.y, factor)
      current.position.z = lerp(current.position.z, target.position.z, factor)
    }
  }

  function oneShotPose(kind: OneShotKind | undefined): Partial<Record<BoneName, BonePose>> {
    if (!kind || oneShotElapsed > 900) return {}
    const t = Math.min(oneShotElapsed / 900, 1)
    const pulse = Math.sin(Math.PI * t)

    if (kind === 'joyBurst') {
      return {
        hips: { position: { y: pulse * 0.035 }, rotation: { y: Math.sin(Math.PI * 2 * t) * 0.08 } },
        spine: { rotation: { y: Math.sin(Math.PI * 2 * t) * 0.1, z: pulse * 0.04 } },
        leftUpperArm: { rotation: { x: -pulse * 0.18, z: -pulse * 0.26 } },
        rightUpperArm: { rotation: { x: -pulse * 0.18, z: pulse * 0.26 } },
      }
    }

    if (kind === 'surpriseBack') {
      return {
        hips: { position: { z: -pulse * 0.025 } },
        spine: { rotation: { x: -pulse * 0.08 } },
        head: { rotation: { x: -pulse * 0.08 } },
        leftUpperArm: { rotation: { x: -pulse * 0.18, z: -pulse * 0.18 } },
        rightUpperArm: { rotation: { x: -pulse * 0.18, z: pulse * 0.18 } },
      }
    }

    return {
      spine: { rotation: { x: -pulse * 0.06 } },
      head: { rotation: { y: Math.sin(Math.PI * 4 * t) * 0.08 } },
      rightUpperArm: { rotation: { x: -pulse * 0.2, z: pulse * 0.24 } },
      rightLowerArm: { rotation: { x: -pulse * 0.16 } },
    }
  }

  function runtimePose(profile: EmotionMotionProfile, boneName: BoneName): PoseValues {
    const amp = profile.scales.amplitude
    const speed = profile.scales.speed
    const breath = profile.scales.breath
    const tremble = profile.scales.tremble
    const time = motionElapsed * speed
    const pose = emptyPose()

    const slow = Math.sin((2 * Math.PI * time) / 6000)
    const nod = Math.sin((2 * Math.PI * time) / 5200)
    const look = Math.sin((2 * Math.PI * time) / 3600)
    const shake = tremble ? Math.sin((2 * Math.PI * motionElapsed) / 115) * tremble : 0
    const breathWave = Math.sin((2 * Math.PI * motionElapsed) / (4200 / Math.max(breath, 0.2)))

    if (boneName === 'hips') {
      pose.position.y += breathWave * 0.002 * breath
      pose.position.x += slow * 0.006 * amp
      pose.rotation.y += slow * 0.01 * amp
    }
    if (boneName === 'spine') {
      pose.rotation.z += slow * 0.012 * amp
      pose.rotation.y += shake * 0.35
    }
    if (boneName === 'chest' || boneName === 'upperChest') {
      pose.rotation.z += slow * 0.007 * amp
      pose.rotation.y -= shake * 0.2
    }
    if (boneName === 'neck') {
      pose.rotation.x += nod * 0.008 * amp
      pose.rotation.y += look * 0.01 * amp
    }
    if (boneName === 'head') {
      pose.rotation.x += nod * 0.02 * amp
      pose.rotation.y += look * 0.02 * amp + shake
      pose.rotation.z += slow * 0.018 * amp
    }
    if (boneName === 'leftShoulder') {
      pose.rotation.x += slow * 0.006 * amp
      pose.rotation.z -= shake * 0.4
    }
    if (boneName === 'rightShoulder') {
      pose.rotation.x -= slow * 0.006 * amp
      pose.rotation.z += shake * 0.4
    }
    if (boneName === 'leftUpperArm' || boneName === 'leftLowerArm') {
      pose.rotation.x += slow * 0.02 * amp
      pose.rotation.z -= shake * 0.55
    }
    if (boneName === 'rightUpperArm' || boneName === 'rightLowerArm') {
      pose.rotation.x -= slow * 0.02 * amp
      pose.rotation.z += shake * 0.55
    }

    return pose
  }

  function mergePose(...poses: Array<BonePose | undefined>): PoseValues {
    const result = emptyPose()
    for (const pose of poses) {
      if (!pose) continue
      result.rotation.x += pose.rotation?.x ?? 0
      result.rotation.y += pose.rotation?.y ?? 0
      result.rotation.z += pose.rotation?.z ?? 0
      result.position.x += pose.position?.x ?? 0
      result.position.y += pose.position?.y ?? 0
      result.position.z += pose.position?.z ?? 0
    }
    return result
  }

  function applyBone(v: VRM, boneName: BoneName, profile: EmotionMotionProfile, oneShots: Partial<Record<BoneName, BonePose>>): void {
    const node = v.humanoid?.getNormalizedBoneNode(boneName as any)
    if (!node) return

    const base = BASE_POSE[boneName]
    const current = currentFor(boneName)
    const runtime = runtimePose(profile, boneName)
    const oneShot = oneShots[boneName]
    const merged = mergePose(current, runtime, oneShot)

    node.rotation.x = base.rotation.x + merged.rotation.x
    node.rotation.y = base.rotation.y + merged.rotation.y
    node.rotation.z = base.rotation.z + merged.rotation.z

    if (boneName === 'hips') {
      node.position.x = baseHipsPosition.x + merged.position.x
      node.position.y = baseHipsPosition.y + merged.position.y
      node.position.z = baseHipsPosition.z + merged.position.z
    }
  }

  watch(emotionState, (emotion) => {
    const nextProfile = resolveProfile(emotion)
    activeProfile = nextProfile
    elapsed = 0
    if (nextProfile.oneShot) {
      oneShotElapsed = 0
    }
  }, { deep: true, immediate: true })

  function update(deltaMs: number): void {
    const v = vrm.value
    if (!v) return

    const state = characterState.value
    const isActive = state === 'idle' || state === 'speaking'
    if (!isActive) return

    const hips = v.humanoid?.getNormalizedBoneNode('hips')
    if (hips && baseHipsPosition.y === 0) {
      baseHipsPosition.x = hips.position.x
      baseHipsPosition.y = hips.position.y
      baseHipsPosition.z = hips.position.z
    }

    elapsed += deltaMs
    motionElapsed += deltaMs
    if (Number.isFinite(oneShotElapsed)) {
      oneShotElapsed += deltaMs
    }

    const profile = elapsed > EMOTION_STATE_HOLD_MS ? FALLBACK_MOTION : activeProfile
    updateCurrentPose(profile, deltaMs)
    const oneShots = elapsed > EMOTION_STATE_HOLD_MS ? {} : oneShotPose(profile.oneShot)

    for (const boneName of TRACKED_BONES) {
      applyBone(v, boneName, profile, oneShots)
    }
  }

  return { update }
}
