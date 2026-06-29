<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { apiUrl } from '../utils/api'
import { useEscapeKey } from '../composables/useEscapeKey'

const { t } = useI18n()

const props = defineProps<{
  audienceId: string
}>()

const emit = defineEmits<{
  close: []
}>()

// ── 状态 ──
interface VoiceCloneStatus {
  has_cloned_voice: boolean
  is_active: boolean
  cloned_voice_id: string
  source_file: string
  created_at: string
  default_voice: string
}

const status = ref<VoiceCloneStatus | null>(null)
const loadingStatus = ref(false)
const errorMsg = ref('')
const successMsg = ref('')

// ── 上传文件相关 ──
const uploadedFilename = ref('')
const uploading = ref(false)
const dragOver = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

// ── 录音相关 ──
const isRecording = ref(false)
const recordDuration = ref(0)
const recordedBlob = ref<Blob | null>(null)
const recordedAudioUrl = ref('')
let mediaRecorder: MediaRecorder | null = null
let recordTimer: ReturnType<typeof setInterval> | null = null
let mediaStream: MediaStream | null = null

// ── 克隆 / 重置状态 ──
const cloning = ref(false)
const resetting = ref(false)
const cloneProgress = ref(0)
let cloneProgressTimer: ReturnType<typeof setInterval> | null = null

useEscapeKey(() => emit('close'), { priority: 80 })

function _startProgressAnimation() {
  cloneProgress.value = 0
  cloneProgressTimer = setInterval(() => {
    // 指数衰减策略：每次增量为剩余距离的 12%，使进度条先快后慢趋近于 90%
    if (cloneProgress.value < 90) {
      const remaining = 90 - cloneProgress.value
      cloneProgress.value += Math.max(1, Math.floor(remaining * 0.12))
    }
  }, 400)
}

function _stopProgressAnimation(success: boolean) {
  if (cloneProgressTimer !== null) {
    clearInterval(cloneProgressTimer)
    cloneProgressTimer = null
  }
  if (success) {
    cloneProgress.value = 100
    // 2 秒后隐藏进度条
    setTimeout(() => { cloneProgress.value = 0 }, 2000)
  }
  else {
    cloneProgress.value = 0
  }
}

async function loadStatus() {
  loadingStatus.value = true
  errorMsg.value = ''
  try {
    const resp = await fetch(apiUrl(`/api/voice-clone/${props.audienceId}/status`))
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    status.value = await resp.json()
  }
  catch (e: any) {
    errorMsg.value = e.message
  }
  finally {
    loadingStatus.value = false
  }
}

loadStatus()

// ── 文件上传 ──
async function uploadFile(file: File) {
  uploading.value = true
  errorMsg.value = ''
  successMsg.value = ''
  uploadedFilename.value = ''
  try {
    const formData = new FormData()
    formData.append('file', file)
    const resp = await fetch(apiUrl(`/api/voice-clone/${props.audienceId}/upload`), {
      method: 'POST',
      body: formData,
    })
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}))
      throw new Error(data.detail || `HTTP ${resp.status}`)
    }
    const data = await resp.json()
    uploadedFilename.value = data.filename
    successMsg.value = t('voiceClone.uploadSuccess')
  }
  catch (e: any) {
    errorMsg.value = `${t('voiceClone.errorUpload')}: ${e.message}`
  }
  finally {
    uploading.value = false
  }
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) uploadFile(file)
}

function onDrop(event: DragEvent) {
  dragOver.value = false
  const file = event.dataTransfer?.files?.[0]
  if (file) uploadFile(file)
}

// ── 在线录音 ──
async function startRecording() {
  errorMsg.value = ''
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true })
  }
  catch {
    errorMsg.value = t('voiceClone.micPermissionDenied')
    return
  }

  recordedBlob.value = null
  recordedAudioUrl.value = ''
  uploadedFilename.value = ''
  recordDuration.value = 0
  const chunks: BlobPart[] = []

  mediaRecorder = new MediaRecorder(mediaStream)
  mediaRecorder.ondataavailable = e => { if (e.data.size > 0) chunks.push(e.data) }
  mediaRecorder.onstop = () => {
    const blob = new Blob(chunks, { type: 'audio/webm' })
    recordedBlob.value = blob
    recordedAudioUrl.value = URL.createObjectURL(blob)
  }
  mediaRecorder.start()
  isRecording.value = true

  recordTimer = setInterval(() => { recordDuration.value++ }, 1000)
}

