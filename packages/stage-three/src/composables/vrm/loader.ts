import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { VRMLoaderPlugin } from '@pixiv/three-vrm'

let _loader: GLTFLoader | null = null

/**
 * GLTFLoader 单例，注册 VRMLoaderPlugin。
 * 模块级单例（非 ref），因为 GLTFLoader 是无状态工具对象，不需要响应式。
 */
export function useVRMLoader(): GLTFLoader {
  if (_loader) return _loader
  _loader = new GLTFLoader()
  _loader.crossOrigin = 'anonymous'
  _loader.register(parser => new VRMLoaderPlugin(parser))
  return _loader
}
