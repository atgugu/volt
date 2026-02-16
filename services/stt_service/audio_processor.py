"""
Audio Processing Utilities for STT Service
"""

import io
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Union

import numpy as np
import soundfile as sf

import config

logger = logging.getLogger(__name__)


class AudioProcessor:
    """Handles audio format conversion and validation"""

    @staticmethod
    def validate_file_size(file_size: int) -> bool:
        """Check if file size is within limits"""
        max_size = config.MAX_FILE_SIZE_MB * 1024 * 1024
        return file_size <= max_size

    @staticmethod
    def validate_format(filename: str) -> bool:
        """Check if file format is supported"""
        file_ext = Path(filename).suffix.lower()
        return file_ext in config.SUPPORTED_FORMATS

    @staticmethod
    def convert_with_ffmpeg(input_path: str, output_path: str) -> bool:
        """
        Convert audio to WAV using ffmpeg

        Args:
            input_path: Path to input audio file
            output_path: Path to output WAV file

        Returns:
            True if conversion succeeded, False otherwise
        """
        try:
            # ffmpeg command: convert to 16kHz mono WAV
            cmd = [
                'ffmpeg', '-i', input_path,
                '-ar', '16000',  # 16kHz sample rate (Whisper native)
                '-ac', '1',       # Mono
                '-y',             # Overwrite output
                '-loglevel', 'error',  # Only show errors
                output_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                logger.error(f"ffmpeg conversion failed: {result.stderr}")
                return False
            logger.info(f"Successfully converted {Path(input_path).suffix} to WAV")
            return True
        except subprocess.TimeoutExpired:
            logger.error("ffmpeg conversion timeout (>30s)")
            return False
        except Exception as e:
            logger.error(f"ffmpeg conversion error: {e}")
            return False

    @staticmethod
    def load_audio_from_bytes(
        audio_bytes: bytes,
        filename: str = "audio.wav"
    ) -> np.ndarray:
        """
        Load audio from bytes

        Args:
            audio_bytes: Audio file bytes
            filename: Original filename (for format detection)

        Returns:
            Numpy array of audio samples (float32, mono, 16kHz)
        """
        try:
            # Save to temporary file
            with tempfile.NamedTemporaryFile(suffix=Path(filename).suffix, delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name

            wav_path = None  # Track converted file for cleanup

            try:
                # Check if format needs ffmpeg conversion
                file_ext = Path(filename).suffix.lower()
                formats_needing_conversion = ['.webm', '.mp4', '.m4a', '.ogg']

                if file_ext in formats_needing_conversion:
                    logger.info(f"Converting {file_ext} to WAV using ffmpeg...")
                    # Create temp WAV file
                    wav_path = tmp_path.replace(file_ext, '.wav')

                    if not AudioProcessor.convert_with_ffmpeg(tmp_path, wav_path):
                        raise ValueError(f"Failed to convert {file_ext} to WAV")

                    # Load converted WAV
                    audio, sample_rate = sf.read(wav_path, dtype='float32')
                else:
                    # Load directly with soundfile
                    audio, sample_rate = sf.read(tmp_path, dtype='float32')

            finally:
                # Clean up temp files
                Path(tmp_path).unlink(missing_ok=True)
                if wav_path:
                    Path(wav_path).unlink(missing_ok=True)

            # Convert to mono if stereo
            if len(audio.shape) > 1:
                audio = audio.mean(axis=1)

            logger.info(f"Loaded audio: {len(audio)/sample_rate:.2f}s at {sample_rate}Hz")

            return audio

        except Exception as e:
            logger.error(f"Failed to load audio from bytes: {e}")
            raise ValueError(f"Invalid audio file: {e}")

    @staticmethod
    def load_audio_from_file(file_path: str) -> np.ndarray:
        """
        Load audio from file path

        Args:
            file_path: Path to audio file

        Returns:
            Numpy array of audio samples (float32, mono)
        """
        try:
            audio, sample_rate = sf.read(file_path, dtype='float32')

            # Convert to mono if stereo
            if len(audio.shape) > 1:
                audio = audio.mean(axis=1)

            logger.info(f"Loaded audio file: {len(audio)/sample_rate:.2f}s at {sample_rate}Hz")

            return audio

        except Exception as e:
            logger.error(f"Failed to load audio file {file_path}: {e}")
            raise

    @staticmethod
    def save_audio(audio: np.ndarray, output_path: str, sample_rate: int = 16000):
        """
        Save audio to file

        Args:
            audio: Numpy array of audio samples
            output_path: Path to save audio file
            sample_rate: Sample rate
        """
        try:
            sf.write(output_path, audio, sample_rate)
            logger.info(f"Saved audio to {output_path}")
        except Exception as e:
            logger.error(f"Failed to save audio: {e}")
            raise

    @staticmethod
    def chunk_audio(
        audio: np.ndarray,
        chunk_duration: float,
        sample_rate: int = 16000,
        overlap: float = 0.0
    ) -> list[np.ndarray]:
        """
        Split audio into chunks

        Args:
            audio: Audio numpy array
            chunk_duration: Duration of each chunk in seconds
            sample_rate: Sample rate
            overlap: Overlap duration in seconds

        Returns:
            List of audio chunks
        """
        chunk_samples = int(chunk_duration * sample_rate)
        overlap_samples = int(overlap * sample_rate)
        step = chunk_samples - overlap_samples

        chunks = []
        for i in range(0, len(audio), step):
            chunk = audio[i:i + chunk_samples]
            if len(chunk) > 0:  # Avoid empty chunks
                chunks.append(chunk)

        logger.info(f"Split audio into {len(chunks)} chunks of {chunk_duration}s")
        return chunks

    @staticmethod
    def get_audio_duration(audio: np.ndarray, sample_rate: int = 16000) -> float:
        """Get audio duration in seconds"""
        return len(audio) / sample_rate

    @staticmethod
    def normalize_audio(audio: np.ndarray) -> np.ndarray:
        """Normalize audio to [-1, 1] range"""
        max_val = np.abs(audio).max()
        if max_val > 0:
            return audio / max_val
        return audio
