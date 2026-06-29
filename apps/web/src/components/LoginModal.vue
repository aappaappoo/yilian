<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../stores/auth'
import { useEscapeKey } from '../composables/useEscapeKey'

const { t } = useI18n()
const authStore = useAuthStore()

const emit = defineEmits<{
  close: []
  switchToRegister: []
}>()

const username = ref('')
const password = ref('')
const apiKey = ref('')
const errorMsg = ref('')
const submitting = ref(false)
const loginMode = ref<'password' | 'apiKey'>('password')

useEscapeKey(() => emit('close'), { priority: 80 })

async function handleLogin() {
  errorMsg.value = ''
  if (loginMode.value === 'password' && (!username.value.trim() || !password.value)) {
    errorMsg.value = t('auth.fillRequired')
    return
  }
  if (loginMode.value === 'apiKey' && !apiKey.value.trim()) {
    errorMsg.value = t('auth.fillApiKey')
    return
  }
  submitting.value = true
  try {
    if (loginMode.value === 'apiKey') {
      await authStore.loginWithApiKey(apiKey.value.trim())
    }
    else {
      await authStore.login(username.value.trim(), password.value)
    }
    emit('close')
  }
  catch (e: any) {
    errorMsg.value = e.message || t('auth.loginFailed')
  }
  finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="auth-overlay" @click.self="emit('close')">
    <div class="auth-card" @click.stop>
      <button
        class="auth-close"
        type="button"
        aria-label="关闭登录弹窗"
        @click="emit('close')"
      >
        <span class="i-carbon-close"></span>
      </button>

      <div class="auth-header">
        <span class="auth-header__mark">
          <span class="i-carbon-user-avatar-filled"></span>
        </span>
        <div class="min-w-0">
          <h2>{{ t('auth.loginTitle') }}</h2>
          <p>回到你的陪伴大厅，让艾妮继续记得今天的你。</p>
        </div>
      </div>

      <div v-if="errorMsg" class="auth-message auth-message--error">
        {{ errorMsg }}
      </div>

      <div class="auth-mode-tabs" role="tablist" aria-label="登录方式">
        <button
          type="button"
          :class="{ 'auth-mode-tabs__button--active': loginMode === 'password' }"
          class="auth-mode-tabs__button"
          @click="loginMode = 'password'"
        >
          {{ t('auth.passwordLogin') }}
        </button>
        <button
          type="button"
          :class="{ 'auth-mode-tabs__button--active': loginMode === 'apiKey' }"
          class="auth-mode-tabs__button"
          @click="loginMode = 'apiKey'"
        >
          {{ t('auth.apiKeyLogin') }}
        </button>
      </div>

      <form class="auth-form" @submit.prevent="handleLogin">
        <template v-if="loginMode === 'password'">
          <div class="auth-field">
            <label>
              <span class="i-carbon-user-avatar"></span>
              {{ t('auth.username') }}
            </label>
            <input
              v-model="username"
              type="text"
              autocomplete="username"
              :placeholder="t('auth.usernamePlaceholder')"
            >
          </div>
          <div class="auth-field">
            <label>
              <span class="i-carbon-password"></span>
              {{ t('auth.password') }}
            </label>
            <input
              v-model="password"
              type="password"
              autocomplete="current-password"
              :placeholder="t('auth.passwordPlaceholder')"
            >
          </div>
        </template>

        <div v-else class="auth-field">
          <label>
            <span class="i-carbon-api"></span>
            {{ t('auth.apiKeyLoginLabel') }}
          </label>
          <input
            v-model="apiKey"
            type="password"
            autocomplete="off"
            spellcheck="false"
            :placeholder="t('auth.apiKeyLoginPlaceholder')"
          >
          <p class="auth-field__hint">{{ t('auth.apiKeyLoginHint') }}</p>
        </div>

        <button
          type="submit"
          :disabled="submitting"
          class="auth-primary"
        >
          {{ submitting ? t('auth.loggingIn') : t('auth.loginBtn') }}
        </button>
      </form>

      <p class="auth-switch">
        {{ t('auth.noAccount') }}
        <button type="button" @click="emit('switchToRegister')">
          {{ t('auth.goRegister') }}
        </button>
      </p>
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
    linear-gradient(rgba(255, 255, 255, 0.12) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.1) 1px, transparent 1px),
    radial-gradient(circle at 24% 18%, rgba(255, 215, 234, 0.42), transparent 34%),
    radial-gradient(circle at 76% 12%, rgba(221, 235, 255, 0.38), transparent 36%),
    rgba(58, 47, 84, 0.34);
  background-size: 34px 34px, 34px 34px, auto, auto, auto;
  backdrop-filter: blur(16px);
}

