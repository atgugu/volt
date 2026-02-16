"""
Global framework settings loaded from environment variables.

All settings have sensible defaults so the framework works out of the box.
Override via .env file or environment variables.
"""

import os
from pathlib import Path

# =============================================================================
# Path Configuration
# =============================================================================
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
AGENTS_DIR = os.getenv("AGENTS_DIR", str(PROJECT_ROOT / "agents"))
DB_PATH = os.getenv("DB_PATH", str(PROJECT_ROOT / "data" / "framework.db"))

# =============================================================================
# LLM Service
# =============================================================================
LLM_MODEL_PATH = os.getenv("LLM_MODEL_PATH", "")
LLM_CONTEXT_SIZE = int(os.getenv("LLM_CONTEXT_SIZE", "8192"))
LLM_GPU_LAYERS = int(os.getenv("LLM_GPU_LAYERS", "-1"))
LLM_THREADS = int(os.getenv("LLM_THREADS", "8"))
LLM_PORT = int(os.getenv("LLM_PORT", "8000"))

# Generation defaults
LLM_DEFAULT_MAX_TOKENS = int(os.getenv("LLM_DEFAULT_MAX_TOKENS", "1024"))
LLM_DEFAULT_TEMPERATURE = float(os.getenv("LLM_DEFAULT_TEMPERATURE", "0.7"))
LLM_DEFAULT_TOP_P = float(os.getenv("LLM_DEFAULT_TOP_P", "0.9"))
LLM_DEFAULT_TOP_K = int(os.getenv("LLM_DEFAULT_TOP_K", "40"))
LLM_DEFAULT_REPEAT_PENALTY = float(os.getenv("LLM_DEFAULT_REPEAT_PENALTY", "1.1"))

# =============================================================================
# Load Balancer
# =============================================================================
LB_WORKER_COUNT = int(os.getenv("LB_WORKER_COUNT", "1"))
LB_WORKER_BASE_PORT = int(os.getenv("LB_WORKER_BASE_PORT", "8010"))
LB_HEALTH_CHECK_INTERVAL = int(os.getenv("LB_HEALTH_CHECK_INTERVAL", "30"))
LB_REQUEST_TIMEOUT = int(os.getenv("LB_REQUEST_TIMEOUT", "300"))

# =============================================================================
# Backend Service
# =============================================================================
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "10821"))
BACKEND_HOST = os.getenv("BACKEND_HOST", "0.0.0.0")

# =============================================================================
# Voice Services
# =============================================================================
TTS_SERVICE_URL = os.getenv("TTS_SERVICE_URL", f"http://localhost:{os.getenv('TTS_PORT', '8033')}")
STT_SERVICE_URL = os.getenv("STT_SERVICE_URL", f"http://localhost:{os.getenv('STT_PORT', '8034')}")
TTS_PORT = int(os.getenv("TTS_PORT", "8033"))
STT_PORT = int(os.getenv("STT_PORT", "8034"))

# =============================================================================
# LLM Endpoint (used by framework nodes to call LLM service)
# =============================================================================
LLM_ENDPOINT = os.getenv("LLM_ENDPOINT", f"http://localhost:{LLM_PORT}")

# =============================================================================
# Framework
# =============================================================================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
VERBOSE = os.getenv("VERBOSE", "false").lower() in ("true", "1", "yes")
