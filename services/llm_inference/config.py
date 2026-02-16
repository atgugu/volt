# services/llm_inference/config.py
import os
from chat_formats import initialize_format_detector, detect_and_get_format

# --- Model Loading Configuration ---
# Model path is configurable via environment variable LLM_MODEL_PATH
MODEL_PATH = os.getenv(
    "LLM_MODEL_PATH",
    os.path.join(os.getenv("LLM_MODELS_DIR", "./models"), "model.gguf")
)
MODEL_FILENAME = os.path.basename(MODEL_PATH)

N_CTX = int(os.getenv("LLM_N_CTX", 8192))  # Context window size
N_GPU_LAYERS = int(os.getenv("LLM_N_GPU_LAYERS", -1))  # Offload all layers to GPU
N_THREADS = int(os.getenv("LLM_N_THREADS", 32))
N_BATCH = int(os.getenv("LLM_N_BATCH", N_CTX))  # Match N_CTX for optimal GPU utilization
USE_MMAP = os.getenv("LLM_USE_MMAP", "true").lower() == "true"
USE_MLOCK = os.getenv("LLM_USE_MLOCK", "true").lower() == "true"  # Will fall back if it fails
FLASH_ATTN = os.getenv("LLM_FLASH_ATTN", "true").lower() == "true"
SEED = int(os.getenv("LLM_SEED", 1))

# --- Chat Format Configuration ---
# Optional manual override for chat format (None for auto-detection)
# Valid options: "mistral", "qwen", "gemma", or None
_chat_format_override_env = os.getenv("LLM_CHAT_FORMAT_OVERRIDE", "")
CHAT_FORMAT_OVERRIDE = _chat_format_override_env if _chat_format_override_env else None

# Initialize format detector
initialize_format_detector()

# Get chat format based on model path and optional override
_chat_format = detect_and_get_format(MODEL_PATH, CHAT_FORMAT_OVERRIDE)

# --- Default Generation Configuration ---
# These are the default parameters for a generation request.
# They can be overridden by the client in the API call.
DEFAULT_MAX_TOKENS = int(os.getenv("LLM_DEFAULT_MAX_TOKENS", 1024))

# Model-specific parameters (auto-detected from model path, overridable via env)
if os.getenv("LLM_DEFAULT_TEMP"):
    # If explicitly set via env, use those values
    DEFAULT_TEMP = float(os.getenv("LLM_DEFAULT_TEMP"))
    DEFAULT_TOP_P = float(os.getenv("LLM_DEFAULT_TOP_P", 0.95))
    DEFAULT_TOP_K = int(os.getenv("LLM_DEFAULT_TOP_K", 40))
elif "qwen" in MODEL_PATH.lower():
    # Qwen model parameters
    DEFAULT_TEMP = 0.7
    DEFAULT_TOP_P = 0.8
    DEFAULT_TOP_K = 20
elif "gemma" in MODEL_PATH.lower():
    # Gemma model parameters
    DEFAULT_TEMP = 1.0
    DEFAULT_TOP_P = 0.95
    DEFAULT_TOP_K = 64
elif "mistral" in MODEL_PATH.lower():
    # Mistral model parameters
    DEFAULT_TEMP = 0.2
    DEFAULT_TOP_P = 0.95
    DEFAULT_TOP_K = 40
else:
    # Generic defaults
    DEFAULT_TEMP = 0.7
    DEFAULT_TOP_P = 0.95
    DEFAULT_TOP_K = 40

DEFAULT_REPEAT_PENALTY = float(os.getenv("LLM_DEFAULT_REPEAT_PENALTY", 1.0))

# Stop sequences are automatically determined by the chat format
STOP_SEQUENCES = _chat_format.get_stop_sequences()

# --- Model Warmup Configuration ---
# Perform a warmup prompt to ensure model is fully ready
ENABLE_WARMUP = os.getenv("LLM_ENABLE_WARMUP", "true").lower() == "true"
WARMUP_PROMPT = os.getenv("LLM_WARMUP_PROMPT", "Hello, are you ready?")
WARMUP_MAX_TOKENS = int(os.getenv("LLM_WARMUP_MAX_TOKENS", 10))


# --- Chat Format Access ---
def get_chat_format():
    """Get the current chat format instance."""
    return _chat_format
