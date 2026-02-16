"""
Intent Detection Node

Uses LLM to detect user intent: question, agent_task, or response.
This enables mid-conversation Q&A mode where users can ask questions
without losing their progress.
"""

import logging
import httpx

from framework.state.agent_state import AgentState
from framework.config.constants import LLM_TIMEOUT_CLASSIFICATION

logger = logging.getLogger(__name__)

LLM_TIMEOUT = LLM_TIMEOUT_CLASSIFICATION


def intent_detection_node(
    state: AgentState,
    endpoint: str = "http://localhost:8000",
    verbose: bool = False,
) -> AgentState:
    """
    Detect whether user is asking a question, starting a task, or responding.

    Intents:
    - 'question': User is asking an informational question
    - 'agent_task': User wants to start or continue the agent's task
    - 'response': User is responding to a previous question

    Args:
        state: Current AgentState
        endpoint: LLM service endpoint
        verbose: Enable verbose logging

    Returns:
        AgentState: Updated with detected_intent and Q&A mode flags
    """
    user_message = state.get("last_user_message", "").strip()
    if not user_message:
        return state

    agent_name = state.get("agent_name", "assistant")
    has_agent = bool(state.get("agent_id"))

    prompt = f"""Classify the user's intent into exactly one category.

Categories:
- "question": User is asking an informational question (e.g., "What do you do?", "How does this work?")
- "agent_task": User wants to start or continue a task (e.g., providing information, requesting action)
- "response": User is responding to a previous question with information

Context: The user is interacting with a {agent_name}. {"A task is already in progress." if has_agent else "No task has started yet."}

User message: "{user_message}"

Respond with ONLY one word: question, agent_task, or response"""

    detected_intent = "agent_task"  # Default

    try:
        response = httpx.post(
            f"{endpoint}/generate",
            json={
                "prompt": prompt,
                "max_tokens": 10,
                "temperature": 0.1,
            },
            timeout=LLM_TIMEOUT,
        )
        response.raise_for_status()

        result = response.json().get("text", "").strip().lower()

        if "question" in result:
            detected_intent = "question"
        elif "response" in result:
            detected_intent = "response"
        else:
            detected_intent = "agent_task"

    except Exception as e:
        logger.error(f"INTENT | Detection error: {e}")

    if verbose:
        logger.info(f"INTENT | Message: '{user_message}' -> {detected_intent}")

    # Set Q&A mode flags
    should_enter_qa = detected_intent == "question"

    return {
        **state,
        "detected_intent": detected_intent,
        "should_enter_qa_mode": should_enter_qa,
        "has_task_info_in_qa": False,
    }
