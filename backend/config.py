"""
Backend Configuration

API settings and service URLs.
"""

import os

# API Settings
API_TITLE = "Local LLM Agent Framework"
API_DESCRIPTION = "A modular framework for building agentic workflows with local LLMs and LangGraph"
API_VERSION = "1.0.0"

# Service URLs
LLM_ENDPOINT = os.getenv("LLM_ENDPOINT", f"http://localhost:{os.getenv('LLM_PORT', '8000')}")
TTS_SERVICE_URL = os.getenv("TTS_SERVICE_URL", f"http://localhost:{os.getenv('TTS_PORT', '8033')}")
STT_SERVICE_URL = os.getenv("STT_SERVICE_URL", f"http://localhost:{os.getenv('STT_PORT', '8034')}")

# Backend
BACKEND_HOST = os.getenv("BACKEND_HOST", "0.0.0.0")
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "10821"))

# Session storage
MAX_SESSIONS = int(os.getenv("MAX_SESSIONS", "1000"))
SESSION_TIMEOUT = int(os.getenv("SESSION_TIMEOUT", "3600"))  # seconds

# Verbose logging
VERBOSE = os.getenv("VERBOSE", "false").lower() in ("true", "1", "yes")
