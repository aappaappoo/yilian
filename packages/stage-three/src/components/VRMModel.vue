<script setup lang="ts">
import { ref, shallowRef, toRef, onMounted, onUnmounted, watch } from 'vue'
import type { EmotionState } from '@soulmeet/shared'
import type { CharacterState, ConnectionStatus } from '../types'
import { useVRMCore } from '../composables/vrm/core'
import { useExpression } from '../composables/vrm/expression'
import { useAnimation } from '../composables/vrm/animation'
import { useEmotionMotion } from '../composables/vrm/useEmotionMotion'
import { useCharacterState } from '../composables/useCharacterState'
import AvatarFallback from './AvatarFallback.vue'

const props = defineProps<{
  emotionState: EmotionState
  connectionStatus: ConnectionStatus
  streamingMessage?: any
  modelUrl?: string
  mini?: boolean
  modelScale?: number
}>()

const emit = defineEmits<{
  (e: 'state-change', state: CharacterState): void
}>()

const DEFAULT_MODEL_URL = '/models/default.vrm'

const canvasRef = ref<HTMLCanvasElement | null>(null)
const showFallback = ref(false)
const isWebGLSupported = ref(true)

// 状态机
const connectionStatusRef = toRef(props, 'connectionStatus')
const streamingMessageRef = toRef(props, 'streamingMessage')
const { state: characterState, transitionTo } = useCharacterState({
  connectionStatus: connectionStatusRef,
  streamingMessage: streamingMessageRef,
})

// Three.js 引用
let renderer: any = null
let scene: any = null
let camera: any = null
let controls: any = null          // ← 新增
let animationFrameId: number | null = null
let lastRenderTimeMs = 0
let isComponentMounted = false
let initToken = 0

const CAMERA_FOV = 30
const CAMERA_POSITION = { x: 0, y: 1.24, z: 3.45 }
const CAMERA_TARGET = { x: 0, y: 1.08, z: 0 }
const CAMERA_VIEW_OFFSET_Y_RATIO = -0.15

const MAX_DELTA_SECONDS = 0.05

let isPageVisible = true

// VRM core
let vrmCore: ReturnType<typeof useVRMCore> | null = null
let expressionSystem: ReturnType<typeof useExpression> | null = null
let animationSystem: ReturnType<typeof useAnimation> | null = null
let emotionMotionSystem: ReturnType<typeof useEmotionMotion> | null = null

// 检测 WebGL 支持
function checkWebGLSupport(): boolean {
  try {
    const testCanvas = document.createElement('canvas')
    const gl = testCanvas.getContext('webgl2') || testCanvas.getContext('webgl')
    return !!gl
  } catch {
    return false
  }
}

function isCurrentInit(token: number): boolean {
  return isComponentMounted && token === initToken
}

function getCanvasParent(): HTMLElement | null {
  const canvas = canvasRef.value
  if (!canvas) return null
  return canvas.parentElement
}

function resetFrameTimer() {
  lastRenderTimeMs = typeof performance !== 'undefined' ? performance.now() : Date.now()
}

function disposeThreeScene() {
  controls?.dispose()
  controls = null

  renderer?.dispose()
  renderer = null
  scene = null
  camera = null
  lastRenderTimeMs = 0
}


