<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useEscapeKey } from '../../composables/useEscapeKey'

const props = defineProps<{
  open: boolean
  title: string
}>()

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
  (e: 'confirm', title: string): void
}>()

const draftTitle = ref('')
const inputRef = ref<HTMLInputElement | null>(null)
const maxTitleLength = 36
const trimmedTitle = computed(() => draftTitle.value.trim())
const canSubmit = computed(() => trimmedTitle.value.length > 0 && trimmedTitle.value.length <= maxTitleLength)
const stateText = computed(() => {
  if (!trimmedTitle.value) return '名字不能为空'
  if (trimmedTitle.value.length > maxTitleLength) return `最多 ${maxTitleLength} 个字`
  return '会同步显示在左侧对话列表'
})

watch(() => props.open, async (open) => {
  if (!open) return
  draftTitle.value = props.title || ''
  await nextTick()
  inputRef.value?.focus()
  inputRef.value?.select()
})

function close() {
  emit('update:open', false)
}

useEscapeKey(close, {
  enabled: () => props.open,
  priority: 90,
})

function submit() {
  if (!canSubmit.value) return
  emit('confirm', trimmedTitle.value)
  close()
}
</script>

<template>
  <Teleport to="body">
    <Transition name="rename-modal">
      <div
        v-if="open"
        class="rename-overlay"
        @click.self="close"
      >
        <form
          class="rename-card"
          role="dialog"
          aria-modal="true"
          aria-labelledby="rename-conversation-title"
          aria-describedby="rename-conversation-desc"
          @submit.prevent="submit"
        >
          <div class="rename-card__ambient" aria-hidden="true"></div>
          <div class="rename-card__content">
            <header class="rename-header">
              <span class="rename-header__icon" aria-hidden="true">
                <span class="i-carbon-edit"></span>
              </span>
              <div class="rename-header__text">
                <p>对话命名</p>
                <h2 id="rename-conversation-title">重命名这段对话</h2>
                <span id="rename-conversation-desc">换一个更好记的名字，方便之后继续找回。</span>
              </div>
              <button
                type="button"
                class="rename-close"
                aria-label="关闭重命名"
                @click="close"
              >
                <span class="i-carbon-close"></span>
              </button>
            </header>

            <label class="rename-field">
              <span class="rename-field__label">新的对话名称</span>
              <span class="rename-field__control">
                <span class="i-carbon-chat-bot rename-field__icon" aria-hidden="true"></span>
                <input
                  ref="inputRef"
                  v-model="draftTitle"
                  :maxlength="maxTitleLength"
                  autocomplete="off"
                  placeholder="例如：周末旅行计划"
                >
              </span>
            </label>

            <div class="rename-meta">
              <span :class="canSubmit ? 'rename-meta__hint' : 'rename-meta__error'">{{ stateText }}</span>
              <span>{{ trimmedTitle.length }}/{{ maxTitleLength }}</span>
            </div>

            <div class="rename-actions">
              <button
                type="button"
                class="rename-button rename-button--ghost"
                @click="close"
              >
                取消
              </button>
              <button
                type="submit"
                class="rename-button rename-button--primary"
                :disabled="!canSubmit"
              >
                保存名称
              </button>
            </div>
          </div>
        </form>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped lang="scss">
.rename-overlay {
  position: fixed;
  inset: 0;
  z-index: 82;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 18px;
  background:
    radial-gradient(circle at 18% 10%, rgba(255, 216, 235, 0.22), transparent 34%),
    radial-gradient(circle at 84% 6%, rgba(222, 234, 255, 0.22), transparent 34%),
    rgba(57, 48, 86, 0.22);
  backdrop-filter: blur(4px);
  font-family: var(--soulmeet-font-family);
}

.rename-card {
  position: relative;
  width: min(92vw, 436px);
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.78);
  border-radius: 28px;
  background:
    radial-gradient(circle at 14% 4%, rgba(255, 246, 253, 0.86), transparent 30%),
    radial-gradient(circle at 88% 0%, rgba(241, 244, 255, 0.86), transparent 34%),
    rgba(249, 247, 255, 0.9);
  color: #443a68;
  box-shadow: 0 28px 76px rgba(93, 80, 140, 0.18), inset 0 1px 0 rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(22px);

  :deep(button),
  :deep(input) {
    font-family: inherit;
  }
}

.rename-card__ambient {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.42), rgba(255, 255, 255, 0.14)),
    radial-gradient(circle at 78% 86%, rgba(255, 225, 241, 0.48), transparent 36%);
  pointer-events: none;
}

.rename-card__content {
  position: relative;
  padding: 24px;
}

.rename-header {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 14px;
  align-items: start;
}

.rename-header__icon {
  display: inline-flex;
  width: 46px;
  height: 46px;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(255, 255, 255, 0.82);
  border-radius: 16px;
  background: linear-gradient(145deg, rgba(250, 239, 255, 0.92), rgba(236, 229, 255, 0.8));
  box-shadow: 0 12px 24px rgba(126, 98, 223, 0.14);
  color: #7d62df;
  font-size: 22px;
}

