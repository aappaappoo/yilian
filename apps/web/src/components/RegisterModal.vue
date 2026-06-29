<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../stores/auth'
import { useEscapeKey } from '../composables/useEscapeKey'

const { t } = useI18n()
const authStore = useAuthStore()

const emit = defineEmits<{
  close: []
  switchToLogin: []
}>()

const username = ref('')
const password = ref('')
const confirmPassword = ref('')
const displayName = ref('')
const errorMsg = ref('')
const submitting = ref(false)

// 注册成功后展示的 API Key
const registeredApiKey = ref<string | null>(null)
const apiKeyCopied = ref(false)

useEscapeKey(() => emit('close'), { priority: 80 })

async function handleRegister() {
  errorMsg.value = ''

  if (!username.value.trim() || !password.value) {
    errorMsg.value = t('auth.fillRequired')
    return
  }
  if (password.value.length < 6) {
    errorMsg.value = t('auth.passwordTooShort')
    return
  }
  if (password.value !== confirmPassword.value) {
    errorMsg.value = t('auth.passwordMismatch')
    return
  }

  submitting.value = true
  try {
    const result = await authStore.register(
      username.value.trim(),
      password.value,
      displayName.value.trim() || undefined,
    )
    registeredApiKey.value = result.apiKey
  }
  catch (e: any) {
    errorMsg.value = e.message || t('auth.registerFailed')
  }
  finally {
    submitting.value = false
  }
}

function copyApiKey() {
  if (!registeredApiKey.value) return
  navigator.clipboard.writeText(registeredApiKey.value).then(() => {
    apiKeyCopied.value = true
    setTimeout(() => { apiKeyCopied.value = false }, 2000)
  }).catch(() => {
    // 回退：选中输入框文本供用户手动复制
    const input = document.querySelector('input[readonly]') as HTMLInputElement | null
    if (input) {
      input.select()
    }
  })
}

function handleDone() {
  emit('switchToLogin')
}
</script>

<template>
  <div class="auth-overlay" @click.self="emit('close')">
    <div class="auth-card" @click.stop>
      <button
        class="auth-close"
        type="button"
        aria-label="关闭注册弹窗"
        @click="emit('close')"
      >
        <span class="i-carbon-close"></span>
      </button>

      <div class="auth-header">
        <span class="auth-kicker">New companion</span>
        <h2>{{ t('auth.registerTitle') }}</h2>
        <p>创建你的陪伴档案，让每一次聊天都更靠近你。</p>
      </div>

      <template v-if="registeredApiKey">
        <div class="auth-message auth-message--success">
          {{ t('auth.registerSuccess') }}
        </div>

        <div class="api-key-block">
          <label>{{ t('auth.apiKeyLabel') }}</label>
          <div class="api-key-row">
            <input
              type="text"
              readonly
              :value="registeredApiKey"
            >
            <button
              class="auth-secondary"
              type="button"
              @click="copyApiKey"
            >
              {{ apiKeyCopied ? t('auth.copied') : t('auth.copy') }}
            </button>
          </div>
          <p>
            {{ t('auth.apiKeyHint') }}
          </p>
        </div>

        <button
          class="auth-primary"
          type="button"
          @click="handleDone"
        >
          {{ t('auth.goLoginBtn') }}
        </button>
      </template>

      <template v-else>
        <div v-if="errorMsg" class="auth-message auth-message--error">
          {{ errorMsg }}
        </div>

        <form class="auth-form" @submit.prevent="handleRegister">
          <div class="auth-field">
            <label>{{ t('auth.username') }}</label>
            <input
              v-model="username"
              type="text"
              autocomplete="username"
              :placeholder="t('auth.usernamePlaceholder')"
            >
          </div>
          <div class="auth-field">
            <label>
              {{ t('auth.displayName') }}
              <span>({{ t('auth.optional') }})</span>
            </label>
            <input
              v-model="displayName"
              type="text"
              autocomplete="name"
              :placeholder="t('auth.displayNamePlaceholder')"
            >
          </div>
          <div class="auth-field">
            <label>{{ t('auth.password') }}</label>
            <input
              v-model="password"
              type="password"
              autocomplete="new-password"
              :placeholder="t('auth.passwordPlaceholder')"
            >
          </div>
          <div class="auth-field">
            <label>{{ t('auth.confirmPassword') }}</label>
            <input
              v-model="confirmPassword"
              type="password"
              autocomplete="new-password"
              :placeholder="t('auth.confirmPasswordPlaceholder')"
            >
          </div>
          <button
            type="submit"
            :disabled="submitting"
            class="auth-primary"
          >
            {{ submitting ? t('auth.registering') : t('auth.registerBtn') }}
          </button>
        </form>

        <p class="auth-switch">
          {{ t('auth.hasAccount') }}
          <button type="button" @click="emit('switchToLogin')">
            {{ t('auth.goLogin') }}
          </button>
        </p>
      </template>
    </div>
  </div>
</template>

<style scoped lang="scss">
.auth-overlay {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background:
    radial-gradient(circle at 24% 18%, rgba(255, 215, 234, 0.42), transparent 32%),
    radial-gradient(circle at 76% 12%, rgba(221, 235, 255, 0.4), transparent 34%),
    rgba(56, 45, 82, 0.34);
  backdrop-filter: blur(14px);
}

