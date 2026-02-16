"""Tests for the profile_collector example agent."""

import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from framework.config.agent_registry import AgentRegistry


class TestProfileAgent:
    def setup_method(self):
        agents_dir = Path(__file__).parent.parent / "agents"
        self.registry = AgentRegistry(str(agents_dir))
        self.registry.discover()
        self.agent = self.registry.get_agent("profile_collector")

    def test_agent_exists(self):
        assert self.agent is not None

    def test_agent_metadata(self):
        assert self.agent.id == "profile_collector"
        assert self.agent.name == "User Profile Collection"
        assert "profile" in self.agent.description.lower()

    def test_required_fields(self):
        required_names = [f["name"] for f in self.agent.required_fields]
        assert "full_name" in required_names
        assert "email" in required_names
        assert "phone" in required_names

    def test_optional_fields(self):
        optional_names = [f["name"] for f in self.agent.optional_fields]
        assert "age" in optional_names
        assert "interests" in optional_names

    def test_field_order(self):
        """Fields should be sorted by order."""
        orders = [f.get("order", 999) for f in self.agent.required_fields]
        assert orders == sorted(orders)

    def test_validators_assigned(self):
        name_field = self.agent.get_field_by_name("full_name")
        assert name_field["validator"] == "name"

        email_field = self.agent.get_field_by_name("email")
        assert email_field["validator"] == "email"

        age_field = self.agent.get_field_by_name("age")
        assert age_field["validator"] == "number"
        assert age_field["validator_config"]["min"] == 13
        assert age_field["validator_config"]["max"] == 120

    def test_completion_template(self):
        template = self.agent.completion_message
        assert "{full_name}" in template
        assert "{email}" in template

    def test_greeting(self):
        assert self.agent.greeting
        assert len(self.agent.greeting) > 10

    def test_agent_json_valid(self):
        """Verify agent.json is valid JSON."""
        json_path = Path(__file__).parent.parent / "agents" / "profile_collector" / "agent.json"
        with open(json_path) as f:
            data = json.load(f)
        assert data["id"] == "profile_collector"
        assert len(data["fields"]) == 5
