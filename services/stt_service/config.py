"""
Configuration for Whisper STT Service
"""

import os
from pathlib import Path

# Service Configuration
SERVICE_NAME = "Whisper STT Service"
SERVICE_VERSION = "1.0.0"
HOST = "0.0.0.0"
PORT = 8034

# Model Configuration
MODEL_NAME = "large-v3-turbo"  # Will use faster-whisper's auto-download
MODEL_SIZE = "large-v3-turbo"
DEVICE = "cuda"  # or "cpu"
COMPUTE_TYPE = "float16"  # For GPU: float16, int8_float16 | For CPU: int8

# Model cache directory (faster-whisper default: ~/.cache/huggingface/hub/)
# Override with STT_MODELS_DIR environment variable if needed
MODELS_DIR = Path(os.getenv("STT_MODELS_DIR", str(Path.home() / ".cache" / "whisper-models")))
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# Transcription Configuration
DEFAULT_BEAM_SIZE = 5  # Higher = more accurate but slower (1-10)
DEFAULT_BATCH_SIZE = 16  # Number of parallel batches (higher = faster but more memory)
DEFAULT_LANGUAGE = None  # None for auto-detect, or "en", "es", "fr", etc.
DEFAULT_TASK = "transcribe"  # "transcribe" or "translate" (to English)

# Advanced Options
VAD_FILTER = True  # Voice Activity Detection - skip silence
VAD_THRESHOLD = 0.5
WORD_TIMESTAMPS = True  # Include word-level timestamps
CONDITION_ON_PREVIOUS_TEXT = True  # Use context from previous segments

# Audio Processing
MAX_FILE_SIZE_MB = 100  # Maximum upload file size
SUPPORTED_FORMATS = [".wav", ".mp3", ".m4a", ".flac", ".ogg", ".webm", ".mp4"]
TARGET_SAMPLE_RATE = 16000  # Whisper expects 16kHz

# Performance
MODEL_WARMUP_ENABLED = True  # Load model on startup
WARMUP_AUDIO_DURATION = 5  # seconds of silence for warmup

# WebSocket Configuration
WS_CHUNK_DURATION = 5  # seconds - buffer duration before transcribing
WS_MAX_CONNECTIONS = 10
WS_TIMEOUT = 300  # seconds

# Logging
LOG_LEVEL = "INFO"
LOG_FILE = "stt_service.log"

# Response Configuration
INCLUDE_LANGUAGE_DETECTION = True
INCLUDE_WORD_TIMESTAMPS = True
INCLUDE_SEGMENT_TIMESTAMPS = True
INCLUDE_CONFIDENCE = True

# Supported Languages (99 languages)
SUPPORTED_LANGUAGES = [
    "en", "zh", "de", "es", "ru", "ko", "fr", "ja", "pt", "tr", "pl", "ca", "nl", "ar", "sv", "it",
    "id", "hi", "fi", "vi", "he", "uk", "el", "ms", "cs", "ro", "da", "hu", "ta", "no", "th", "ur",
    "hr", "bg", "lt", "la", "mi", "ml", "cy", "sk", "te", "fa", "lv", "bn", "sr", "az", "sl", "kn",
    "et", "mk", "br", "eu", "is", "hy", "ne", "mn", "bs", "kk", "sq", "sw", "gl", "mr", "pa", "si",
    "km", "sn", "yo", "so", "af", "oc", "ka", "be", "tg", "sd", "gu", "am", "yi", "lo", "uz", "fo",
    "ht", "ps", "tk", "nn", "mt", "sa", "lb", "my", "bo", "tl", "mg", "as", "tt", "haw", "ln", "ha",
    "ba", "jw", "su"
]