.auth-card {
  position: relative;
  width: min(440px, 100%);
  max-height: min(760px, calc(100vh - 48px));
  overflow-y: auto;
  border: 1px solid rgba(255, 255, 255, 0.72);
  border-radius: 32px;
  padding: 34px 30px 28px;
  color: #4c3b7c;
  background:
    radial-gradient(circle at 90% 8%, rgba(255, 216, 234, 0.88), transparent 34%),
    radial-gradient(circle at 4% 100%, rgba(221, 235, 255, 0.7), transparent 38%),
    linear-gradient(145deg, rgba(255, 255, 255, 0.88), rgba(255, 247, 253, 0.66));
  box-shadow: 0 28px 72px rgba(116, 91, 166, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.86);
  backdrop-filter: blur(24px);
}

.auth-close {
  position: absolute;
  top: 16px;
  right: 16px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 1px solid rgba(220, 204, 255, 0.68);
  border-radius: 999px;
  color: #8a79b5;
  background: rgba(255, 255, 255, 0.58);
  cursor: pointer;
  transition: transform 0.2s ease, background 0.2s ease, color 0.2s ease;

  &:hover {
    transform: translateY(-1px);
    color: #6f5ba8;
    background: rgba(255, 255, 255, 0.82);
  }
}

.auth-header {
  margin-bottom: 24px;
  padding-right: 30px;

  .auth-kicker {
    display: inline-flex;
    margin-bottom: 10px;
    border-radius: 999px;
    padding: 5px 11px;
    color: #a074c9;
    background: rgba(255, 255, 255, 0.62);
    font-size: 11px;
    font-weight: 900;
  }

  h2 {
    margin: 0;
    color: #4c3b7c;
    font-size: 28px;
    font-weight: 900;
    line-height: 1.2;
  }

  p {
    margin: 10px 0 0;
    color: #8b82a8;
    font-size: 13px;
    font-weight: 700;
    line-height: 1.8;
  }
}

.auth-message {
  margin-bottom: 14px;
  border-radius: 18px;
  padding: 11px 13px;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.6;
}

.auth-message--error {
  color: #c24d73;
  background: rgba(255, 236, 244, 0.78);
  border: 1px solid rgba(255, 194, 218, 0.72);
}

.auth-message--success {
  color: #6c709b;
  background: rgba(245, 252, 255, 0.78);
  border: 1px solid rgba(202, 226, 255, 0.78);
}

.auth-form {
  display: grid;
  gap: 15px;
}

.auth-field {
  display: grid;
  gap: 8px;

  label {
    color: #6f638c;
    font-size: 13px;
    font-weight: 800;
  }

  span {
    color: #aaa0c0;
    font-weight: 700;
  }

  input {
    width: 100%;
    box-sizing: border-box;
    border: 1px solid rgba(220, 204, 255, 0.78);
    border-radius: 18px;
    padding: 13px 15px;
    color: #4c3b7c;
    background: rgba(255, 255, 255, 0.62);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.82);
    font-size: 14px;
    font-weight: 700;
    outline: none;
    transition: border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;

    &::placeholder {
      color: #b8accf;
      font-weight: 600;
    }

    &:focus {
      border-color: rgba(166, 137, 238, 0.88);
      background: rgba(255, 255, 255, 0.82);
      box-shadow: 0 0 0 4px rgba(218, 198, 255, 0.34), inset 0 1px 0 rgba(255, 255, 255, 0.9);
    }
  }
}

.auth-primary,
.auth-secondary {
  border: 0;
  border-radius: 999px;
  color: #fff;
  background: linear-gradient(135deg, #9c8cf0, #d9a9ff 54%, #ffb7d2);
  box-shadow: 0 16px 32px rgba(156, 140, 240, 0.28);
  font-weight: 900;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease, opacity 0.2s ease;

  &:hover:not(:disabled) {
    transform: translateY(-1px);
    box-shadow: 0 20px 40px rgba(156, 140, 240, 0.34);
  }

  &:disabled {
    cursor: not-allowed;
    opacity: 0.58;
  }
}

.auth-primary {
  width: 100%;
  min-height: 48px;
  font-size: 14px;
}

.auth-secondary {
  flex: 0 0 auto;
  min-height: 40px;
  padding: 0 14px;
  font-size: 12px;
}

.auth-switch {
  margin: 18px 0 0;
  color: #8b82a8;
  text-align: center;
  font-size: 12px;
  font-weight: 700;

  button {
    border: 0;
    padding: 0 0 0 4px;
    color: #9a72d7;
    background: transparent;
    font: inherit;
    font-weight: 900;
    cursor: pointer;

    &:hover {
      color: #7f5ac5;
    }
  }
}

.api-key-block {
  display: grid;
  gap: 8px;
  margin-bottom: 18px;

  label {
    color: #6f638c;
    font-size: 13px;
    font-weight: 800;
  }

  p {
    margin: 0;
    color: #8b82a8;
    font-size: 12px;
    font-weight: 700;
    line-height: 1.7;
  }

  input {
    min-width: 0;
    flex: 1;
    border: 1px solid rgba(220, 204, 255, 0.78);
    border-radius: 16px;
    padding: 12px 13px;
    color: #5c4a86;
    background: rgba(255, 255, 255, 0.66);
    font-family: var(--soulmeet-font-family);
    font-size: 12px;
    outline: none;
  }
}

.api-key-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

@media (max-width: 520px) {
  .auth-overlay {
    align-items: flex-end;
    padding: 14px;
  }

  .auth-card {
    width: 100%;
    max-height: calc(100vh - 28px);
    border-radius: 28px;
    padding: 30px 20px 24px;
  }

  .api-key-row {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
