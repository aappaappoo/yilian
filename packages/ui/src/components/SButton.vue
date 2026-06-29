<script setup lang="ts">
export interface SButtonProps {
  variant?: 'primary' | 'secondary' | 'ghost'
  size?: 'sm' | 'md' | 'lg'
  disabled?: boolean
  loading?: boolean
}

withDefaults(defineProps<SButtonProps>(), {
  variant: 'primary',
  size: 'md',
  disabled: false,
  loading: false,
})

defineEmits<{
  click: [event: MouseEvent]
}>()
</script>

<template>
  <button
    :class="[
      's-button',
      `s-button--${variant}`,
      `s-button--${size}`,
      { 's-button--disabled': disabled || loading },
    ]"
    :disabled="disabled || loading"
    v-bind="$attrs"
    @click="$emit('click', $event)"
  >
    <span v-if="loading" class="s-button__spinner" />
    <slot />
  </button>
</template>

<style scoped>
.s-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  border: none;
  border-radius: 0.5rem;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.2s, background-color 0.2s;
}

.s-button--primary {
  background-color: #6366f1;
  color: #ffffff;
}

.s-button--primary:hover:not(:disabled) {
  background-color: #4f46e5;
}

.s-button--secondary {
  background-color: #e5e7eb;
  color: #374151;
}

.s-button--secondary:hover:not(:disabled) {
  background-color: #d1d5db;
}

.s-button--ghost {
  background-color: transparent;
  color: #6366f1;
}

.s-button--ghost:hover:not(:disabled) {
  background-color: #f0f0ff;
}

.s-button--sm {
  padding: 0.25rem 0.75rem;
  font-size: 0.875rem;
}

.s-button--md {
  padding: 0.5rem 1rem;
  font-size: 1rem;
}

.s-button--lg {
  padding: 0.75rem 1.5rem;
  font-size: 1.125rem;
}

.s-button--disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.s-button__spinner {
  display: inline-block;
  width: 1em;
  height: 1em;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
