import { ref } from 'vue'
import { Room, RoomEvent, Track } from 'livekit-client'
import type { RemoteParticipant, RemoteTrack, RemoteTrackPublication } from 'livekit-client'
import type { ServerMessage, AudienceType } from '@soulmeet/shared'
import { useSessionStore } from '../stores/session'
import { useAuthStore } from '../stores/auth'
import { apiUrl } from '../utils/api'

const VOICE_ENABLED_STORAGE_KEY = 'soulmeet.voiceBroadcast.enabled.v1'

interface ConnectOptions {
  sessionId?: string
  conversationId?: string
}

interface ConnectResult {
  sessionId: string
  conversationId?: string
}

interface DisconnectOptions {
  releaseMicrophone?: boolean
}

interface LiveKitTokenResponse {
  url: string
  token: string
  room_name: string
  session_id: string
  conversation_id?: string
  participant_identity: string
}

function readStoredVoiceEnabled(): boolean {
  if (typeof localStorage === 'undefined') return false
  return localStorage.getItem(VOICE_ENABLED_STORAGE_KEY) === '1'
}

function writeStoredVoiceEnabled(enabled: boolean) {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem(VOICE_ENABLED_STORAGE_KEY, enabled ? '1' : '0')
}

export function useWebRTC() {
  const sessionStore = useSessionStore()
  const authStore = useAuthStore()

  const peerConnection = ref<RTCPeerConnection | null>(null)
  const dataChannel = ref<RTCDataChannel | null>(null)
  const localStream = ref<MediaStream | null>(null)
  const remoteStream = ref<MediaStream | null>(null)
  const remoteAudioEl = ref<HTMLAudioElement | null>(null)
  const isMicMuted = ref(true)
  const voiceEnabled = ref(readStoredVoiceEnabled())
  const vadInterruptEnabled = ref(true)

  const onMessage = ref<((msg: ServerMessage) => void) | null>(null)

  let livekitRoom: Room | null = null
  let connectingLivekitRoom: Room | null = null
  let livekitPublishedTrack: MediaStreamTrack | null = null
  let microphoneRequestSeq = 0
  let microphoneEnablePromise: Promise<void> | null = null

  async function publishMicrophoneTrack(track: MediaStreamTrack) {
    if (!livekitRoom) return
    if (livekitPublishedTrack === track) return
    if (livekitPublishedTrack) {
      livekitRoom.localParticipant.unpublishTrack(livekitPublishedTrack)
      livekitPublishedTrack = null
    }
    const publication = await livekitRoom.localParticipant.publishTrack(track, { source: Track.Source.Microphone })
    livekitPublishedTrack = track
    console.info('[useWebRTC] LiveKit 麦克风音轨已发布', {
      trackId: track.id,
      trackSid: (publication as { trackSid?: string; sid?: string }).trackSid
        ?? (publication as { trackSid?: string; sid?: string }).sid
        ?? '<unknown>',
      enabled: track.enabled,
    })
  }

  function handleRealtimePayload(raw: unknown) {
    try {
      const msg = typeof raw === 'string' ? JSON.parse(raw) as ServerMessage : raw as ServerMessage
      if (msg.type === 'emotion_signals') {
        sessionStore.updateEmotionState({
          sadness: msg.sadness,
          anxiety: msg.anxiety,
          anger: msg.anger,
          label: msg.label,
          keywords: msg.keywords,
        })
      }
      else if (msg.type === 'node_change') {
        sessionStore.updateCurrentNode(msg.node)
      }
      else if (msg.type === 'tools_update') {
        sessionStore.updateAvailableTools(msg.tools)
      }
      else if (typeof msg.type === 'string' && msg.type.startsWith('voice_broadcast_')) {
        return
      }
      onMessage.value?.(msg)
    }
    catch (err) {
      console.warn('[useWebRTC] 实时消息解析失败:', err, '原始数据:', raw)
    }
  }

  async function ensureMicrophoneTrack() {
    const existingTrack = localStream.value?.getAudioTracks()[0]
    if (existingTrack) {
      existingTrack.enabled = true
      await publishMicrophoneTrack(existingTrack)
      return
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error('无法访问麦克风。请确保使用 HTTPS 访问，或在浏览器中允许不安全来源。')
    }
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
      video: false,
    })
    localStream.value = stream
    const track = stream.getAudioTracks()[0]
    if (!track) {
      throw new Error('未获取到可用的麦克风音轨')
    }
    track.enabled = true

    await publishMicrophoneTrack(track)
  }

  function releaseMicrophoneTrack() {
    if (livekitRoom && livekitPublishedTrack) {
      livekitRoom.localParticipant.unpublishTrack(livekitPublishedTrack)
      livekitPublishedTrack = null
    }
    if (!localStream.value) {
      return
    }
    for (const track of localStream.value.getTracks()) {
      track.enabled = false
      track.stop()
    }
    localStream.value = null
  }

  function sendRealtimePayload(payload: Record<string, unknown>): boolean {
    if (livekitRoom) {
      const data = new TextEncoder().encode(JSON.stringify(payload))
      void livekitRoom.localParticipant.publishData(data, { reliable: true })
      return true
    }
    return false
  }

  function sendRealtimeEvent(payload: Record<string, unknown>): boolean {
    return sendRealtimePayload(payload)
  }

  function sendRealtimeSettings() {
    sendRealtimePayload({ type: 'set_voice_mode', enabled: voiceEnabled.value })
    sendRealtimePayload({ type: 'set_vad_interrupt', enabled: vadInterruptEnabled.value })
  }

  async function startLiveKitAudioPlayback(reason: string) {
    const room = livekitRoom || connectingLivekitRoom
    if (!room) {
      return
    }
    try {
      await room.startAudio()
      console.info('[useWebRTC] LiveKit 音频播放已解锁', {
        reason,
        canPlaybackAudio: room.canPlaybackAudio,
      })
    }
    catch (err) {
      console.warn('[useWebRTC] LiveKit 音频播放解锁失败:', err)
    }
  }

  function attachLiveKitAudioTrack(track: RemoteTrack) {
    if (track.kind !== Track.Kind.Audio) {
      return
    }
    const el = track.attach() as HTMLAudioElement
    el.autoplay = true
    el.setAttribute('playsinline', 'true')
    el.muted = !voiceEnabled.value
    el.style.position = 'fixed'
    el.style.width = '1px'
    el.style.height = '1px'
    el.style.opacity = '0'
    el.style.pointerEvents = 'none'
    el.setAttribute('aria-hidden', 'true')
    if (typeof document !== 'undefined' && !el.isConnected) {
      document.body.appendChild(el)
    }
    remoteAudioEl.value = el
    const stream = el.srcObject instanceof MediaStream ? el.srcObject : null
    if (stream) {
      remoteStream.value = stream
    }
    if (voiceEnabled.value) {
      void startLiveKitAudioPlayback('track_subscribed')
      void el.play().catch((err) => {
        console.warn('[useWebRTC] LiveKit 远端音频播放失败:', err)
      })
    }
  }

  async function connectLiveKit(audience: string, options: ConnectOptions = {}): Promise<ConnectResult> {
    const sessionId = options.sessionId || ''
    const conversationId = options.conversationId || ''
    const participantIdentity = authStore.user?.userId
      ? `user-${authStore.user.userId}`
      : `guest-${crypto.randomUUID()}`

    console.info('[useWebRTC] LiveKit token 请求', {
      audience,
      sessionId: sessionId || '<new>',
      participantIdentity,
    })
    const tokenResp = await fetch(apiUrl('/api/livekit/token'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        audience,
        session_id: sessionId || undefined,
        conversation_id: conversationId || undefined,
        participant_identity: participantIdentity,
        token: authStore.token ?? '',
      }),
    })
    if (!tokenResp.ok) {
      const detail = await tokenResp.json().catch(() => null) as { detail?: string } | null
      throw new Error(detail?.detail || `LiveKit token 获取失败: ${tokenResp.status}`)
    }
    const tokenData = await tokenResp.json() as LiveKitTokenResponse
    console.info('[useWebRTC] LiveKit token 已获取', {
      sessionId: tokenData.session_id,
      roomName: tokenData.room_name,
      participantIdentity: tokenData.participant_identity,
      url: tokenData.url,
    })

    const room = new Room({
      adaptiveStream: true,
      dynacast: true,
      webAudioMix: true,
    })
    connectingLivekitRoom = room

    ;(room as any).on(RoomEvent.ConnectionStateChanged, (state: string) => {
      console.info('[useWebRTC] LiveKit 连接状态变化', {
        state,
        sessionId: tokenData.session_id,
        roomName: tokenData.room_name,
      })
    })
    ;(room as any).on(RoomEvent.ParticipantConnected, (participant: RemoteParticipant) => {
      console.info('[useWebRTC] LiveKit 远端参与者已加入', {
        identity: participant.identity,
        sessionId: tokenData.session_id,
        roomName: tokenData.room_name,
      })
    })
    ;(room as any).on(RoomEvent.ParticipantDisconnected, (participant: RemoteParticipant) => {
      console.info('[useWebRTC] LiveKit 远端参与者已离开', {
        identity: participant.identity,
        sessionId: tokenData.session_id,
        roomName: tokenData.room_name,
      })
    })
    ;(room as any).on(RoomEvent.TrackPublished, (
      publication: RemoteTrackPublication,
      participant: RemoteParticipant,
    ) => {
      console.info('[useWebRTC] LiveKit 远端音轨已发布', {
        identity: participant.identity,
        kind: publication.kind,
        source: publication.source,
        trackSid: publication.trackSid,
        sessionId: tokenData.session_id,
        roomName: tokenData.room_name,
      })
    })
    ;(room as any).on(RoomEvent.TrackSubscribed, (
      track: RemoteTrack,
      publication: RemoteTrackPublication,
      participant: RemoteParticipant,
    ) => {
      console.info('[useWebRTC] LiveKit 音频轨道已订阅', {
        kind: track.kind,
        identity: participant.identity,
        source: publication.source,
        trackSid: publication.trackSid,
        sessionId: tokenData.session_id,
        roomName: tokenData.room_name,
      })
      attachLiveKitAudioTrack(track)
    })
    ;(room as any).on(RoomEvent.LocalTrackPublished, (publication: { kind?: string; source?: string; trackSid?: string }) => {
      console.info('[useWebRTC] LiveKit 本地音轨发布完成', {
        kind: publication.kind,
        source: publication.source,
        trackSid: publication.trackSid,
        sessionId: tokenData.session_id,
        roomName: tokenData.room_name,
      })
    })
    ;(room as any).on(RoomEvent.AudioPlaybackStatusChanged, (playing: boolean) => {
      console.info('[useWebRTC] LiveKit 音频播放状态变化', {
        playing,
        canPlaybackAudio: room.canPlaybackAudio,
        sessionId: tokenData.session_id,
        roomName: tokenData.room_name,
      })
    })
    ;(room as any).on(RoomEvent.MediaDevicesError, (err: unknown) => {
      console.warn('[useWebRTC] LiveKit 媒体设备错误:', err)
    })
    ;(room as any).on(RoomEvent.DataReceived, (payload: Uint8Array) => {
      console.debug('[useWebRTC] LiveKit 数据消息已收到', {
        bytes: payload.byteLength,
        sessionId: tokenData.session_id,
      })
      handleRealtimePayload(new TextDecoder().decode(payload))
    })
    ;(room as any).on(RoomEvent.Disconnected, (reason: unknown) => {
      console.info('[useWebRTC] LiveKit 房间已断开', {
        sessionId: tokenData.session_id,
        roomName: tokenData.room_name,
        reason,
      })
      if (livekitRoom === room) {
        sessionStore.setStatus('disconnected')
      }
    })

    console.info('[useWebRTC] LiveKit 开始连接房间', {
      sessionId: tokenData.session_id,
      roomName: tokenData.room_name,
    })
    await room.connect(tokenData.url, tokenData.token)
    if (connectingLivekitRoom !== room) {
      room.disconnect()
      throw new Error('LiveKit 连接已取消')
    }
    connectingLivekitRoom = null
    livekitRoom = room
    if (voiceEnabled.value) {
      void startLiveKitAudioPlayback('room_connected')
    }
    console.info('[useWebRTC] LiveKit 房间连接成功', {
      sessionId: tokenData.session_id,
      roomName: tokenData.room_name,
    })
    sessionStore.setSessionInfo({
      sessionId: tokenData.session_id,
      audience: audience as AudienceType,
      currentNode: '',
      connectedAt: new Date().toISOString(),
    })
    sessionStore.setStatus('connected')
    const existingTrack = localStream.value?.getAudioTracks()[0]
    if (existingTrack && !isMicMuted.value) {
      await publishMicrophoneTrack(existingTrack)
    }
    sendRealtimeSettings()
    return {
      sessionId: tokenData.session_id,
      conversationId: tokenData.conversation_id,
    }
  }

  async function connect(audience: string, options: ConnectOptions = {}): Promise<ConnectResult | undefined> {
    disconnect(false, { releaseMicrophone: false })
    sessionStore.setStatus('connecting')
    try {
      return await connectLiveKit(audience, options)
    }
    catch (err) {
      const msg = err instanceof Error ? err.message : '连接失败'
      console.error('[useWebRTC] 连接错误:', err)
      disconnect(false)
      sessionStore.setError(msg)
      return undefined
    }
  }

  function sendMessage(text: string): boolean {
    const sent = sendRealtimePayload({ type: 'text_input', text })
    if (!sent) {
      console.warn('[useWebRTC] sendMessage: 实时通道未就绪，消息未发送。')
    }
    return sent
  }

  function interruptResponse(): boolean {
    return sendRealtimePayload({ type: 'interrupt_response' })
  }

  function toggleVoice() {
    const newState = !voiceEnabled.value
    voiceEnabled.value = newState
    writeStoredVoiceEnabled(newState)
    if (newState) {
      void startLiveKitAudioPlayback('voice_enabled')
    }
    if (remoteAudioEl.value) {
      remoteAudioEl.value.muted = !newState
      if (newState) {
        void remoteAudioEl.value.play().catch((err) => {
          console.warn('[useWebRTC] LiveKit 远端音频播放失败:', err)
        })
      }
    }
    sendRealtimePayload({ type: 'set_voice_mode', enabled: newState })
  }

  function toggleVadInterrupt() {
    const newState = !vadInterruptEnabled.value
    vadInterruptEnabled.value = newState
    sendRealtimePayload({ type: 'set_vad_interrupt', enabled: newState })
  }

  function setMicMuted(muted: boolean) {
    if (muted) {
      ++microphoneRequestSeq
      microphoneEnablePromise = null
      releaseMicrophoneTrack()
      isMicMuted.value = true
      return
    }
    if (microphoneEnablePromise) {
      return
    }
    const requestSeq = ++microphoneRequestSeq
    microphoneEnablePromise = ensureMicrophoneTrack()
      .then(() => {
        if (requestSeq !== microphoneRequestSeq) {
          releaseMicrophoneTrack()
          isMicMuted.value = true
          return
        }
        for (const track of localStream.value?.getAudioTracks() ?? []) {
          track.enabled = true
        }
        isMicMuted.value = false
        console.info('[useWebRTC] 麦克风已开启', {
          tracks: localStream.value?.getAudioTracks().length ?? 0,
        })
      })
      .catch((err) => {
        if (requestSeq !== microphoneRequestSeq) {
          return
        }
        const msg = err instanceof Error ? err.message : '无法开启麦克风'
        sessionStore.setError(msg)
        isMicMuted.value = true
      })
      .finally(() => {
        if (requestSeq === microphoneRequestSeq) {
          microphoneEnablePromise = null
        }
      })
  }

  function forceReleaseMicrophone() {
    ++microphoneRequestSeq
    microphoneEnablePromise = null
    releaseMicrophoneTrack()
    isMicMuted.value = true
  }

  function toggleMic() {
    setMicMuted(!isMicMuted.value)
  }

  function disconnect(updateStatus = true, options: DisconnectOptions = {}) {
    const shouldReleaseMicrophone = options.releaseMicrophone ?? true
    remoteStream.value = null
    if (remoteAudioEl.value) {
      remoteAudioEl.value.srcObject = null
      remoteAudioEl.value.remove()
      remoteAudioEl.value = null
    }
    if (livekitRoom && livekitPublishedTrack) {
      livekitRoom.localParticipant.unpublishTrack(livekitPublishedTrack)
      livekitPublishedTrack = null
    }
    if (shouldReleaseMicrophone) {
      forceReleaseMicrophone()
    }
    dataChannel.value = null
    peerConnection.value = null
    if (connectingLivekitRoom) {
      connectingLivekitRoom.disconnect()
      connectingLivekitRoom = null
    }
    if (livekitRoom) {
      livekitRoom.disconnect()
      livekitRoom = null
    }
    livekitPublishedTrack = null
    if (shouldReleaseMicrophone) {
      isMicMuted.value = true
    }
    if (updateStatus) {
      sessionStore.setStatus('disconnected')
    }
  }

  return {
    peerConnection,
    dataChannel,
    localStream,
    remoteStream,
    isMicMuted,
    voiceEnabled,
    vadInterruptEnabled,
    onMessage,
    connect,
    disconnect,
    sendMessage,
    sendRealtimeEvent,
    interruptResponse,
    toggleMic,
    setMicMuted,
    forceReleaseMicrophone,
    toggleVoice,
    toggleVadInterrupt,
  }
}
