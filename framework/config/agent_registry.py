"""
Agent Registry - Auto-discovers and manages agent definitions.

Scans the agents/ directory for agent.json files, validates them,
and provides access to agent definitions and compiled LangGraph workflows.
"""

import json
import logging
import importlib
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# Required fields in agent.json
REQUIRED_AGENT_KEYS = {"name", "id", "description", "fields"}
REQUIRED_FIELD_KEYS = {"name", "type", "question"}


class AgentDefinition:
    """Parsed and validated agent definition from agent.json."""

    def __init__(self, config: Dict[str, Any], agent_dir: Path):
        self.config = config
        self.agent_dir = agent_dir

        # Core properties
        self.id: str = config["id"]
        self.name: str = config["name"]
        self.description: str = config["description"]
        self.greeting: str = config.get("greeting", f"Hello! I'm the {self.name} agent. How can I help?")
        self.persona: str = config.get("persona", "helpful assistant")

        # Fields
        self.fields: List[Dict[str, Any]] = config["fields"]
        self.required_fields = [f for f in self.fields if f.get("required", True)]
        self.optional_fields = [f for f in self.fields if not f.get("required", True)]
        self.conditional_fields = [f for f in self.fields if f.get("condition")]

        # Sort by order
        self.required_fields.sort(key=lambda f: f.get("order", 999))
        self.optional_fields.sort(key=lambda f: f.get("order", 999))

        # Completion config
        self.completion = config.get("completion", {})
        self.completion_message = self.completion.get(
            "message", "All information collected. Thank you!"
        )
        self.completion_action = self.completion.get("action", "log")

        # Custom modules
        self._custom_nodes = None
        self._custom_validators = None

    @property
    def custom_nodes(self) -> Optional[Any]:
        """Lazy-load custom_nodes.py from agent directory if it exists."""
        if self._custom_nodes is None:
            custom_path = self.agent_dir / "custom_nodes.py"
            if custom_path.exists():
                spec = importlib.util.spec_from_file_location(
                    f"agents.{self.id}.custom_nodes", custom_path
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                self._custom_nodes = module
                logger.info(f"Loaded custom nodes for agent '{self.id}'")
        return self._custom_nodes

    @property
    def custom_validators(self) -> Optional[Any]:
        """Lazy-load custom_validators.py from agent directory if it exists."""
        if self._custom_validators is None:
            custom_path = self.agent_dir / "custom_validators.py"
            if custom_path.exists():
                spec = importlib.util.spec_from_file_location(
                    f"agents.{self.id}.custom_validators", custom_path
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                self._custom_validators = module
                logger.info(f"Loaded custom validators for agent '{self.id}'")
        return self._custom_validators

    def get_field_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a field definition by name."""
        for field in self.fields:
            if field["name"] == name:
                return field
        return None

    def get_field_question(self, field_name: str) -> str:
        """Get the question prompt for a field."""
        field = self.get_field_by_name(field_name)
        if field:
            return field.get("question", f"Please provide your {field_name}.")
        return f"Please provide your {field_name}."

    def get_field_validator(self, field_name: str) -> Optional[str]:
        """Get the validator name for a field."""
        field = self.get_field_by_name(field_name)
        if field:
            return field.get("validator")
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for API responses."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "field_count": len(self.fields),
            "required_field_count": len(self.required_fields),
            "optional_field_count": len(self.optional_fields),
        }


def _validate_agent_config(config: Dict[str, Any], path: Path) -> List[str]:
    """Validate an agent.json configuration. Returns list of errors."""
    errors = []

    # Check required keys
    missing_keys = REQUIRED_AGENT_KEYS - set(config.keys())
    if missing_keys:
        errors.append(f"Missing required keys: {missing_keys}")

    # Validate fields
    fields = config.get("fields", [])
    if not fields:
        errors.append("Agent must define at least one field")

    field_names = set()
    for i, field in enumerate(fields):
        missing_field_keys = REQUIRED_FIELD_KEYS - set(field.keys())
        if missing_field_keys:
            errors.append(f"Field {i} missing keys: {missing_field_keys}")

        name = field.get("name", "")
        if name in field_names:
            errors.append(f"Duplicate field name: '{name}'")
        field_names.add(name)

    return errors


class AgentRegistry:
    """
    Auto-discovers and manages agent definitions.

    Usage:
        registry = AgentRegistry("/path/to/agents")
        registry.discover()
        agent = registry.get_agent("profile_collector")
    """

    def __init__(self, agents_dir: str = None):
        if agents_dir is None:
            from framework.config.settings import AGENTS_DIR
            agents_dir = AGENTS_DIR

        self.agents_dir = Path(agents_dir)
        self._agents: Dict[str, AgentDefinition] = {}
        self._graphs: Dict[str, Any] = {}

    def discover(self) -> List[str]:
        """
        Scan agents/ directory for agent.json files and load them.

        Returns:
            List of discovered agent IDs
        """
        self._agents.clear()
        self._graphs.clear()

        if not self.agents_dir.exists():
            logger.warning(f"Agents directory not found: {self.agents_dir}")
            return []

        discovered = []

        for agent_dir in sorted(self.agents_dir.iterdir()):
            if not agent_dir.is_dir():
                continue

            config_path = agent_dir / "agent.json"
            if not config_path.exists():
                continue

            try:
                with open(config_path, "r") as f:
                    config = json.load(f)

                # Validate
                errors = _validate_agent_config(config, config_path)
                if errors:
                    logger.error(
                        f"Invalid agent config at {config_path}: {errors}"
                    )
                    continue

                # Create definition
                agent_def = AgentDefinition(config, agent_dir)
                self._agents[agent_def.id] = agent_def
                discovered.append(agent_def.id)

                logger.info(
                    f"Discovered agent: '{agent_def.name}' (id={agent_def.id}, "
                    f"fields={len(agent_def.fields)})"
                )

            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in {config_path}: {e}")
            except Exception as e:
                logger.error(f"Error loading agent from {agent_dir}: {e}")

        logger.info(f"Discovered {len(discovered)} agent(s): {discovered}")
        return discovered

    def get_agent(self, agent_id: str) -> Optional[AgentDefinition]:
        """Get an agent definition by ID."""
        return self._agents.get(agent_id)

    def list_agents(self) -> List[Dict[str, str]]:
        """List all available agents with summary info."""
        return [agent.to_dict() for agent in self._agents.values()]

    def get_graph(self, agent_id: str, endpoint: str = None, verbose: bool = False, checkpointer=None):
        """
        Get or build a compiled LangGraph for an agent.

        Graphs are cached after first build. A graph compiled with a
        checkpointer is cached separately from one compiled without.

        Args:
            agent_id: Agent ID
            endpoint: LLM service endpoint
            verbose: Enable verbose logging
            checkpointer: Optional LangGraph checkpointer for state persistence

        Returns:
            Compiled LangGraph workflow, or None if agent not found
        """
        if endpoint is None:
            from framework.config.settings import LLM_ENDPOINT
            endpoint = LLM_ENDPOINT

        cp_key = id(checkpointer) if checkpointer else "none"
        cache_key = f"{agent_id}:{endpoint}:{verbose}:{cp_key}"

        if cache_key not in self._graphs:
            agent_def = self.get_agent(agent_id)
            if agent_def is None:
                logger.error(f"Agent not found: {agent_id}")
                return None

            from framework.graph.agent_graph import create_agent_graph
            graph = create_agent_graph(agent_def, endpoint, verbose, checkpointer=checkpointer)
            self._graphs[cache_key] = graph

        return self._graphs[cache_key]

    def register_agent(self, config: Dict[str, Any], agent_dir) -> AgentDefinition:
        """
        Register a new agent without re-scanning the filesystem.

        Args:
            config: Validated agent.json dict
            agent_dir: Path to the agent directory

        Returns:
            The created AgentDefinition
        """
        agent_def = AgentDefinition(config, Path(agent_dir))
        self._agents[agent_def.id] = agent_def

        # Clear any cached graphs for this agent
        stale_keys = [k for k in self._graphs if k.startswith(f"{agent_def.id}:")]
        for k in stale_keys:
            del self._graphs[k]

        logger.info(f"Registered agent: '{agent_def.name}' (id={agent_def.id})")
        return agent_def

    def unregister_agent(self, agent_id: str) -> bool:
        """
        Remove an agent from the registry (does not delete files).

        Args:
            agent_id: ID of the agent to remove

        Returns:
            True if found and removed, False if not found
        """
        if agent_id not in self._agents:
            return False

        del self._agents[agent_id]

        # Clear cached graphs
        stale_keys = [k for k in self._graphs if k.startswith(f"{agent_id}:")]
        for k in stale_keys:
            del self._graphs[k]

        logger.info(f"Unregistered agent: {agent_id}")
        return True

    @property
    def agent_count(self) -> int:
        return len(self._agents)

    @property
    def agent_ids(self) -> List[str]:
        return list(self._agents.keys())


# Global registry instance
_global_registry: Optional[AgentRegistry] = None


def get_registry(agents_dir: str = None) -> AgentRegistry:
    """Get or create the global agent registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = AgentRegistry(agents_dir)
        _global_registry.discover()
    return _global_registry
