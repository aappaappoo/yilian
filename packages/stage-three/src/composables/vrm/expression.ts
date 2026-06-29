import { watch, type Ref, type ShallowRef } from 'vue'
import type { VRM } from '@pixiv/three-vrm'
import { EMOTION_FALLBACK_LABEL, EMOTION_STATE_HOLD_MS, type EmotionState } from '@soulmeet/shared'
import type { CharacterState } from '../../types'

/** 表情过渡持续时间 ms */
const TRANSITION_DURATION = 400

/** 情绪 label → VRM 表情目标映射 */
const LABEL_EXPRESSION_MAP: Record<string, Array<{ name: string; value: number }>> = {
  neutral: [{ name: 'neutral', value: 1.0 }],
  中性: [{ name: 'neutral', value: 1.0 }],
  happy: [{ name: 'happy', value: 0.7 }],
  开心: [{ name: 'happy', value: 0.7 }],
  joy: [{ name: 'happy', value: 0.7 }],
  喜悦: [{ name: 'happy', value: 0.8 }],
  sad: [{ name: 'sad', value: 0.6 }],
  伤心: [{ name: 'sad', value: 0.6 }],
  sorrow: [{ name: 'sad', value: 0.6 }],
  哀伤: [{ name: 'sad', value: 0.8 }],
  missing_someone: [{ name: 'sad', value: 0.45 }, { name: 'relaxed', value: 0.25 }],
  想念: [{ name: 'sad', value: 0.45 }, { name: 'relaxed', value: 0.25 }],
  想恋: [{ name: 'sad', value: 0.45 }, { name: 'relaxed', value: 0.25 }],
  lonely: [{ name: 'sad', value: 0.45 }, { name: 'neutral', value: 0.35 }],
  孤独: [{ name: 'sad', value: 0.45 }, { name: 'neutral', value: 0.35 }],
  孤单: [{ name: 'sad', value: 0.45 }, { name: 'neutral', value: 0.35 }],
  anxious: [{ name: 'surprised', value: 0.35 }],
  焦虑: [{ name: 'surprised', value: 0.35 }],
  angry: [{ name: 'angry', value: 0.6 }],
  生气: [{ name: 'angry', value: 0.65 }],
  surprise: [{ name: 'surprised', value: 0.5 }],
  surprised: [{ name: 'surprised', value: 0.5 }],
  惊讶: [{ name: 'surprised', value: 0.65 }],
  urgent: [{ name: 'surprised', value: 0.45 }, { name: 'angry', value: 0.2 }],
  紧急: [{ name: 'surprised', value: 0.45 }, { name: 'angry', value: 0.2 }],
  calm: [{ name: 'relaxed', value: 0.5 }],
  平静: [{ name: 'relaxed', value: 0.5 }],
  relaxed: [{ name: 'relaxed', value: 0.5 }],
  放松: [{ name: 'relaxed', value: 0.55 }, { name: 'happy', value: 0.18 }],
}

/** 数值字段 → 表情回退映射 */
const NUMERIC_FALLBACK_MAP: Record<string, string> = {
  sadness: 'sad',
  anxiety: 'surprised',
  anger: 'angry',
}

/** 表情权重上限 */
const MAX_EXPRESSION_VALUE = 0.8

/** 口型 BlendShape 黑名单（P1.5 口型通道独占） */
const VISEME_BLACKLIST = new Set(['aa', 'ee', 'ih', 'oh', 'ou'])

/** easeInOutCubic 缓动函数 */
function easeInOutCubic(t: number): number {
  return t < 0.5
    ? 4 * t * t * t
    : 1 - Math.pow(-2 * t + 2, 3) / 2
}

/** 安全设置表情值，过滤 viseme 黑名单 + 上限 clamp */
function safeSetValue(vrm: VRM, name: string, value: number) {
  if (VISEME_BLACKLIST.has(name)) {
    console.warn(`[expression] 拒绝写入 viseme BlendShape: ${name}`)
    return
  }
  vrm.expressionManager?.setValue(name, Math.min(value, MAX_EXPRESSION_VALUE))
}

export interface UseExpressionOptions {
  vrm: ShallowRef<VRM | null>
  emotionState: Ref<EmotionState>
  availableExpressions: Ref<Map<string, string>>
  characterState: Ref<CharacterState>
}

export interface UseExpressionReturn {
  update: (deltaMs: number) => void
}

/**
 * 情绪→VRM 表情映射 composable
 *
 * 映射管线：
 * 1. 策略 1：label 在映射表中 → 使用映射结果
 * 2. 策略 2：取 sadness/anxiety/anger 最大值
 * 3. 策略 3：全部数值 ≈ 0 → neutral
 *
 * 每帧 lerp 过渡到目标值
 */