.rename-header__text {
  min-width: 0;

  p {
    margin: 1px 0 0;
    color: #a59ac7;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.08em;
  }

  h2 {
    margin: 4px 0 0;
    color: #43386c;
    font-size: 22px;
    font-weight: 700;
    line-height: 1.18;
    letter-spacing: 0;
  }

  span {
    display: block;
    margin-top: 8px;
    color: #726a94;
    font-size: 14px;
    line-height: 1.65;
  }
}

.rename-close {
  display: inline-flex;
  width: 40px;
  height: 40px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(255, 255, 255, 0.74);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.66);
  color: #746994;
  box-shadow: 0 8px 18px rgba(110, 94, 160, 0.08);
  font-size: 20px;
  transition: background 0.18s ease, color 0.18s ease, transform 0.18s ease;

  &:hover {
    background: rgba(255, 255, 255, 0.9);
    color: #6e5ec4;
    transform: translateY(-1px);
  }

  &:active {
    transform: scale(0.96);
  }
}

.rename-field {
  display: block;
  margin-top: 24px;
}

.rename-field__label {
  display: block;
  margin-bottom: 10px;
  color: #675f88;
  font-size: 14px;
  font-weight: 700;
}

.rename-field__control {
  display: flex;
  height: 52px;
  align-items: center;
  gap: 10px;
  border: 1px solid rgba(218, 208, 244, 0.92);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.66);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.72), 0 10px 26px rgba(110, 94, 160, 0.08);
  padding: 0 15px;
  transition: border-color 0.18s ease, background 0.18s ease, box-shadow 0.18s ease;

  &:focus-within {
    border-color: rgba(169, 144, 244, 0.92);
    background: rgba(255, 255, 255, 0.86);
    box-shadow: 0 0 0 4px rgba(169, 144, 244, 0.14), inset 0 1px 0 rgba(255, 255, 255, 0.82);
  }

  input {
    min-width: 0;
    flex: 1;
    border: 0;
    background: transparent;
    color: #443a68;
    font-size: 15px;
    font-weight: 600;
    outline: none;

    &::placeholder {
      color: #a99fbd;
      font-weight: 500;
    }
  }
}

.rename-field__icon {
  flex: 0 0 auto;
  color: #9a86df;
  font-size: 20px;
}

.rename-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 10px;
  padding: 0 2px;
  color: #aaa1c7;
  font-size: 12px;
}

.rename-meta__hint {
  color: #8f85ad;
}

.rename-meta__error {
  color: #d85d78;
}

.rename-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 24px;
}

.rename-button {
  display: inline-flex;
  min-width: 112px;
  height: 44px;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  font-size: 14px;
  font-weight: 700;
  transition: transform 0.18s ease, background 0.18s ease, box-shadow 0.18s ease, opacity 0.18s ease;

  &:active {
    transform: scale(0.98);
  }
}

.rename-button--ghost {
  border: 1px solid rgba(217, 205, 247, 0.92);
  background: rgba(255, 255, 255, 0.62);
  color: #6b5ea0;

  &:hover {
    background: rgba(255, 255, 255, 0.86);
  }
}

.rename-button--primary {
  border: 1px solid rgba(255, 255, 255, 0.68);
  background: linear-gradient(90deg, #a48af0, #7d62df);
  color: #fff;
  box-shadow: 0 12px 24px rgba(126, 98, 223, 0.23);

  &:hover:not(:disabled) {
    box-shadow: 0 14px 28px rgba(126, 98, 223, 0.28);
    transform: translateY(-1px);
  }

  &:disabled {
    cursor: not-allowed;
    opacity: 0.46;
    box-shadow: none;
  }
}

.rename-modal-enter-active,
.rename-modal-leave-active {
  transition: opacity 0.22s ease;
}

.rename-modal-enter-active .rename-card,
.rename-modal-leave-active .rename-card {
  transition: transform 0.24s ease, opacity 0.22s ease;
}

.rename-modal-enter-from,
.rename-modal-leave-to {
  opacity: 0;
}

.rename-modal-enter-from .rename-card,
.rename-modal-leave-to .rename-card {
  opacity: 0;
  transform: translateY(10px) scale(0.98);
}

@media (max-width: 520px) {
  .rename-overlay {
    align-items: flex-end;
    padding: 12px;
  }

  .rename-card {
    width: 100%;
    border-radius: 26px;
  }

  .rename-card__content {
    padding: 20px;
  }

  .rename-header {
    grid-template-columns: auto minmax(0, 1fr) auto;
    gap: 12px;
  }

  .rename-header__icon {
    width: 42px;
    height: 42px;
    border-radius: 15px;
  }

  .rename-header__text h2 {
    font-size: 20px;
  }

  .rename-header__text span {
    font-size: 13px;
  }

  .rename-actions {
    gap: 10px;
  }

  .rename-button {
    min-width: 0;
    flex: 1;
  }
}
</style>