async function initThreeScene() {
  const token = ++initToken
  if (!canvasRef.value) return

  try {
    const THREE = await import('three')
    // 动态导入 OrbitControls
    const { OrbitControls } = await import('three/addons/controls/OrbitControls.js')  // ← 新增

    if (!isCurrentInit(token) || !canvasRef.value) return
    const canvas = canvasRef.value
    const parent = getCanvasParent()
    if (!parent) return

    // 创建渲染器
    renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: true,
      premultipliedAlpha: false,
    })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.outputColorSpace = THREE.SRGBColorSpace
    renderer.setClearColor(0x000000, 0)

    const rect = parent.getBoundingClientRect()
    const width = rect?.width ?? 360
    const height = rect?.height ?? 480
    renderer.setSize(width, height)

    // 创建场景
    scene = new THREE.Scene()

    // 创建相机
    camera = new THREE.PerspectiveCamera(CAMERA_FOV, width / height, 0.1, 100)
    camera.position.set(CAMERA_POSITION.x, CAMERA_POSITION.y, CAMERA_POSITION.z)
    camera.lookAt(CAMERA_TARGET.x, CAMERA_TARGET.y, CAMERA_TARGET.z)

    // 将视窗向上偏移，让人物头部靠近画布顶部
    camera.setViewOffset(width, height, 0, height * CAMERA_VIEW_OFFSET_Y_RATIO, width, height)

    // 创建轨道控制器，仅用于固定相机目标；禁止用户拖拽、旋转、缩放和平移。
    controls = new OrbitControls(camera, renderer.domElement)
    controls.target.set(CAMERA_TARGET.x, CAMERA_TARGET.y, CAMERA_TARGET.z)
    controls.enabled = false
    controls.enableRotate = false
    controls.enableZoom = false
    controls.enablePan = false
    controls.enableDamping = false
    controls.dampingFactor = 0
    controls.minDistance = 1.5
    controls.maxDistance = 5
    controls.minPolarAngle = 0.5
    controls.maxPolarAngle = Math.PI / 1.8
    controls.update()
    // ──────────────────────────────────────────────

    // 创建灯光
    const mainLight = new THREE.DirectionalLight(0xffffff, 0.8)
    mainLight.position.set(2, 3, 2)
    scene.add(mainLight)

    const fillLight = new THREE.DirectionalLight(0xf0f4ff, 0.3)
    fillLight.position.set(-2, 1, 2)
    scene.add(fillLight)

    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6)
    scene.add(ambientLight)

    resetFrameTimer()

    canvas.addEventListener('webglcontextlost', handleContextLost)

    await initVRM(token)
    if (!isCurrentInit(token)) return
    startRenderLoop()

    resizeObserver = new ResizeObserver(handleResize)
    const resizeTarget = getCanvasParent()
    if (resizeTarget) {
      resizeObserver.observe(resizeTarget)
    }

  } catch (err) {
    if (!isCurrentInit(token)) return
    console.error('[VRMModel] Three.js 初始化失败:', err)
    transitionTo('fallback')
    showFallback.value = true
  }
}


async function initVRM(token: number) {
  if (!scene || !isCurrentInit(token)) return

  const modelUrl = props.modelUrl ?? DEFAULT_MODEL_URL

  vrmCore = useVRMCore({
    modelUrl,
    scene,
  })

  try {
    await vrmCore.load()
    if (!isCurrentInit(token)) {
      vrmCore?.dispose()
      return
    }

    // 初始化表情系统
    expressionSystem = useExpression({
      vrm: vrmCore.vrm,
      emotionState: toRef(props, 'emotionState'),
      availableExpressions: vrmCore.availableExpressions,
      characterState,
    })

    // 初始化动画系统
    animationSystem = useAnimation({
      vrm: vrmCore.vrm,
      availableExpressions: vrmCore.availableExpressions,
      characterState,
    })

    emotionMotionSystem = useEmotionMotion({
      vrm: vrmCore.vrm,
      emotionState: toRef(props, 'emotionState'),
      characterState,
    })

    // 调整模型缩放（用于页面默认放大/缩小角色）
    const targetScale = props.modelScale ?? 1
    // vrmCore.vrm.value.scene.scale.setScalar(targetScale)
    const vrm = vrmCore.vrm.value
    if (!vrm || !isCurrentInit(token)) return

    vrm.scene.scale.setScalar(targetScale)
    // 设置自然待机姿态（解除 T-Pose）
    animationSystem.applyIdlePose()

    transitionTo('idle')
  } catch (err) {
    if (!isCurrentInit(token)) return
    console.error('[VRMModel] VRM 加载失败:', err)
    transitionTo('fallback')
    showFallback.value = true
  }
}

function startRenderLoop() {
  stopRenderLoop()
  scheduleNextRender()
}

