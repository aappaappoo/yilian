import { createI18n } from 'vue-i18n'
import zhCN from './locales/zh-CN'
import en from './locales/en'

export { zhCN, en }

export const locales = {
  'zh-CN': zhCN,
  en,
}

export function setupI18n(locale: 'zh-CN' | 'en' = 'zh-CN') {
  return createI18n({
    legacy: false,
    locale,
    fallbackLocale: 'zh-CN',
    messages: locales,
  })
}