.auth-card {
  position: relative;
  width: min(400px, 100%);
  max-height: min(720px, calc(100vh - 48px));
  overflow-y: auto;
  border: 1px solid rgba(255, 255, 255, 0.72);
  border-radius: 28px;
  padding: 1.35rem;
  color: #514b78;
  background:
    radial-gradient(circle at 10% 0%, rgba(255, 220, 238, 0.8), transparent 34%),
    radial-gradient(circle at 94% 10%, rgba(218, 229, 255, 0.74), transparent 36%),
    linear-gradient(145deg, rgba(255, 255, 255, 0.88), rgba(255, 247, 253, 0.72));
  box-shadow: 0 28px 74px rgba(105, 86, 150, 0.24), inset 0 1px 0 rgba(255, 255, 255, 0.84);
  backdrop-filter: blur(24px);
  font-family: var(--soulmeet-font-family);
  scrollbar-width: thin;
}

.auth-close {
  position: absolute;
  top: 0.9rem;
  right: 0.9rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.35rem;
  height: 2.35rem;
  border: 1px solid rgba(255, 255, 255, 0.72);
  border-radius: 999px;
  color: #7b719f;
  background: rgba(255, 255, 255, 0.58);
  box-shadow: 0 8px 18px rgba(105, 86, 150, 0.12);
  cursor: pointer;
  transition: transform 0.2s ease, background 0.2s ease, color 0.2s ease;

  &:hover,
  &:focus-visible {
    transform: scale(1.03);
    color: #6f5ba8;
    background: rgba(255, 255, 255, 0.82);
    outline: none;
  }
}

.auth-header {
  display: flex;
  align-items: center;
  gap: 0.85rem;
  margin-bottom: 1.2rem;
  padding-right: 2.8rem;

  .auth-header__mark {
    display: inline-flex;
    width: 3.25rem;
    height: 3.25rem;
    flex: 0 0 auto;
    align-items: center;
    justify-content: center;
    border: 1px solid rgba(255, 255, 255, 0.78);
    border-radius: 999px;
    background:
      linear-gradient(135deg, rgba(255, 255, 255, 0.92), rgba(255, 244, 252, 0.72)),
      rgba(255, 255, 255, 0.7);
    color: #a986df;
    font-size: 1.45rem;
    box-shadow: 0 12px 24px rgba(115, 92, 165, 0.14);
  }

  h2 {
    margin: 0;
    overflow: hidden;
    color: #4a4a6a;
    font-size: 1.15rem;
    font-weight: 800;
    letter-spacing: 0;
    line-height: 1.35;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  p {
    margin: 0.25rem 0 0;
    color: #9b91b7;
    font-size: 0.78rem;
    font-weight: 600;
    line-height: 1.65;
  }
}

.auth-message {
  margin-bottom: 0.85rem;
  border-radius: 18px;
  padding: 0.68rem 0.78rem;
  font-size: 0.8rem;
  font-weight: 700;
  line-height: 1.6;
}

.auth-message--error {
  color: #c24d73;
  background: rgba(255, 236, 244, 0.78);
  border: 1px solid rgba(255, 194, 218, 0.72);
}

.auth-mode-tabs {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.35rem;
  margin-bottom: 1rem;
  border: 1px solid rgba(255, 255, 255, 0.64);
  border-radius: 999px;
  padding: 0.32rem;
  background: rgba(255, 255, 255, 0.38);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.7);
}

