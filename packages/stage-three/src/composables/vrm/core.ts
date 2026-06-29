import { ref, shallowRef, type Ref, type ShallowRef } from 'vue'
import type { Scene } from 'three'
import type { VRM } from '@pixiv/three-vrm'
import { useVRMLoader } from './loader'

/** VRM 模型加载超时时间 ms */
const LOAD_TIMEOUT_MS = 60000

/**
 * BlendShape 别名映射表
 * businessName → VRM 模型中可能的 preset 名称列表
 */
const ALIAS_MAP: Record<string, string[]> = {
  happy: ['joy', 'happy'],
  sad: ['sorrow', 'sad'],
  angry: ['angry'],
  surprised: ['surprised'],
  relaxed: ['relaxed'],
  neutral: ['neutral'],
  blink: ['blink'],
}

/**
 * 解析 VRM 模型中实际可用的表情 preset 名称
 */
function resolveExpression(vrm: VRM, businessName: string): string | null {
  const candidates = ALIAS_MAP[businessName] ?? [businessName]
  for (const name of candidates) {
    if (vrm.expressionManager?.getExpression(name)) return name
  }
  return null
}

function getMaterialList(material: unknown): any[] {
  if (!material) return []
  return Array.isArray(material) ? material : [material]
}

function isMToonOutlineMaterial(material: any): boolean {
  return Boolean(material?.isMToonMaterial && material?.isOutline)
}

function disableMToonOutlines(vrm: VRM): void {
  vrm.scene.traverse((object) => {
    const mesh = object as any
    if (!mesh.isMesh && !mesh.isSkinnedMesh) return

    const materials = getMaterialList(mesh.material)
    const outlineMaterials = materials.filter(isMToonOutlineMaterial)

    if (outlineMaterials.length > 0 && outlineMaterials.length === materials.length) {
      mesh.visible = false
      return
    }

    for (const material of materials) {
      if (isMToonOutlineMaterial(material)) {
        material.visible = false
        material.transparent = true
        material.opacity = 0
        material.needsUpdate = true
        continue
      }

      if (!material?.isMToonMaterial) continue
      if ('outlineWidthFactor' in material) {
        material.outlineWidthFactor = 0
      }
      if (material.uniforms?.outlineWidthFactor) {
        material.uniforms.outlineWidthFactor.value = 0
      }
      material.needsUpdate = true
    }
  })
}

export interface UseVRMCoreOptions {
  modelUrl: string
  scene: Scene
  onProgress?: (progress: number) => void
}

export interface UseVRMCoreReturn {
  vrm: ShallowRef<VRM | null>
  loadingProgress: Ref<number>
  availableExpressions: Ref<Map<string, string>>
  load: () => Promise<void>
  dispose: () => void
}

/**
 * VRM 加载 + 场景挂载 composable
 *
 * 加载流程：
 * 1. loadAsync() + 15s 超时
 * 2. 校验 humanoid 骨骼
 * 3. 校验 BlendShape 可用性
 * 4. 添加到 TresJS scene
 */
export function useVRMCore(options: UseVRMCoreOptions): UseVRMCoreReturn {
  const { modelUrl, scene, onProgress } = options

  const vrm = shallowRef<VRM | null>(null)
  const loadingProgress = ref<number>(0)
  const availableExpressions = ref<Map<string, string>>(new Map())

  async function load(): Promise<void> {
    const loader = useVRMLoader()

    const loadPromise = loader.loadAsync(modelUrl, (event) => {
      if (event.lengthComputable) {
        const progress = event.loaded / event.total
        loadingProgress.value = progress
        onProgress?.(progress)
      } else {
        loadingProgress.value = -1
        onProgress?.(-1)
      }
    })

    const timeoutPromise = new Promise<never>((_, reject) => {
      setTimeout(() => reject(new Error('VRM 模型加载超时')), LOAD_TIMEOUT_MS)
    })

    const gltf = await Promise.race([loadPromise, timeoutPromise])
    const vrmInstance = gltf.userData.vrm as VRM | undefined

    if (!vrmInstance) {
      throw new Error('GLTF 文件不包含有效的 VRM 数据')
    }

    // 校验 humanoid 骨骼
    if (!vrmInstance.humanoid) {
      throw new Error('VRM 模型缺少 humanoid 骨骼')
    }

    // 校验 BlendShape 可用性
    const expressionMap = new Map<string, string>()
    for (const businessName of Object.keys(ALIAS_MAP)) {
      const preset = resolveExpression(vrmInstance, businessName)
      if (preset) {
        expressionMap.set(businessName, preset)
      } else {
        console.warn(`[useVRMCore] 表情 "${businessName}" 在模型中不可用，已跳过`)
      }
    }
    availableExpressions.value = expressionMap

    // 添加到场景
    scene.add(vrmInstance.scene)
    disableMToonOutlines(vrmInstance)

    // 设置模型初始位置（世界坐标原点）
    vrmInstance.scene.position.set(0, 0, 0)
    vrmInstance.scene.rotation.set(0.1, Math.PI, 0)

    vrm.value = vrmInstance
    loadingProgress.value = 1
  }

  function dispose() {
    if (!vrm.value) return

    // 从场景移除
    scene.remove(vrm.value.scene)

    // 遍历 VRM scene 释放 GPU 资源
    vrm.value.scene.traverse((object) => {
      if ((object as any).isMesh) {
        const mesh = object as any
        mesh.geometry?.dispose()
        const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
        for (const material of materials) {
          if (!material) continue
          const textureProps = ['map', 'normalMap', 'emissiveMap', 'roughnessMap', 'metalnessMap', 'aoMap']
          for (const prop of textureProps) {
            if (material[prop]) {
              material[prop].dispose()
            }
          }
          material.dispose()
        }
      }
    })

    vrm.value = null
  }

  return {
    vrm,
    loadingProgress,
    availableExpressions,
    load,
    dispose,
  }
}
