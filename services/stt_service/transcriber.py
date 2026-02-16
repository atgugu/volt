"""
Whisper Transcriber - Wrapper for faster-whisper model
"""

import logging
import time
from typing import Optional, Dict, List, Any
import numpy as np

from faster_whisper import WhisperModel, BatchedInferencePipeline
import config

logger = logging.getLogger(__name__)


class WhisperTranscriber:
    """Wrapper class for Whisper transcription with faster-whisper"""

    def __init__(
        self,
        model_size: str = config.MODEL_SIZE,
        device: str = config.DEVICE,
        compute_type: str = config.COMPUTE_TYPE,
        download_root: Optional[str] = None,
    ):
        """
        Initialize Whisper model

        Args:
            model_size: Model size (tiny, base, small, medium, large-v2, large-v3, large-v3-turbo)
            device: Device to use (cuda, cpu, auto)
            compute_type: Computation type (float16, int8_float16, int8)
            download_root: Directory to download models to
        """
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.model = None
        self.batched_model = None

        logger.info(f"Initializing Whisper model: {model_size}")
        logger.info(f"Device: {device}, Compute type: {compute_type}")

        try:
            start_time = time.time()

            # Initialize model
            self.model = WhisperModel(
                model_size,
                device=device,
                compute_type=compute_type,
                download_root=str(config.MODELS_DIR) if download_root is None else download_root,
            )

            # Initialize batched inference pipeline for better performance
            self.batched_model = BatchedInferencePipeline(model=self.model)

            load_time = time.time() - start_time
            logger.info(f"Model loaded successfully in {load_time:.2f}s")

            # Warmup
            if config.MODEL_WARMUP_ENABLED:
                self._warmup()

        except Exception as e:
            logger.error(f"Failed to initialize Whisper model: {e}")
            raise

    def _warmup(self):
        """Warm up the model with a short audio sample"""
        try:
            logger.info("Warming up model...")
            # Generate 5 seconds of silence
            sample_rate = config.TARGET_SAMPLE_RATE
            duration = config.WARMUP_AUDIO_DURATION
            silence = np.zeros(sample_rate * duration, dtype=np.float32)

            # Run a quick transcription
            segments, _ = self.model.transcribe(
                silence,
                beam_size=1,
                language="en",
            )
            # Consume generator
            list(segments)

            logger.info("Model warmup complete")
        except Exception as e:
            logger.warning(f"Model warmup failed (non-critical): {e}")

    def transcribe(
        self,
        audio: str | np.ndarray,
        language: Optional[str] = None,
        task: str = "transcribe",
        beam_size: int = config.DEFAULT_BEAM_SIZE,
        batch_size: int = config.DEFAULT_BATCH_SIZE,
        word_timestamps: bool = config.WORD_TIMESTAMPS,
        vad_filter: bool = config.VAD_FILTER,
    ) -> Dict[str, Any]:
        """
        Transcribe audio file or numpy array

        Args:
            audio: Path to audio file or numpy array
            language: Language code (None for auto-detect)
            task: "transcribe" or "translate"
            beam_size: Beam size for decoding (1-10)
            batch_size: Batch size for parallel processing
            word_timestamps: Include word-level timestamps
            vad_filter: Use Voice Activity Detection to filter silence

        Returns:
            Dictionary with transcription results
        """
        try:
            start_time = time.time()

            logger.info(f"Starting transcription (language: {language or 'auto'}, task: {task})")

            # Use batched model for better performance
            segments, info = self.batched_model.transcribe(
                audio,
                language=language,
                task=task,
                beam_size=beam_size,
                batch_size=batch_size,
                word_timestamps=word_timestamps,
                vad_filter=vad_filter,
                condition_on_previous_text=config.CONDITION_ON_PREVIOUS_TEXT,
            )

            # Convert segments generator to list and extract data
            segments_list = []
            full_text = []

            for segment in segments:
                segment_data = {
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text,
                }

                # Add word timestamps if available
                if word_timestamps and hasattr(segment, "words") and segment.words:
                    segment_data["words"] = [
                        {
                            "word": word.word,
                            "start": word.start,
                            "end": word.end,
                            "probability": word.probability,
                        }
                        for word in segment.words
                    ]

                segments_list.append(segment_data)
                full_text.append(segment.text)

            # Combine all text
            text = " ".join(full_text).strip()

            # Calculate processing time
            processing_time = time.time() - start_time

            # Build response
            result = {
                "text": text,
                "segments": segments_list,
                "language": info.language if config.INCLUDE_LANGUAGE_DETECTION else None,
                "language_probability": info.language_probability if config.INCLUDE_LANGUAGE_DETECTION else None,
                "duration": info.duration,
                "processing_time": processing_time,
                "model": self.model_size,
            }

            # Calculate real-time factor (RTF)
            if info.duration > 0:
                rtf = processing_time / info.duration
                result["real_time_factor"] = rtf
                logger.info(f"Transcription complete: {processing_time:.2f}s for {info.duration:.2f}s audio (RTF: {rtf:.2f}x)")
            else:
                logger.info(f"Transcription complete: {processing_time:.2f}s")

            return result

        except Exception as e:
            logger.error(f"Transcription failed: {e}", exc_info=True)
            raise

    def transcribe_streaming(
        self,
        audio_chunks: List[np.ndarray],
        language: Optional[str] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Transcribe audio chunks for streaming scenarios

        Args:
            audio_chunks: List of audio numpy arrays
            language: Language code (None for auto-detect)
            **kwargs: Additional transcription parameters

        Returns:
            List of transcription results for each chunk
        """
        results = []

        for i, chunk in enumerate(audio_chunks):
            logger.info(f"Transcribing chunk {i+1}/{len(audio_chunks)}")
            try:
                result = self.transcribe(
                    chunk,
                    language=language,
                    **kwargs
                )
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to transcribe chunk {i+1}: {e}")
                results.append({
                    "text": "",
                    "error": str(e),
                    "chunk_index": i
                })

        return results

    def detect_language(self, audio: str | np.ndarray) -> Dict[str, Any]:
        """
        Detect the language of the audio

        Args:
            audio: Path to audio file or numpy array

        Returns:
            Dictionary with language detection results
        """
        try:
            # Transcribe first 30 seconds to detect language
            segments, info = self.model.transcribe(
                audio,
                language=None,  # Auto-detect
                beam_size=1,  # Fast detection
                word_timestamps=False,
            )

            # Consume generator (we only need the info)
            list(segments)

            return {
                "language": info.language,
                "language_probability": info.language_probability,
                "duration": info.duration,
            }

        except Exception as e:
            logger.error(f"Language detection failed: {e}")
            raise

    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the loaded model"""
        return {
            "model_size": self.model_size,
            "device": self.device,
            "compute_type": self.compute_type,
            "supported_languages": len(config.SUPPORTED_LANGUAGES),
            "word_timestamps": config.WORD_TIMESTAMPS,
            "vad_filter": config.VAD_FILTER,
        }
