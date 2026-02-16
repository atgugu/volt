"""
Whisper STT Streaming Service

A FastAPI service for speech-to-text transcription using Whisper Large V3 Turbo.
Supports both REST API (file upload) and WebSocket (streaming) modes.
"""

import io
import logging
import time
from typing import Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, WebSocket, WebSocketDisconnect, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import config
from transcriber import WhisperTranscriber
from audio_processor import AudioProcessor

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title=config.SERVICE_NAME,
    description="Speech-to-text transcription using Whisper Large V3 Turbo with streaming support",
    version=config.SERVICE_VERSION
)

# Global transcriber instance (lazy loaded)
transcriber: Optional[WhisperTranscriber] = None
audio_processor = AudioProcessor()


def get_transcriber() -> WhisperTranscriber:
    """Get or initialize the transcriber instance"""
    global transcriber
    if transcriber is None:
        logger.info("Initializing Whisper transcriber...")
        transcriber = WhisperTranscriber(
            model_size=config.MODEL_SIZE,
            device=config.DEVICE,
            compute_type=config.COMPUTE_TYPE
        )
    return transcriber


# Pydantic Models
class TranscriptionResponse(BaseModel):
    """Response model for transcription"""
    text: str = Field(..., description="Full transcribed text")
    segments: list = Field(..., description="Timestamped segments")
    language: Optional[str] = Field(None, description="Detected language")
    language_probability: Optional[float] = Field(None, description="Language detection confidence")
    duration: float = Field(..., description="Audio duration in seconds")
    processing_time: float = Field(..., description="Processing time in seconds")
    real_time_factor: Optional[float] = Field(None, description="Real-time factor (processing_time/duration)")
    model: str = Field(..., description="Model used for transcription")


class LanguageDetectionResponse(BaseModel):
    """Response model for language detection"""
    language: str
    language_probability: float
    duration: float


class ErrorResponse(BaseModel):
    """Error response model"""
    error: str
    detail: Optional[str] = None


# REST API Endpoints

@app.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio(
    file: UploadFile = File(..., description="Audio file to transcribe"),
    language: Optional[str] = Form(None, description="Language code (e.g., 'en', 'es', 'fr'). None for auto-detect."),
    task: str = Form("transcribe", description="Task: 'transcribe' or 'translate' (to English)"),
    beam_size: int = Form(config.DEFAULT_BEAM_SIZE, description="Beam size for decoding (1-10, higher=more accurate)"),
    word_timestamps: bool = Form(True, description="Include word-level timestamps"),
):
    """
    Transcribe an audio file to text

    Supports multiple audio formats: WAV, MP3, M4A, FLAC, OGG, WebM, MP4

    Returns transcription with timestamps and language detection.
    """
    try:
        # Validate file size
        contents = await file.read()
        file_size = len(contents)

        if not audio_processor.validate_file_size(file_size):
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size: {config.MAX_FILE_SIZE_MB}MB"
            )

        # Validate file format
        if not audio_processor.validate_format(file.filename):
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported format. Supported: {', '.join(config.SUPPORTED_FORMATS)}"
            )

        logger.info(f"Received file: {file.filename} ({file_size / 1024:.1f} KB)")

        # Load audio
        try:
            audio = audio_processor.load_audio_from_bytes(contents, file.filename)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to load audio: {str(e)}")

        # Get transcriber
        trans = get_transcriber()

        # Transcribe
        result = trans.transcribe(
            audio,
            language=language,
            task=task,
            beam_size=beam_size,
            word_timestamps=word_timestamps,
        )

        logger.info(f"Transcription successful: {len(result['text'])} characters")

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Transcription error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")


