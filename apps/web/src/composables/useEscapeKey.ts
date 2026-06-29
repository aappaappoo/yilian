import { onMounted, onUnmounted } from 'vue'

interface EscapeKeyOptions {
  enabled?: () => boolean
  priority?: number
}

interface EscapeKeyBinding {
  id: number
  priority: number
  enabled?: () => boolean
  handler: (event: KeyboardEvent) => void
}

let nextBindingId = 0
let listening = false
const bindings: EscapeKeyBinding[] = []

function isBindingEnabled(binding: EscapeKeyBinding): boolean {
  return binding.enabled ? binding.enabled() : true
}

function handleDocumentKeydown(event: KeyboardEvent) {
  if (event.key !== 'Escape' || event.isComposing) return

  const activeBinding = bindings
    .filter(isBindingEnabled)
    .sort((left, right) => right.priority - left.priority || right.id - left.id)[0]

  if (!activeBinding) return

  event.preventDefault()
  activeBinding.handler(event)
}

function addBinding(binding: EscapeKeyBinding) {
  bindings.push(binding)
  if (!listening && typeof window !== 'undefined') {
    window.addEventListener('keydown', handleDocumentKeydown)
    listening = true
  }
}

function removeBinding(bindingId: number) {
  const index = bindings.findIndex(binding => binding.id === bindingId)
  if (index >= 0) {
    bindings.splice(index, 1)
  }

  if (listening && bindings.length === 0 && typeof window !== 'undefined') {
    window.removeEventListener('keydown', handleDocumentKeydown)
    listening = false
  }
}

export function useEscapeKey(handler: (event: KeyboardEvent) => void, options: EscapeKeyOptions = {}) {
  const binding: EscapeKeyBinding = {
    id: nextBindingId++,
    priority: options.priority ?? 0,
    enabled: options.enabled,
    handler,
  }

  onMounted(() => addBinding(binding))
  onUnmounted(() => removeBinding(binding.id))
}
