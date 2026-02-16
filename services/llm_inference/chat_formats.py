"""
Chat format detection and handling for different LLM models.
Provides automatic detection of chat formats based on model names and manual overrides.
"""

import os
from abc import ABC, abstractmethod


class ChatFormat(ABC):
    """Base class for chat format implementations."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def get_stop_sequences(self) -> list:
        """Get stop sequences for this chat format."""
        pass

    @abstractmethod
    def clean_response(self, response: str) -> str:
        """Clean the model response for this format."""
        pass


class MistralChatFormat(ChatFormat):
    """Chat format for Mistral models."""

    def __init__(self):
        super().__init__("mistral")

    def get_stop_sequences(self) -> list:
        return ["</s>", "[INST]", "[/INST]"]

    def clean_response(self, response: str) -> str:
        """Clean Mistral model response."""
        # Remove common artifacts
        response = response.strip()

        # Remove stop sequences that might appear
        for stop in self.get_stop_sequences():
            response = response.replace(stop, "")

        return response.strip()


class GemmaChatFormat(ChatFormat):
    """Chat format for Gemma models."""

    def __init__(self):
        super().__init__("gemma")

    def get_stop_sequences(self) -> list:
        return ["<end_of_turn>", "<start_of_turn>"]

    def clean_response(self, response: str) -> str:
        """Clean Gemma model response."""
        response = response.strip()

        # Remove stop sequences
        for stop in self.get_stop_sequences():
            response = response.replace(stop, "")

        # Remove model/user prefixes that might appear
        if response.startswith("model\n"):
            response = response[6:].strip()

        return response.strip()


class QwenChatFormat(ChatFormat):
    """Chat format for Qwen models."""

    def __init__(self):
        super().__init__("qwen")

    def get_stop_sequences(self) -> list:
        return ["<|im_end|>", "<|im_start|>", "<|endoftext|>"]

    def clean_response(self, response: str) -> str:
        """Clean Qwen model response."""
        response = response.strip()

        # Remove stop sequences
        for stop in self.get_stop_sequences():
            response = response.replace(stop, "")

        return response.strip()


# Global format detector registry
_format_detector = None


def initialize_format_detector():
    """Initialize the format detector (call once at startup)."""
    global _format_detector
    if _format_detector is None:
        _format_detector = {
            "mistral": MistralChatFormat(),
            "gemma": GemmaChatFormat(),
            "qwen": QwenChatFormat(),
        }


def detect_and_get_format(model_path: str, override: str = None) -> ChatFormat:
    """
    Detect chat format from model path or use override.

    Args:
        model_path: Path to the model file
        override: Manual override for chat format (mistral, gemma, qwen)

    Returns:
        ChatFormat instance
    """
    if _format_detector is None:
        raise RuntimeError(
            "Format detector not initialized. Call initialize_format_detector() first."
        )

    # Use manual override if provided
    if override and override.lower() in _format_detector:
        return _format_detector[override.lower()]

    # Auto-detect from model path/filename
    model_filename = os.path.basename(model_path).lower()

    if "mistral" in model_filename:
        return _format_detector["mistral"]
    elif "gemma" in model_filename:
        return _format_detector["gemma"]
    elif "qwen" in model_filename:
        return _format_detector["qwen"]
    else:
        # Default fallback to Mistral format
        return _format_detector["mistral"]