export function useExpression(options: UseExpressionOptions): UseExpressionReturn {
  const { vrm, emotionState, availableExpressions, characterState } = options

  // 过渡状态
  let targets = new Map<string, number>()      // VRM preset → 目标权重
  let current = new Map<string, number>()      // VRM preset → 当前权重
  let startValues = new Map<string, number>()  // VRM preset → 过渡起始权重
  let transitionElapsed = TRANSITION_DURATION  // 初始标记为完成
  let fallbackTimer = 0                        // 无新 emotionState 计时

  function resolveTargets(emotion: EmotionState): Map<string, number> {
    const result = new Map<string, number>()
    const expressions = availableExpressions.value

    // 策略 1：label 在映射表中
    if (emotion.label && LABEL_EXPRESSION_MAP[emotion.label.toLowerCase()]) {
      const mappings = LABEL_EXPRESSION_MAP[emotion.label.toLowerCase()]
      for (const m of mappings) {
        const preset = expressions.get(m.name)
        if (preset) {
          result.set(preset, m.value)
        }
      }
      if (result.size > 0) return result
    }

    // 策略 2：取数值最大维度
    const numericFields: Array<{ key: keyof typeof NUMERIC_FALLBACK_MAP; val: number }> = [
      { key: 'sadness', val: emotion.sadness },
      { key: 'anxiety', val: emotion.anxiety },
      { key: 'anger', val: emotion.anger },
    ]
    const max = numericFields.reduce((a, b) => (a.val >= b.val ? a : b))
    if (max.val > 0.1) {
      const businessName = NUMERIC_FALLBACK_MAP[max.key]
      const preset = expressions.get(businessName)
      if (preset) {
        result.set(preset, Math.min(max.val, MAX_EXPRESSION_VALUE))
        return result
      }
    }

    // 策略 3：neutral
    const neutralPreset = expressions.get('neutral')
    if (neutralPreset) {
      result.set(neutralPreset, 1.0)
    }
    return result
  }

  watch(emotionState, (newEmotion) => {
    if (!vrm.value) return

    const newTargets = resolveTargets(newEmotion)

    // 记录过渡起始值
    startValues = new Map(current)
    targets = newTargets
    transitionElapsed = 0
    fallbackTimer = 0

    // 确保旧表情也有过渡回 0 的目标
    for (const key of current.keys()) {
      if (!targets.has(key)) {
        targets.set(key, 0)
        if (!startValues.has(key)) {
          startValues.set(key, current.get(key) ?? 0)
        }
      }
    }
    // 确保新目标也有起始值
    for (const key of targets.keys()) {
      if (!startValues.has(key)) {
        startValues.set(key, 0)
      }
    }
  }, { deep: true })

  function update(deltaMs: number) {
    const v = vrm.value
    if (!v) return

    const state = characterState.value
    if (state === 'fallback' || state === 'loading' || state === 'error') return

    // 无新 emotionState → 自动过渡到平静
    fallbackTimer += deltaMs
    if (fallbackTimer > EMOTION_STATE_HOLD_MS && transitionElapsed >= TRANSITION_DURATION) {
      const fallbackTargets = resolveTargets({
        sadness: 0,
        anxiety: 0,
        anger: 0,
        label: EMOTION_FALLBACK_LABEL,
        keywords: ['auto:fallback'],
      })
      const alreadyFallback = fallbackTargets.size === targets.size
        && [...fallbackTargets.keys()].every(key => targets.get(key) === fallbackTargets.get(key))

      if (fallbackTargets.size > 0 && !alreadyFallback) {
        startValues = new Map(current)
        targets = new Map(fallbackTargets)
        for (const key of current.keys()) {
          if (!targets.has(key)) {
            targets.set(key, 0)
            if (!startValues.has(key)) startValues.set(key, current.get(key) ?? 0)
          }
        }
        for (const key of targets.keys()) {
          if (!startValues.has(key)) startValues.set(key, 0)
        }
        transitionElapsed = 0
        fallbackTimer = 0
      }
    }

    if (transitionElapsed < TRANSITION_DURATION) {
      transitionElapsed += deltaMs
      const rawT = Math.min(transitionElapsed / TRANSITION_DURATION, 1)
      const easedT = easeInOutCubic(rawT)

      for (const [preset, targetVal] of targets.entries()) {
        const startVal = startValues.get(preset) ?? 0
        const val = startVal + (targetVal - startVal) * easedT
        safeSetValue(v, preset, val)
        current.set(preset, val)
      }

      // 过渡完成后清理权重为 0 的条目
      if (transitionElapsed >= TRANSITION_DURATION) {
        for (const [key, val] of current.entries()) {
          if (val < 0.001) {
            current.delete(key)
          }
        }
      }
    }
  }

  return { update }
}
