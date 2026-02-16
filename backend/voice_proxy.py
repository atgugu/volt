"""
Voice Service Proxy Module

Provides proxy endpoints for TTS and STT services to enable voice mode
in the conversational interface.
"""

import logging
import httpx
from typing import Optional, Dict, Any
from fastapi import HTTPException, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
import asyncio
import json

logger = logging.getLogger(__name__)

# Service configuration
from backend.config import TTS_SERVICE_URL, STT_SERVICE_URL

# Timeout configuration
SERVICE_TIMEOUT = 30.0  # seconds
STREAM_TIMEOUT = 60.0  # seconds for streaming responses


class VoiceServiceProxy:
    """Proxy handler for TTS and STT services."""

    def __init__(self):
        self.tts_client = None
        self.stt_client = None

    async def initialize(self):
        """Initialize HTTP clients for services."""
        self.tts_client = httpx.AsyncClient(
            base_url=TTS_SERVICE_URL,
            timeout=httpx.Timeout(SERVICE_TIMEOUT)
        )
        self.stt_client = httpx.AsyncClient(
            base_url=STT_SERVICE_URL,
            timeout=httpx.Timeout(SERVICE_TIMEOUT)
        )

    async def cleanup(self):
        """Cleanup HTTP clients."""
        if self.tts_client:
            await self.tts_client.aclose()
        if self.stt_client:
            await self.stt_client.aclose()

    async def check_services_health(self) -> Dict[str, bool]:
        """Check if TTS and STT services are healthy."""
        health_status = {"tts": False, "stt": False}

        try:
            # Check TTS service
            tts_response = await self.tts_client.get("/health")
            health_status["tts"] = tts_response.status_code == 200
        except Exception as e:
            logger.error(f"TTS health check failed: {e}")

        try:
            # Check STT service
            stt_response = await self.stt_client.get("/health")
            health_status["stt"] = stt_response.status_code == 200
        except Exception as e:
            logger.error(f"STT health check failed: {e}")

        return health_status

    async def generate_speech(
        self,
        text: str,
        voice: str = "af_heart",
        speed: float = 1.1,
        language: str = "en"
    ):
        """
        Generate speech from text using TTS service.

        Args:
            text: Text to convert to speech
            voice: Voice to use for generation
            speed: Speech speed (0.5 to 2.0)
            language: Language code

        Returns:
            Streaming audio response
        """
        try:
            # Prepare request payload
            payload = {
                "text": text,
                "voice": voice,
                "speed": speed,
                "language": language,
                "format": "wav"
            }

            # Make streaming request to TTS service
            async with self.tts_client.stream(
                "POST",
                "/generate",
                json=payload,
                timeout=httpx.Timeout(STREAM_TIMEOUT)
            ) as response:
                if response.status_code != 200:
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"TTS service error: {response.text}"
                    )

                # Stream the audio chunks
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    yield chunk

        except httpx.TimeoutException:
            logger.error("TTS service timeout")
            raise HTTPException(status_code=504, detail="TTS service timeout")
        except httpx.RequestError as e:
            logger.error(f"TTS service connection error: {e}")
            raise HTTPException(status_code=503, detail="TTS service unavailable")
        except Exception as e:
            logger.error(f"TTS generation error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def transcribe_audio(
        self,
        audio_file: UploadFile,
        language: Optional[str] = None,
        task: str = "transcribe",
        beam_size: int = 5,
        word_timestamps: bool = True
    ) -> Dict[str, Any]:
        """
        Transcribe audio to text using STT service.

        Args:
            audio_file: Audio file to transcribe
            language: Language code (None for auto-detect)
            task: "transcribe" or "translate"
            beam_size: Beam size for decoding
            word_timestamps: Include word-level timestamps

        Returns:
            Transcription result with text and metadata
        """
        try:
            # Read file content
            content = await audio_file.read()

            # Prepare multipart form data
            files = {"file": (audio_file.filename, content, audio_file.content_type)}
            data = {
                "task": task,
                "beam_size": str(beam_size),
                "word_timestamps": str(word_timestamps).lower()
            }

            if language:
                data["language"] = language

            # Make request to STT service
            response = await self.stt_client.post(
                "/transcribe",
                files=files,
                data=data
            )

            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"STT service error: {response.text}"
                )

            return response.json()

        except httpx.TimeoutException:
            logger.error("STT service timeout")
            raise HTTPException(status_code=504, detail="STT service timeout")
        except httpx.RequestError as e:
            logger.error(f"STT service connection error: {e}")
            raise HTTPException(status_code=503, detail="STT service unavailable")
        except Exception as e:
            logger.error(f"STT transcription error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def handle_websocket_transcription(self, websocket: WebSocket):
        """
        Handle WebSocket connection for real-time transcription.

        Args:
            websocket: FastAPI WebSocket connection
        """
        await websocket.accept()
        logger.info("Voice WebSocket connection established")

        # Connect to STT service WebSocket
        stt_ws_url = STT_SERVICE_URL.replace("http://", "ws://").replace("https://", "wss://") + "/ws/transcribe"

        try:
            async with httpx.AsyncClient() as client:
                async with client.websocket_connect(stt_ws_url) as stt_ws:
                    # Create tasks for bidirectional communication
                    async def forward_to_stt():
                        """Forward audio from client to STT service."""
                        try:
                            while True:
                                # Receive audio data from client
                                data = await websocket.receive_bytes()
                                # Forward to STT service
                                await stt_ws.send_bytes(data)
                        except WebSocketDisconnect:
                            logger.info("Client WebSocket disconnected")
                            return
                        except Exception as e:
                            logger.error(f"Error forwarding to STT: {e}")
                            return

                    async def forward_to_client():
                        """Forward transcription results from STT to client."""
                        try:
                            while True:
                                # Receive transcription from STT
                                message = await stt_ws.receive_text()
                                # Forward to client
                                await websocket.send_text(message)
                        except Exception as e:
                            logger.error(f"Error forwarding to client: {e}")
                            return

                    # Run both tasks concurrently
                    await asyncio.gather(
                        forward_to_stt(),
                        forward_to_client()
                    )

        except Exception as e:
            logger.error(f"WebSocket proxy error: {e}")
            await websocket.send_json({
                "status": "error",
                "error": str(e)
            })
        finally:
            await websocket.close()

    async def get_available_voices(self, language: Optional[str] = None) -> Dict[str, Any]:
        """
        Get list of available TTS voices.

        Args:
            language: Filter by language code

        Returns:
            Dictionary with available voices
        """
        try:
            params = {}
            if language:
                params["language"] = language

            response = await self.tts_client.get("/voices", params=params)

            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"TTS service error: {response.text}"
                )

            return response.json()

        except Exception as e:
            logger.error(f"Error fetching voices: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_supported_languages(self) -> Dict[str, Any]:
        """
        Get list of supported STT languages.

        Returns:
            Dictionary with supported languages
        """
        try:
            response = await self.stt_client.get("/languages")

            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"STT service error: {response.text}"
                )

            return response.json()

        except Exception as e:
            logger.error(f"Error fetching languages: {e}")
            raise HTTPException(status_code=500, detail=str(e))


# Create global proxy instance
voice_proxy = VoiceServiceProxy()
