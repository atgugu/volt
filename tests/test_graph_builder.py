"""Tests for agent graph builder and registry."""

import sys
import json
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from framework.config.agent_registry import AgentRegistry, AgentDefinition, _validate_agent_config


class TestAgentValidation:
    def test_valid_config(self):
        config = {
            "name": "Test",
            "id": "test",
            "description": "Test agent",
            "fields": [
                {"name": "f1", "type": "string", "question": "Q?"}
            ],
        }
        errors = _validate_agent_config(config, Path("."))
        assert len(errors) == 0

    def test_missing_required_keys(self):
        config = {"name": "Test"}
        errors = _validate_agent_config(config, Path("."))
        assert len(errors) > 0

    def test_empty_fields(self):
        config = {
            "name": "Test",
            "id": "test",
            "description": "Test",
            "fields": [],
        }
        errors = _validate_agent_config(config, Path("."))
        assert any("at least one field" in e for e in errors)

    def test_duplicate_field_names(self):
        config = {
            "name": "Test",
            "id": "test",
            "description": "Test",
            "fields": [
                {"name": "f1", "type": "string", "question": "Q1?"},
                {"name": "f1", "type": "string", "question": "Q2?"},
            ],
        }
        errors = _validate_agent_config(config, Path("."))
        assert any("Duplicate" in e for e in errors)


class TestAgentDefinition:
    def test_field_separation(self):
        config = {
            "name": "Test",
            "id": "test",
            "description": "Test",
            "fields": [
                {"name": "req", "type": "string", "required": True, "question": "Q?"},
                {"name": "opt", "type": "string", "required": False, "question": "Q?"},
            ],
        }
        ad = AgentDefinition(config, Path("."))
        assert len(ad.required_fields) == 1
        assert len(ad.optional_fields) == 1
        assert ad.required_fields[0]["name"] == "req"
        assert ad.optional_fields[0]["name"] == "opt"

    def test_get_field_by_name(self):
        config = {
            "name": "Test",
            "id": "test",
            "description": "Test",
            "fields": [
                {"name": "email", "type": "string", "question": "Email?", "validator": "email"},
            ],
        }
        ad = AgentDefinition(config, Path("."))
        field = ad.get_field_by_name("email")
        assert field is not None
        assert field["validator"] == "email"

        missing = ad.get_field_by_name("nonexistent")
        assert missing is None

    def test_to_dict(self):
        config = {
            "name": "Test",
            "id": "test",
            "description": "Test agent",
            "fields": [
                {"name": "f1", "type": "string", "required": True, "question": "Q?"},
                {"name": "f2", "type": "string", "required": False, "question": "Q?"},
            ],
        }
        ad = AgentDefinition(config, Path("."))
        d = ad.to_dict()
        assert d["id"] == "test"
        assert d["field_count"] == 2
        assert d["required_field_count"] == 1
        assert d["optional_field_count"] == 1


class TestAgentRegistry:
    def test_discover_agents(self):
        """Test discovery with real agents/ directory."""
        agents_dir = Path(__file__).parent.parent / "agents"
        registry = AgentRegistry(str(agents_dir))
        discovered = registry.discover()
        assert "profile_collector" in discovered

    def test_discover_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = AgentRegistry(tmpdir)
            discovered = registry.discover()
            assert len(discovered) == 0

    def test_get_agent(self):
        agents_dir = Path(__file__).parent.parent / "agents"
        registry = AgentRegistry(str(agents_dir))
        registry.discover()
        agent = registry.get_agent("profile_collector")
        assert agent is not None
        assert agent.name == "User Profile Collection"

    def test_list_agents(self):
        agents_dir = Path(__file__).parent.parent / "agents"
        registry = AgentRegistry(str(agents_dir))
        registry.discover()
        agents = registry.list_agents()
        assert len(agents) > 0
        assert all("id" in a for a in agents)
