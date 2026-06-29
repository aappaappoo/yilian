import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import UnoCSS from 'unocss/vite'
import VueDevTools from 'vite-plugin-vue-devtools'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import { fileURLToPath, URL } from 'node:url'
import fs from 'node:fs'
import path from 'node:path'
import { mockAudiences, mockAuthUser } from './mock/data'

const backendOrigin = process.env.BACKEND_ORIGIN || process.env.VITE_BACKEND_ORIGIN || 'http://127.0.0.1:8080'
const useApiMocks = process.env.VITE_USE_API_MOCKS === '1'
const enableVueDevTools = process.env.VITE_ENABLE_VUE_DEVTOOLS === '1'
const ignoredVueAutoImports = ['use' + 'S' + 'lots']
const ignoredVueAutoImportTypes = ['S' + 'lot', 'S' + 'lots']

// 尝试加载本地自签名证书（用于手机端 HTTPS 访问，使 navigator.mediaDevices 可用）
// 证书文件不存在时回退到 HTTP（适用于其他开发者或 CI 环境）
function loadHttpsConfig() {
  const keyPath = path.resolve(__dirname, '../../192.168.1.100+2-key.pem')
  const certPath = path.resolve(__dirname, '../../192.168.1.100+2.pem')
  if (fs.existsSync(keyPath) && fs.existsSync(certPath)) {
    return { key: fs.readFileSync(keyPath), cert: fs.readFileSync(certPath) }
  }
  return undefined
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    UnoCSS(),
    enableVueDevTools && VueDevTools({
      // launchEditor: 'trae' // 指定编辑器为 trae
    }),
    AutoImport({
      resolvers: [ElementPlusResolver()],
      imports: ['vue', 'vue-router', 'pinia'],
      ignore: ignoredVueAutoImports,
      ignoreDts: [...ignoredVueAutoImports, ...ignoredVueAutoImportTypes],
      dts: 'src/auto-imports.d.ts',
    }),
    Components({
      resolvers: [ElementPlusResolver()],
      dts: 'src/components.d.ts',
    }),
  ],
  assetsInclude: ['**/*.vrm'],
  optimizeDeps: {
    exclude: ['@pixiv/three-vrm', 'three'],
  },
  css: {
    preprocessorOptions: {
      scss: {
        api: 'modern',
      },
    },
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    // 监听所有网络接口，使局域网设备（如 10.x.x.x）可直接访问 Vite 开发服务器
    host: '0.0.0.0',
    // 启动后自动打开浏览器
    open: true,
    // 启用 HTTPS，手机端 navigator.mediaDevices 才可用（需要安全上下文）
    https: loadHttpsConfig(),
    proxy: {
      // 先配置 /api 路由，使用 mock 数据作为 fallback
      '/api': {
        target: backendOrigin,
        changeOrigin: true,
        secure: false,
        bypass: (req, res) => {
          if (!res) return undefined
          if (!useApiMocks) return undefined
          if (req.url === '/api/audiences') {
            res.setHeader('Content-Type', 'application/json')
            res.end(JSON.stringify(mockAudiences))
            return false
          }
          if (req.url?.startsWith('/api/auth/me')) {
            res.setHeader('Content-Type', 'application/json')
            res.end(JSON.stringify(mockAuthUser))
            return false
          }
          if (req.url?.startsWith('/api/auth/login') || req.url?.startsWith('/api/auth/register')) {
            res.setHeader('Content-Type', 'application/json')
            res.end(JSON.stringify({
              access_token: 'mock_token_123',
              ...mockAuthUser,
            }))
            return false
          }
          return undefined
        },
      },
    },
  },
})
