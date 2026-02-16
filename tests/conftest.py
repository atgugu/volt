"""Test fixtures for the agent framework."""

import sys
import os
import pytest
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def project_root():
    return PROJECT_ROOT


@pytest.fixture
def agents_dir():
    return PROJECT_ROOT / "agents"


@pytest.fixture
def sample_agent_config():
    """A minimal valid agent configuration."""
    return {
        "name": "Test Agent",
        "id": "test_agent",
        "description": "A test agent",
        "greeting": "Hello! This is a test.",
        "persona": "test assistant",
        "fields": [
            {
                "name": "test_field",
                "type": "string",
                "required": True,
                "question": "What is the test value?",
                "order": 0,
            }
        ],
        "completion": {
            "message": "Test complete: {test_field}",
            "action": "log",
        },
    }
