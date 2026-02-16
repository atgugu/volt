"""
Kokoro TTS Streaming Service

A FastAPI service for streaming text-to-speech generation using the Kokoro-82M model.
Provides real-time audio streaming with support for multiple voices and languages.
"""

import io
import logging
import wave
from typing import Optional

import numpy as np
import soundfile as sf
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# Import TTS preprocessor
from tts_preprocessor import preprocess_for_tts

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Kokoro TTS Service",
    description="Streaming text-to-speech service using Kokoro-82M",
    version="1.0.0"
)

# Global pipeline instance (lazy loaded)
pipeline = None
SAMPLE_RATE = 24000

# Available voices for each language
VOICES = {
    "en": ["af_heart", "af_bella", "af_sarah", "af_nicole", "am_adam", "am_michael", "bf_emma", "bf_isabella", "bm_george", "bm_lewis"],
    "ja": ["af_yuna", "am_sota"],
    "zh": ["af_lulu", "am_leo"],
    "es": ["af_sofia"],
    "fr": ["af_chloe"],
    "hi": ["af_priya"],
    "it": ["af_chiara"],
    "pt": ["af_isabela"]
}

# Language code mapping
LANG_CODES = {
    "en": "a",  # American English
    "en-gb": "b",  # British English
    "es": "e",  # Spanish
    "fr": "f",  # French
    "hi": "h",  # Hindi
    "it": "i",  # Italian
    "ja": "j",  # Japanese
    "pt": "p",  # Portuguese
    "zh": "z"   # Chinese
}


class TTSRequest(BaseModel):
    """Request model for TTS generation"""
    text: str = Field(..., description="Text to convert to speech", min_length=1)
    voice: str = Field(default="af_heart", description="Voice to use for speech generation")
    speed: float = Field(default=1.2, description="Speed of speech (0.5 to 2.0)", ge=0.5, le=2.0)
    language: str = Field(default="en", description="Language code (en, ja, zh, es, fr, hi, it, pt)")
    format: str = Field(default="wav", description="Audio format (currently only wav supported)")


def get_pipeline(lang_code: str = "a"):
    """Initialize or return cached Kokoro pipeline"""
    global pipeline

    try:
        from kokoro import KPipeline

        # Create new pipeline for the requested language
        # Note: We create a new pipeline each time to support language switching
        logger.info(f"Initializing Kokoro pipeline with language code: {lang_code}")
        return KPipeline(lang_code=lang_code)

    except Exception as e:
        logger.error(f"Failed to initialize Kokoro pipeline: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to initialize TTS pipeline: {str(e)}")


def numpy_to_wav_bytes(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Convert numpy audio array to WAV bytes"""
    # Ensure audio is in the correct format
    if audio.dtype != np.int16:
        # Convert float to int16
        audio = (audio * 32767).astype(np.int16)

    # Create in-memory WAV file
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio.tobytes())

    wav_buffer.seek(0)
    return wav_buffer.read()


async def generate_audio_stream(text: str, voice: str, speed: float, language: str):
    """Generator function for streaming audio chunks"""
    try:
        # Preprocess text for TTS
        processed_text = preprocess_for_tts(text)

        # Get language code
        lang_code = LANG_CODES.get(language, "a")

        # Initialize pipeline
        pipe = get_pipeline(lang_code)

        # Generate audio using Kokoro
        logger.info(f"Generating speech for text: {processed_text[:50]}... (voice: {voice}, speed: {speed})")
        generator = pipe(processed_text, voice=voice, speed=speed)

        # Track if this is the first chunk
        first_chunk = True
        all_audio = []

        # Stream audio chunks
        for i, (graphemes, phonemes, audio) in enumerate(generator):
            logger.info(f"Generated chunk {i}: {len(audio)} samples")

            # Collect all audio chunks
            all_audio.append(audio)

        # Concatenate all audio chunks
        if all_audio:
            full_audio = np.concatenate(all_audio)
            logger.info(f"Total audio length: {len(full_audio)} samples ({len(full_audio)/SAMPLE_RATE:.2f} seconds)")

            # Convert to WAV and yield
            wav_bytes = numpy_to_wav_bytes(full_audio, SAMPLE_RATE)
            yield wav_bytes
        else:
            logger.warning("No audio generated")

    except Exception as e:
        logger.error(f"Error generating audio: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Audio generation failed: {str(e)}")


@app.post("/generate")
async def generate_speech(request: TTSRequest):
    """
    Generate speech from text with streaming response

    Returns audio in WAV format, streamed in real-time as it's generated.
    """
    try:
        # Validate voice for language
        lang_voices = VOICES.get(request.language, VOICES["en"])
        if request.voice not in lang_voices and request.voice not in VOICES.get("en", []):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid voice '{request.voice}' for language '{request.language}'. Available voices: {lang_voices}"
            )

        # Generate streaming response
        return StreamingResponse(
            generate_audio_stream(request.text, request.voice, request.speed, request.language),
            media_type="audio/wav",
            headers={
                "Content-Disposition": "attachment; filename=speech.wav",
                "Cache-Control": "no-cache"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in generate_speech endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Try to initialize pipeline to verify everything works
        pipe = get_pipeline("a")
        return {
            "status": "healthy",
            "service": "kokoro-tts",
            "model": "Kokoro-82M",
            "sample_rate": SAMPLE_RATE
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }


@app.get("/voices")
async def list_voices(language: Optional[str] = Query(None, description="Filter by language code")):
    """List available voices, optionally filtered by language"""
    if language:
        if language not in VOICES:
            raise HTTPException(status_code=400, detail=f"Unknown language: {language}")
        return {
            "language": language,
            "voices": VOICES[language]
        }

    return {
        "languages": list(VOICES.keys()),
        "voices_by_language": VOICES,
        "total_voices": sum(len(v) for v in VOICES.values())
    }


@app.get("/")
async def root():
    """Root endpoint with service information"""
    return {
        "service": "Kokoro TTS Streaming Service",
        "version": "1.0.0",
        "model": "Kokoro-82M",
        "endpoints": {
            "generate": "POST /generate - Generate speech from text",
            "voices": "GET /voices - List available voices",
            "health": "GET /health - Health check"
        },
        "documentation": "/docs"
    }


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting Kokoro TTS Service on port 8033")
    uvicorn.run(app, host="0.0.0.0", port=8033, log_level="info")
