"""Tests for AgentState and state management."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from framework.state.agent_state import (
    AgentState,
    create_initial_state,
    get_state_summary,
)


def test_create_initial_state():
    state = create_initial_state("test-session")
    assert state["session_id"] == "test-session"
    assert state["agent_id"] is None
    assert state["voice_mode"] is False
    assert state["collected_fields"] == {}
    assert state["required_fields"] == []
    assert state["is_complete"] is False
    assert state["retry_count"] == 0


def test_create_initial_state_with_agent():
    state = create_initial_state(
        session_id="s1",
        agent_id="profile_collector",
        agent_name="Profile Agent",
        voice_mode=True,
    )
    assert state["agent_id"] == "profile_collector"
    assert state["agent_name"] == "Profile Agent"
    assert state["voice_mode"] is True


def test_state_immutable_update():
    state = create_initial_state("s1")
    updated = {**state, "collected_fields": {"name": "John"}}
    assert state["collected_fields"] == {}
    assert updated["collected_fields"] == {"name": "John"}


def test_get_state_summary():
    state = create_initial_state("s1", agent_id="test", agent_name="Test Agent")
    summary = get_state_summary(state)
    assert "test-session" not in summary  # different session
    assert "Test Agent" in summary
    assert "0/0" in summary  # no fields yet


def test_qa_mode_defaults():
    state = create_initial_state("s1")
    assert state["qa_mode_active"] is False
    assert state["saved_graph_position"] is None
    assert state["qa_consecutive_questions"] == 0
    assert state["should_enter_qa_mode"] is False