.auth-mode-tabs__button {
  min-height: 2.35rem;
  border: 0;
  border-radius: 999px;
  color: #847aa4;
  background: transparent;
  cursor: pointer;
  font-size: 0.82rem;
  font-weight: 800;
  transition: color 0.2s ease, background 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;

  &:hover,
  &:focus-visible {
    color: #6b55a5;
    outline: none;
  }
}

.auth-mode-tabs__button--active {
  color: #fff;
  background: linear-gradient(135deg, #8b7ae6, #c59dff 58%, #ffbddd);
  box-shadow: 0 10px 22px rgba(139, 122, 230, 0.18), inset 0 1px 0 rgba(255, 255, 255, 0.28);
}

.auth-form {
  display: grid;
  gap: 0.85rem;
}

.auth-field {
  display: grid;
  gap: 0.45rem;

  label {
    display: inline-flex;
    align-items: center;
    gap: 0.42rem;
    color: #6f638c;
    font-size: 0.82rem;
    font-weight: 800;
  }

  label span {
    color: #a986df;
    font-size: 0.96rem;
  }

  input {
    width: 100%;
    box-sizing: border-box;
    min-height: 2.85rem;
    border: 1px solid rgba(255, 255, 255, 0.62);
    border-radius: 18px;
    padding: 0.78rem 0.88rem;
    color: #4f4a72;
    background:
      linear-gradient(135deg, rgba(255, 255, 255, 0.7), rgba(255, 247, 253, 0.52)),
      rgba(255, 255, 255, 0.52);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.84), 0 8px 18px rgba(105, 86, 150, 0.06);
    font-size: 0.9rem;
    font-weight: 700;
    outline: none;
    transition: border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;

    &::placeholder {
      color: #b8b0c9;
      font-weight: 600;
    }

    &:focus {
      border-color: rgba(197, 157, 255, 0.72);
      background: rgba(255, 255, 255, 0.82);
      box-shadow: 0 0 0 4px rgba(218, 198, 255, 0.28), 0 12px 24px rgba(139, 122, 230, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.9);
    }
  }
}

.auth-field__hint {
  margin: 0;
  color: #9a90b5;
  font-size: 0.76rem;
  font-weight: 600;
  line-height: 1.6;
}

.auth-primary {
  width: 100%;
  min-height: 2.8rem;
  border: 1px solid rgba(255, 255, 255, 0.76);
  border-radius: 999px;
  color: #fff;
  background: linear-gradient(135deg, #8b7ae6, #c59dff 58%, #ffbddd);
  box-shadow: 0 14px 30px rgba(139, 122, 230, 0.22);
  font-size: 0.9rem;
  font-weight: 800;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease, opacity 0.2s ease;

  &:hover:not(:disabled),
  &:focus-visible:not(:disabled) {
    transform: translateY(-1px);
    box-shadow: 0 18px 38px rgba(139, 122, 230, 0.3);
    outline: none;
  }

  &:active:not(:disabled) {
    transform: translateY(0);
  }

  &:disabled {
    cursor: not-allowed;
    opacity: 0.58;
  }
}

.auth-switch {
  margin: 1rem 0 0;
  color: #8b82a8;
  text-align: center;
  font-size: 0.78rem;
  font-weight: 600;

  button {
    border: 0;
    padding: 0 0 0 4px;
    color: #9a72d7;
    background: transparent;
    font: inherit;
    font-weight: 900;
    cursor: pointer;
    transition: color 0.18s ease;

    &:hover,
    &:focus-visible {
      color: #7f5ac5;
      outline: none;
    }
  }
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
    padding: 1.25rem;
  }

  .auth-header {
    align-items: flex-start;
    padding-right: 2.45rem;

    .auth-header__mark {
      width: 2.8rem;
      height: 2.8rem;
      font-size: 1.25rem;
    }

    h2 {
      font-size: 1.08rem;
    }
  }
}
</style>
