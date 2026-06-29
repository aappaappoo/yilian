import { createApp } from 'vue'
import { createPinia } from 'pinia'
import * as Sentry from '@sentry/vue'
import { setupI18n } from '@soulmeet/i18n'
import 'virtual:uno.css'
import '@unocss/reset/tailwind.css'
import 'element-plus/dist/index.css'
import './styles/theme.css'
import App from './App.vue'
import router from './router'

const app = createApp(App)
const pinia = createPinia()
const i18n = setupI18n('zh-CN')

if (import.meta.env.VITE_SENTRY_DSN) {
  Sentry.init({
    app,
    dsn: import.meta.env.VITE_SENTRY_DSN,
    environment: import.meta.env.VITE_SENTRY_ENVIRONMENT ?? import.meta.env.MODE,
    integrations: [
      Sentry.browserTracingIntegration({ router }),
    ],
    tracesSampleRate: Number(import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE ?? '0.1'),
  })
}

app.use(pinia)
app.use(router)
app.use(i18n)

app.mount('#app')
