#!/bin/sh
set -eu

if [ -n "${LIVEKIT_URL:-}" ] && [ -n "${LIVEKIT_API_KEY:-}" ] && [ -n "${LIVEKIT_API_SECRET:-}" ]; then
  python -m core.agents.companion_voice_agent start &
fi

python main.py
