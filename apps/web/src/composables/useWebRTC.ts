import { ref } from 'vue'
import { Room, RoomEvent, Track } from 'livekit-client'
import type { RemoteParticipant, RemoteTrack, RemoteTrackPublication } from 'livekit-client'
import type { ServerMessage, AudienceType } from '@soulmeet/shared'
import { useSessionStore } from '../stores/session'
import { useAuthStore } from '../stores/auth'
import { apiUrl } from '../utils/api'

interface ConnectOptions {
  sessionId?: string
  conversationId?: string
}

interface ConnectResult {
  sessionId: string
  conversationId?: string
}

interface LiveKitTokenResponse {
  url: string
  token: string
  room_name: string
  session_id: string
  conversation_id?: string
  participant_identity: string
}

const voiceTransport = (import.meta.env.VITE_VOICE_TRANSPORT || 'livekit').toLowerCase()

export function useWebRTC() {
  const sessionStore = useSessionStore()
  const authStore = useAuthStore()

  const peerConnection = ref<RTCPeerConnection | null>(null)
  const dataChannel = ref<RTCDataChannel | null>(null)
  const localStream = ref<MediaStream | null>(null)
  const remoteStream = ref<MediaStream | null>(null)
  const remoteAudioEl = ref<HTMLAudioElement | null>(null)
  const isMicMuted = ref(true)
  const voiceEnabled = ref(false)
  const vadInterruptEnabled = ref(true)

  const onMessage = ref<((msg: ServerMessage) => void) | null>(null)

  let pingInterval: ReturnType<typeof setInterval> | null = null
  let microphoneSender: RTCRtpSender | null = null
  let livekitRoom: Room | null = null
  let livekitPublishedTrack: MediaStreamTrack | null = null

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
      onMessage.value?.(msg)
    }
    catch (err) {
      console.warn('[useWebRTC] 实时消息解析失败:', err, '原始数据:', raw)
    }
  }

  function handleDataChannelMessage(event: MessageEvent) {
    handleRealtimePayload(event.data)
  }

  async function ensureMicrophoneTrack() {
    const existingTrack = localStream.value?.getAudioTracks()[0]
    if (existingTrack) {
      existingTrack.enabled = true
      if (microphoneSender && microphoneSender.track !== existingTrack) {
        await microphoneSender.replaceTrack(existingTrack)
      }
      if (livekitRoom && livekitPublishedTrack !== existingTrack) {
        await livekitRoom.localParticipant.publishTrack(existingTrack, { source: Track.Source.Microphone })
        livekitPublishedTrack = existingTrack
      }
      return
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error('无法访问麦克风。请确保使用 HTTPS 访问，或在浏览器中允许不安全来源。')
    }
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
    localStream.value = stream
    const track = stream.getAudioTracks()[0]
    if (!track) {
      throw new Error('未获取到可用的麦克风音轨')
    }
    track.enabled = true

    if (microphoneSender) {
      await microphoneSender.replaceTrack(track)
      return
    }
    if (livekitRoom) {
      await livekitRoom.localParticipant.publishTrack(track, { source: Track.Source.Microphone })
      livekitPublishedTrack = track
      return
    }

    const pc = peerConnection.value
    if (pc && pc.signalingState === 'stable') {
      console.warn('[useWebRTC] 未找到预协商的麦克风 sender，无法在不重新协商的情况下开启麦克风。')
    }
  }

  function releaseMicrophoneTrack() {
    const sender = microphoneSender
    if (sender?.track) {
      void sender.replaceTrack(null).catch((err) => {
        console.warn('[useWebRTC] 麦克风音轨解绑失败:', err)
      })
    }
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

  function startPing() {
    stopPing()
    pingInterval = setInterval(() => {
      if (dataChannel.value?.readyState === 'open') {
        dataChannel.value.send('ping')
      }
    }, 1000)
  }

  function stopPing() {
    if (pingInterval !== null) {
      clearInterval(pingInterval)
      pingInterval = null
    }
  }

  function sendRealtimePayload(payload: Record<string, unknown>): boolean {
    if (voiceTransport === 'livekit' && livekitRoom) {
      const data = new TextEncoder().encode(JSON.stringify(payload))
      void livekitRoom.localParticipant.publishData(data, { reliable: true })
      return true
    }
    if (dataChannel.value?.readyState === 'open') {
      dataChannel.value.send(JSON.stringify(payload))
      return true
    }
    return false
  }

  function sendRealtimeSettings() {
    sendRealtimePayload({ type: 'set_voice_mode', enabled: voiceEnabled.value })
    sendRealtimePayload({ type: 'set_vad_interrupt', enabled: vadInterruptEnabled.value })
  }

  function attachLiveKitAudioTrack(track: RemoteTrack) {
    if (track.kind !== Track.Kind.Audio) {
      return
    }
    const el = track.attach() as HTMLAudioElement
    el.autoplay = true
    el.muted = !voiceEnabled.value
    remoteAudioEl.value = el
    const stream = el.srcObject instanceof MediaStream ? el.srcObject : null
    if (stream) {
      remoteStream.value = stream
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
      throw new Error(`LiveKit token 获取失败: ${tokenResp.status}`)
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
    })
    livekitRoom = room

    ;(room as any).on(RoomEvent.TrackSubscribed, (
      track: RemoteTrack,
      _publication: RemoteTrackPublication,
      _participant: RemoteParticipant,
    ) => {
      console.info('[useWebRTC] LiveKit 音频轨道已订阅', {
        kind: track.kind,
        sessionId: tokenData.session_id,
        roomName: tokenData.room_name,
      })
      attachLiveKitAudioTrack(track)
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
    sendRealtimeSettings()
    return {
      sessionId: tokenData.session_id,
      conversationId: tokenData.conversation_id,
    }
  }

  async function connectSelfWebRTC(audience: string, options: ConnectOptions = {}): Promise<ConnectResult | undefined> {
    if (!window.RTCPeerConnection) {
      sessionStore.setError('浏览器不支持 WebRTC')
      return
    }

    const reconnectSessionId = options.sessionId || ''
    const conversationId = options.conversationId || ''

    let iceServers: RTCIceServer[] = [{ urls: 'stun:stun.l.google.com:19302' }]
    try {
      const iceResp = await fetch(apiUrl('/api/ice-servers'))
      if (iceResp.ok) {
        const servers = await iceResp.json()
        if (Array.isArray(servers) && servers.length > 0) {
          iceServers = servers
        }
      }
    }
    catch (error) {
      console.warn('[useWebRTC] 获取 ICE 服务器配置失败，使用默认 STUN', error)
    }

    const pc = new RTCPeerConnection({ iceServers })
    peerConnection.value = pc

    const audioTransceiver = pc.addTransceiver('audio', { direction: 'sendrecv' })
    microphoneSender = audioTransceiver.sender

    pc.ontrack = (event) => {
      if (event.streams && event.streams[0]) {
        remoteStream.value = event.streams[0]
        if (!remoteAudioEl.value) {
          remoteAudioEl.value = new Audio()
          remoteAudioEl.value.autoplay = true
        }
        remoteAudioEl.value.muted = !voiceEnabled.value
        remoteAudioEl.value.srcObject = event.streams[0]
      }
    }

    const dc = pc.createDataChannel('messages')
    dataChannel.value = dc
    dc.onmessage = handleDataChannelMessage
    dc.onopen = () => {
      if (dataChannel.value !== dc) {
        return
      }
      sessionStore.setStatus('connected')
      sendRealtimeSettings()
      startPing()
    }
    dc.onclose = () => {
      if (dataChannel.value !== dc) {
        return
      }
      stopPing()
      sessionStore.setStatus('disconnected')
    }

    pc.oniceconnectionstatechange = () => {
      if (peerConnection.value !== pc) {
        return
      }
      if (pc.iceConnectionState === 'failed' || pc.iceConnectionState === 'closed') {
        stopPing()
        sessionStore.setStatus('disconnected')
      }
    }

    const offer = await pc.createOffer()
    await pc.setLocalDescription(offer)

    await new Promise<void>((resolve) => {
      if (pc.iceGatheringState === 'complete') {
        resolve()
      }
      else {
        pc.onicegatheringstatechange = () => {
          if (pc.iceGatheringState === 'complete')
            resolve()
        }
        setTimeout(resolve, 3000)
      }
    })

    const response = await fetch(apiUrl('/api/offer'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sdp: pc.localDescription!.sdp,
        type: pc.localDescription!.type,
        audience,
        session_id: reconnectSessionId || undefined,
        conversation_id: conversationId || undefined,
        token: authStore.token ?? '',
      }),
    })

    if (!response.ok) {
      throw new Error(`后端响应错误: ${response.status}`)
    }

    const data = await response.json()
    sessionStore.setSessionInfo({
      sessionId: data.session_id,
      audience: audience as AudienceType,
      currentNode: '',
      connectedAt: new Date().toISOString(),
    })
    await pc.setRemoteDescription({ sdp: data.sdp, type: data.type })
    return {
      sessionId: data.session_id,
      conversationId: data.conversation_id,
    }
  }

  async function connect(audience: string, options: ConnectOptions = {}): Promise<ConnectResult | undefined> {
    disconnect(false)
    sessionStore.setStatus('connecting')
    try {
      if (voiceTransport === 'livekit') {
        return await connectLiveKit(audience, options)
      }
      else {
        return await connectSelfWebRTC(audience, options)
      }
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
    if (remoteAudioEl.value) {
      remoteAudioEl.value.muted = !newState
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
      releaseMicrophoneTrack()
      isMicMuted.value = true
      return
    }
    ensureMicrophoneTrack()
      .then(() => {
        for (const track of localStream.value?.getAudioTracks() ?? []) {
          track.enabled = true
        }
        isMicMuted.value = false
      })
      .catch((err) => {
        const msg = err instanceof Error ? err.message : '无法开启麦克风'
        sessionStore.setError(msg)
        isMicMuted.value = true
      })
  }

  function forceReleaseMicrophone() {
    releaseMicrophoneTrack()
    if (peerConnection.value) {
      const senders = peerConnection.value.getSenders()
      for (const sender of senders) {
        if (sender.track?.kind === 'audio') {
          void sender.replaceTrack(null).catch((err) => {
            console.warn('[useWebRTC] 麦克风音轨解绑失败:', err)
          })
        }
      }
    }
    isMicMuted.value = true
  }

  function toggleMic() {
    setMicMuted(!isMicMuted.value)
  }

  function disconnect(updateStatus = true) {
    stopPing()
    remoteStream.value = null
    if (remoteAudioEl.value) {
      remoteAudioEl.value.srcObject = null
      remoteAudioEl.value.remove()
      remoteAudioEl.value = null
    }
    forceReleaseMicrophone()
    dataChannel.value?.close()
    dataChannel.value = null
    peerConnection.value?.close()
    peerConnection.value = null
    if (livekitRoom) {
      livekitRoom.disconnect()
      livekitRoom = null
    }
    livekitPublishedTrack = null
    microphoneSender = null
    isMicMuted.value = true
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
    interruptResponse,
    toggleMic,
    setMicMuted,
    forceReleaseMicrophone,
    toggleVoice,
    toggleVadInterrupt,
  }
}