function stopRecording() {
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop()
  }
  if (recordTimer !== null) {
    clearInterval(recordTimer)
    recordTimer = null
  }
  if (mediaStream) {
    mediaStream.getTracks().forEach(t => t.stop())
    mediaStream = null
  }
  isRecording.value = false
}

async function uploadRecording() {
  if (!recordedBlob.value) return
  const file = new File([recordedBlob.value], `recording_${crypto.randomUUID()}.webm`, { type: 'audio/webm' })
  await uploadFile(file)
}

// ── 克隆 ──
async function startClone() {
  if (!uploadedFilename.value) {
    errorMsg.value = t('voiceClone.noAudioHint')
    return
  }
  cloning.value = true
  errorMsg.value = ''
  successMsg.value = ''
  _startProgressAnimation()
  try {
    const resp = await fetch(apiUrl(`/api/voice-clone/${props.audienceId}/clone`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename: uploadedFilename.value }),
    })
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}))
      throw new Error(data.detail || `HTTP ${resp.status}`)
    }
    _stopProgressAnimation(true)
    successMsg.value = t('voiceClone.cloneSuccess')
    await loadStatus()
  }
  catch (e: any) {
    _stopProgressAnimation(false)
    errorMsg.value = `${t('voiceClone.errorClone')}: ${e.message}`
  }
  finally {
    cloning.value = false
  }
}

// ── 重置 ──
async function resetVoice() {
  resetting.value = true
  errorMsg.value = ''
  successMsg.value = ''
  try {
    const resp = await fetch(apiUrl(`/api/voice-clone/${props.audienceId}/reset`), { method: 'POST' })
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}))
      throw new Error(data.detail || `HTTP ${resp.status}`)
    }
    successMsg.value = t('voiceClone.resetSuccess')
    await loadStatus()
  }
  catch (e: any) {
    errorMsg.value = `${t('voiceClone.errorReset')}: ${e.message}`
  }
  finally {
    resetting.value = false
  }
}

function formatDuration(s: number): string {
  const m = Math.floor(s / 60).toString().padStart(2, '0')
  const sec = (s % 60).toString().padStart(2, '0')
  return `${m}:${sec}`
}

const uploadRecordingLabel = computed(() => {
  if (uploading.value) return t('voiceClone.uploading')
  if (successMsg.value === t('voiceClone.uploadSuccess')) return '✓'
  return `${t('voiceClone.previewRecord')} →`
})

onUnmounted(() => {
  if (isRecording.value) stopRecording()
  if (recordedAudioUrl.value) URL.revokeObjectURL(recordedAudioUrl.value)
  if (cloneProgressTimer !== null) clearInterval(cloneProgressTimer)
})
</script>