function scheduleNextRender() {
  if (!isComponentMounted || !renderer || !scene || !camera || !isPageVisible) return
  if (animationFrameId !== null) return

  animationFrameId = requestAnimationFrame(() => {
    animationFrameId = null
    if (!isComponentMounted || !renderer || !scene || !camera) return

    const now = typeof performance !== 'undefined' ? performance.now() : Date.now()
    const delta = Math.min(Math.max((now - lastRenderTimeMs) / 1000, 0), MAX_DELTA_SECONDS)
    lastRenderTimeMs = now
    const deltaMs = delta * 1000

    if (vrmCore?.vrm.value) {
      vrmCore.vrm.value.update(delta)
    }

    expressionSystem?.update(deltaMs)
    animationSystem?.update(deltaMs)
    emotionMotionSystem?.update(deltaMs)

    renderer.render(scene, camera)
    scheduleNextRender()
  })
}

function stopRenderLoop() {
  if (animationFrameId !== null) {
    cancelAnimationFrame(animationFrameId)
    animationFrameId = null
  }
}

function markAvatarActive() {
  resetFrameTimer()
}

function handleVisibilityChange() {
  isPageVisible = !document.hidden

  if (isPageVisible) {
    markAvatarActive()
    scheduleNextRender()
    return
  }

  stopRenderLoop()
}

function handleWindowFocus() {
  markAvatarActive()
  scheduleNextRender()
}

function handleWindowBlur() {
  resetFrameTimer()
}


let resizeObserver: ResizeObserver | null = null

function handleResize(entries: ResizeObserverEntry[]) {
  if (!renderer || !camera) return
  const entry = entries[0]
  if (!entry) return

  const { width, height } = entry.contentRect
  if (width <= 0 || height <= 0) return
  renderer.setSize(width, height)
  camera.aspect = width / height
  camera.setViewOffset(width, height, 0, height * CAMERA_VIEW_OFFSET_Y_RATIO, width, height)
  camera.updateProjectionMatrix()
}

function handleContextLost(event: Event) {
  event.preventDefault()
  console.error('[VRMModel] WebGL context lost')
  transitionTo('error')
  showFallback.value = true
}

// 状态变化通知
watch(characterState, (newState) => {
  emit('state-change', newState)
  if (newState === 'fallback') {
    showFallback.value = true
  }
})

onMounted(() => {
  isComponentMounted = true
  isPageVisible = !document.hidden
  document.addEventListener('visibilitychange', handleVisibilityChange)
  window.addEventListener('focus', handleWindowFocus)
  window.addEventListener('blur', handleWindowBlur)

  if (props.mini) {
    // 手机端直接使用 fallback
    transitionTo('fallback')
    showFallback.value = true
    return
  }

  if (!checkWebGLSupport()) {
    isWebGLSupported.value = false
    transitionTo('fallback')
    showFallback.value = true
    return
  }

  initThreeScene().catch((err) => {
    console.error('[VRMModel] 初始化异常:', err)
    transitionTo('fallback')
    showFallback.value = true
  })
})

onUnmounted(() => {
  isComponentMounted = false
  initToken += 1
  stopRenderLoop()

  resizeObserver?.disconnect()
  resizeObserver = null

  vrmCore?.dispose()

  canvasRef.value?.removeEventListener('webglcontextlost', handleContextLost)
  document.removeEventListener('visibilitychange', handleVisibilityChange)
  window.removeEventListener('focus', handleWindowFocus)
  window.removeEventListener('blur', handleWindowBlur)

  // 释放控制器
  disposeThreeScene()
})
</script>

<template>
  <div class="vrm-model">
    <AvatarFallback v-if="showFallback" :mini="mini" />
    <canvas
      v-show="!showFallback"
      ref="canvasRef"
      class="vrm-model__canvas"
    />
    <div
      v-if="characterState === 'loading' && !showFallback"
      class="vrm-model__loading"
    >
      <span class="vrm-model__loading-text">加载中...</span>
    </div>
  </div>
</template>

<style scoped>
.vrm-model {
  position: relative;
  width: 100%;
  height: 100%;
}

.vrm-model__canvas {
  width: 100%;
  height: 100%;
  display: block;
  pointer-events: none;
  touch-action: none;
  user-select: none;
}

.vrm-model__loading {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(248, 250, 252, 0.35);
}

.vrm-model__loading-text {
  font-size: 0.875rem;
  color: #6366f1;
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
</style>