@app.post("/detect-language", response_model=LanguageDetectionResponse)
async def detect_language(file: UploadFile = File(...)):
    """
    Detect the language of an audio file

    Quickly detects the spoken language without full transcription.
    """
    try:
        # Read file
        contents = await file.read()

        if not audio_processor.validate_file_size(len(contents)):
            raise HTTPException(status_code=413, detail="File too large")

        # Load audio
        audio = audio_processor.load_audio_from_bytes(contents, file.filename)

        # Get transcriber
        trans = get_transcriber()

        # Detect language
        result = trans.detect_language(audio)

        logger.info(f"Language detected: {result['language']} ({result['language_probability']:.2f})")

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Language detection error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Try to get transcriber (will initialize if needed)
        trans = get_transcriber()
        model_info = trans.get_model_info()

        return {
            "status": "healthy",
            "service": config.SERVICE_NAME,
            "version": config.SERVICE_VERSION,
            "model": model_info,
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e)
            }
        )


@app.get("/languages")
async def list_languages():
    """List all supported languages"""
    return {
        "count": len(config.SUPPORTED_LANGUAGES),
        "languages": config.SUPPORTED_LANGUAGES,
        "note": "Use language code in /transcribe endpoint or null for auto-detection"
    }


@app.get("/model-info")
async def get_model_info():
    """Get information about the loaded model"""
    try:
        trans = get_transcriber()
        return trans.get_model_info()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def root():
    """Root endpoint with service information"""
    return {
        "service": config.SERVICE_NAME,
        "version": config.SERVICE_VERSION,
        "model": config.MODEL_SIZE,
        "endpoints": {
            "transcribe": "POST /transcribe - Transcribe audio file",
            "detect_language": "POST /detect-language - Detect audio language",
            "websocket": "WS /ws/transcribe - Real-time streaming transcription",
            "languages": "GET /languages - List supported languages",
            "model_info": "GET /model-info - Get model information",
            "health": "GET /health - Health check"
        },
        "documentation": "/docs",
        "supported_formats": config.SUPPORTED_FORMATS,
        "max_file_size_mb": config.MAX_FILE_SIZE_MB,
    }


# WebSocket Endpoint

@app.websocket("/ws/transcribe")
async def websocket_transcribe(websocket: WebSocket):
    """
    WebSocket endpoint for streaming transcription

    Client should send audio chunks as binary data.
    Server responds with JSON transcription results.
    """
    await websocket.accept()
    logger.info("WebSocket connection established")

    audio_buffer = []
    chunk_count = 0

    try:
        trans = get_transcriber()

        while True:
            # Receive audio data
            data = await websocket.receive_bytes()
            chunk_count += 1

            # Buffer audio chunks
            audio_buffer.append(data)

            logger.debug(f"Received chunk {chunk_count}: {len(data)} bytes")

            # Process when buffer reaches threshold
            # Note: This is a simple implementation - production would use VAD
            if len(audio_buffer) >= 10:  # ~5 seconds at typical chunk rates
                try:
                    # Concatenate buffer
                    audio_bytes = b''.join(audio_buffer)

                    # Load and transcribe
                    audio = audio_processor.load_audio_from_bytes(audio_bytes, "chunk.wav")
                    result = trans.transcribe(audio, beam_size=3, word_timestamps=False)

                    # Send result
                    await websocket.send_json({
                        "status": "success",
                        "chunk": chunk_count // 10,
                        "text": result["text"],
                        "language": result["language"],
                        "duration": result["duration"],
                        "processing_time": result["processing_time"],
                    })

                    logger.info(f"Transcribed chunk: {result['text'][:50]}...")

                    # Clear buffer
                    audio_buffer.clear()

                except Exception as e:
                    logger.error(f"Transcription error in WebSocket: {e}")
                    await websocket.send_json({
                        "status": "error",
                        "error": str(e)
                    })
                    audio_buffer.clear()

    except WebSocketDisconnect:
        logger.info("WebSocket connection closed by client")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "status": "error",
                "error": str(e)
            })
        except Exception:
            pass
        finally:
            await websocket.close()


if __name__ == "__main__":
    import uvicorn

    logger.info(f"Starting {config.SERVICE_NAME} on port {config.PORT}")
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level=config.LOG_LEVEL.lower())