<template>
  <!-- 遮罩层 -->
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/40" @click.self="emit('close')">
    <div class="bg-white rounded-xl shadow-xl w-[90vw] max-w-md p-6 relative max-h-[90vh] overflow-y-auto" @click.stop>
      <!-- 关闭按钮 -->
      <button
        class="absolute top-3 right-3 text-gray-400 hover:text-gray-600 text-xl leading-none"
        @click="emit('close')"
      >
        ✕
      </button>

      <h2 class="text-xl font-bold text-gray-800 mb-4 text-center">
        🎤 {{ t('voiceClone.title') }}
      </h2>

      <!-- 当前声音状态 -->
      <div v-if="!loadingStatus && status" class="mb-4 flex items-center gap-2 text-sm">
        <span class="text-gray-500">{{ t('voiceClone.currentStatus') }}：</span>
        <span
          v-if="status.is_active && status.has_cloned_voice"
          class="px-2 py-0.5 bg-indigo-100 text-indigo-700 rounded-full font-medium"
        >
          {{ t('voiceClone.usingCloned') }}
        </span>
        <span v-else class="px-2 py-0.5 bg-gray-100 text-gray-600 rounded-full">
          {{ t('voiceClone.usingDefault') }}
        </span>
        <span v-if="status.default_voice" class="text-gray-400 text-xs">
          ({{ status.default_voice }})
        </span>
      </div>

      <!-- 提示信息 -->
      <div v-if="errorMsg" class="mb-3 text-sm text-red-500 bg-red-50 rounded-lg px-3 py-2">
        {{ errorMsg }}
      </div>
      <div v-if="successMsg" class="mb-3 text-sm text-green-600 bg-green-50 rounded-lg px-3 py-2">
        {{ successMsg }}
      </div>

      <!-- ── 在线录音 ── -->
      <div class="mb-5">
        <p class="text-sm font-medium text-gray-700 mb-2">
          {{ t('voiceClone.recordSection') }}
        </p>

        <div class="flex items-center gap-3">
          <button
            v-if="!isRecording"
            class="btn-primary px-4 py-1.5 text-xs rounded-full"
            @click="startRecording"
          >
            {{ t('voiceClone.startRecord') }}
          </button>
          <button
            v-else
            class="px-4 py-1.5 text-xs rounded-full bg-red-500 text-white hover:bg-red-600 active:bg-red-700 transition-colors"
            @click="stopRecording"
          >
            {{ t('voiceClone.stopRecord') }} {{ formatDuration(recordDuration) }}
          </button>

          <!-- 波形动画 -->
          <div v-if="isRecording" class="flex items-center gap-0.5 h-5">
            <span
              v-for="i in 5"
              :key="i"
              class="block w-1 bg-indigo-500 rounded-sm animate-pulse"
              :style="{ height: `${8 + (i % 3) * 6}px`, animationDelay: `${i * 0.1}s` }"
            />
          </div>
        </div>

        <!-- 预览 + 上传录音 -->
        <div v-if="recordedAudioUrl" class="mt-3 flex items-center gap-3">
          <audio :src="recordedAudioUrl" controls class="h-8 flex-1" />
          <button
            class="btn-primary px-3 py-1 text-xs rounded-full"
            :disabled="uploading"
            @click="uploadRecording"
          >
            {{ uploadRecordingLabel }}
          </button>
        </div>
      </div>

      <!-- ── 文件上传 ── -->
      <div class="mb-5">
        <p class="text-sm font-medium text-gray-700 mb-2">
          {{ t('voiceClone.uploadSection') }}
        </p>
        <div
          class="border-2 border-dashed rounded-lg p-4 text-center text-sm text-gray-400 cursor-pointer transition-colors"
          :class="dragOver ? 'border-indigo-500 bg-indigo-50' : 'border-gray-300 hover:border-indigo-400'"
          @dragover.prevent="dragOver = true"
          @dragleave="dragOver = false"
          @drop.prevent="onDrop"
          @click="fileInput?.click()"
        >
          <div v-if="uploading">
            {{ t('voiceClone.uploading') }}
          </div>
          <div v-else-if="uploadedFilename" class="text-green-600">
            ✓ {{ uploadedFilename }}
          </div>
          <div v-else>
            <p>{{ t('voiceClone.uploadHint') }}</p>
            <p class="text-xs mt-1 text-gray-300">
              {{ t('voiceClone.supportedFormats') }}
            </p>
          </div>
        </div>
        <input
          ref="fileInput"
          type="file"
          accept=".wav,.mp3,.m4a,.flac,.ogg,.aac,.wma,.amr,.webm"
          class="hidden"
          @change="onFileChange"
        >
      </div>

      <!-- ── 操作按钮 ── -->
      <div class="flex flex-col gap-2">
        <button
          class="btn-primary w-full rounded-lg py-2 text-sm font-medium transition-colors"
          :disabled="cloning || !uploadedFilename"
          @click="startClone"
        >
          {{ cloning ? t('voiceClone.cloning') : t('voiceClone.cloneBtn') }}
        </button>

        <!-- 克隆进度条 -->
        <div v-if="cloning || cloneProgress > 0" class="mt-1">
          <div class="flex items-center justify-between mb-1">
            <span class="text-xs text-gray-500">{{ t('voiceClone.cloneProgress') }}</span>
            <span class="text-xs font-medium" :class="cloneProgress === 100 ? 'text-green-600' : 'text-indigo-600'">
              {{ cloneProgress }}%
            </span>
          </div>
          <div class="w-full bg-gray-200 rounded-full h-2 overflow-hidden">
            <div
              class="h-2 rounded-full transition-all duration-300"
              :class="cloneProgress === 100 ? 'bg-green-500' : 'bg-indigo-500'"
              :style="{ width: `${cloneProgress}%` }"
            />
          </div>
        </div>

        <button
          v-if="status?.has_cloned_voice"
          class="w-full rounded-lg py-2 text-sm font-medium border border-gray-300 text-gray-600 hover:bg-gray-50 active:bg-gray-100 transition-colors"
          :disabled="resetting"
          @click="resetVoice"
        >
          {{ resetting ? t('voiceClone.resetting') : t('voiceClone.resetBtn') }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.btn-primary {
  background-color: #4f46e5;
  color: white;
  border: 1px solid #4f46e5;
  box-shadow: 0 1px 2px 0 rgb(0 0 0 / 0.05);
}
.btn-primary:hover {
  background-color: #4338ca;
}
.btn-primary:active {
  background-color: #3730a3;
}
.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
