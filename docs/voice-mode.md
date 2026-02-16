# VOLT Voice Mode

## Overview

VOLT includes optional voice services for speech-to-text (STT) and text-to-speech (TTS), enabling voice-based conversations. The backend acts as a proxy to dedicated voice microservices.

## Services

### TTS (Text-to-Speech) -- Kokoro

- **Model**: Kokoro-82M (~550MB VRAM)
- **Speed**: 12x realtime generation
- **Languages**: English, Japanese, Chinese, Spanish, French, Hindi, Italian, Portuguese
- **Voices**: 20+ built-in voices
- **Port**: 8033 (default)

### STT (Speech-to-Text) -- Whisper

- **Model**: Whisper Large V3 Turbo (~3-4GB VRAM)
- **Speed**: 50-100x realtime transcription
- **Languages**: 99 languages
- **Formats**: WAV, MP3, M4A, FLAC, OGG, WebM, MP4
- **Port**: 8034 (default)

## Setup

### Option 1: Docker

Voice services are included in `docker-compose.yml`. Just start everything:

```bash
docker compose up -d
```

Both TTS and STT services start automatically with GPU support and model caching via named volumes.

### Option 2: Manual

Install dependencies and start each service:

```bash
pip install kokoro faster-whisper soundfile numpy

# Terminal 1: TTS
cd services/tts_service && python main.py

# Terminal 2: STT
cd services/stt_service && python main.py
```

### Verify

```bash
curl http://localhost:8033/health   # TTS
curl http://localhost:8034/health   # STT
```

## Architecture: Voice Proxy

The backend proxies all voice requests through `VoiceServiceProxy` (`backend/voice_proxy.py`). Clients never talk directly to TTS/STT services.

```
Browser  --->  Backend (10821)  --->  TTS Service (8033)
         --->                   --->  STT Service (8034)
```

This pattern provides:
- **Single entry point**: Clients only need the backend URL
- **Health checking**: Backend monitors TTS/STT availability
- **Streaming**: Speech generation is streamed back in 8KB chunks
- **Error handling**: Timeouts (30s regular, 60s streaming) with proper HTTP status codes

> [!TIP]
> The voice proxy initializes at backend startup and checks service health automatically. If TTS/STT services are unavailable, voice endpoints return 503 errors gracefully.

## API Endpoints

### Via Backend (Recommended)

```bash
# Transcribe audio to text
curl -X POST http://localhost:10821/transcribe \
  -F "file=@audio.wav"

# Generate speech from text
curl -X POST http://localhost:10821/generate_speech \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world", "voice": "af_heart", "language": "en"}'
```

### Direct Service Access

```bash
# TTS: Generate speech
curl -X POST http://localhost:8033/generate \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world", "voice": "af_heart", "language": "en"}'

# TTS: List available voices
curl http://localhost:8033/voices

# STT: Transcribe audio file
curl -X POST http://localhost:8034/transcribe \
  -F "file=@audio.wav"

# STT: List supported languages
curl http://localhost:8034/languages
```

## Using Voice in Conversations

Enable voice mode when starting a conversation:

```bash
curl -X POST http://localhost:10821/conversation/start \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "profile_collector", "voice_mode": true}'
```

When `voice_mode` is enabled, the framework uses natural speech connectors in responses for more conversational output.

## Configuration

```bash
# .env
TTS_PORT=8033
STT_PORT=8034
TTS_DEFAULT_VOICE=af_heart
TTS_DEFAULT_LANGUAGE=en
STT_MODEL_SIZE=large-v3-turbo
STT_DEVICE=cuda
STT_COMPUTE_TYPE=float16
TTS_SAMPLE_RATE=24000
```

> [!NOTE]
> **Browser compatibility**: The frontend sends audio as WebM/Opus. Ensure your browser supports the MediaRecorder API with WebM format (Chrome, Firefox, Edge). Safari may require additional configuration.

## Performance

| Operation | Speed | Notes |
|-----------|-------|-------|
| TTS generation | 12x realtime | 1s of audio generated in ~83ms |
| STT transcription | 50-100x realtime | 10s of audio transcribed in ~100-200ms |
| TTS VRAM | ~550MB | Kokoro-82M model |
| STT VRAM | ~3-4GB | Whisper Large V3 Turbo |

> [!TIP]
> Models are downloaded automatically on first run. Docker setups cache models in named volumes (`tts-model-cache`, `stt-model-cache`) so they persist across container restarts.
