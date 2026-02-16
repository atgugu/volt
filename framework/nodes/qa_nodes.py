"""
Q&A Mode Nodes

Handles mid-conversation Q&A where users can ask questions
without losing their field collection progress.

Nodes:
- save_graph_position: Save current state before entering Q&A
- question_answering: Answer the user's question using LLM
- continuation_detection: Detect if user wants to continue Q&A or resume task
- restore_graph_position: Restore state when exiting Q&A
"""

import logging
import httpx

from framework.state.agent_state import AgentState
from framework.config.constants import LLM_TIMEOUT_CLASSIFICATION

logger = logging.getLogger(__name__)

LLM_TIMEOUT = LLM_TIMEOUT_CLASSIFICATION


def save_graph_position_node(
    state: AgentState,
    verbose: bool = False,
) -> AgentState:
    """
    Save the current graph position before entering Q&A mode.

    This allows seamless return to the exact conversation point
    after the user finishes asking questions.
    """
    position = state.get("expected_field", "field_extraction")

    if verbose:
        logger.info(f"QA_SAVE | Saving position: {position}")

    return {
        **state,
        "qa_mode_active": True,
        "saved_graph_position": position,
        "should_enter_qa_mode": False,
    }


def question_answering_node(
    state: AgentState,
    endpoint: str = "http://localhost:8000",
    verbose: bool = False,
) -> AgentState:
    """
    Answer the user's question using the LLM.

    Generates a helpful response while maintaining conversation context.
    """
    user_message = state.get("last_user_message", "").strip()
    agent_name = state.get("agent_name", "assistant")
    qa_history = list(state.get("qa_conversation_history", []))

    prompt = f"""You are a helpful {agent_name}. Answer the user's question concisely and helpfully.

User question: "{user_message}"

Provide a clear, helpful answer. Keep it brief (2-3 sentences). After answering, let the user know they can ask more questions or continue with their task."""

    answer = "I'm not sure about that. Feel free to ask me something else or we can continue."

    try:
        response = httpx.post(
            f"{endpoint}/generate",
            json={
                "prompt": prompt,
                "max_tokens": 512,
                "temperature": 0.7,
            },
            timeout=LLM_TIMEOUT,
        )
        response.raise_for_status()
        answer = response.json().get("text", answer).strip()
    except Exception as e:
        logger.error(f"QA_ANSWER | Error: {e}")

    # Update Q&A history
    qa_history.append({"role": "user", "content": user_message})
    qa_history.append({"role": "assistant", "content": answer})

    if verbose:
        logger.info(f"QA_ANSWER | Q: {user_message}")
        logger.info(f"QA_ANSWER | A: {answer[:100]}...")

    return {
        **state,
        "last_bot_message": answer,
        "qa_conversation_history": qa_history,
        "qa_consecutive_questions": state.get("qa_consecutive_questions", 0) + 1,
    }


def continuation_detection_node(
    state: AgentState,
    endpoint: str = "http://localhost:8000",
    verbose: bool = False,
) -> AgentState:
    """
    Detect whether user wants to continue asking questions or resume their task.

    Intents:
    - 'ask_more': User has another question
    - 'continue_task': User wants to resume the agent task
    - 'provide_info': User is providing info related to the task
    """
    user_message = state.get("last_user_message", "").strip()
    agent_name = state.get("agent_name", "assistant")

    prompt = f"""The user has been asking questions to a {agent_name} and might want to continue or return to their task.

User message: "{user_message}"

Classify: Is the user asking another question (ask_more), wanting to continue their task (continue_task), or providing task-related information (provide_info)?

Reply with ONLY one: ask_more, continue_task, or provide_info"""

    continuation_intent = "ask_more"

    try:
        response = httpx.post(
            f"{endpoint}/generate",
            json={"prompt": prompt, "max_tokens": 10, "temperature": 0.1},
            timeout=LLM_TIMEOUT,
        )
        response.raise_for_status()
        result = response.json().get("text", "").strip().lower()

        if "continue" in result:
            continuation_intent = "continue_task"
        elif "provide" in result:
            continuation_intent = "provide_info"
        else:
            continuation_intent = "ask_more"

    except Exception as e:
        logger.error(f"QA_CONTINUE | Error: {e}")

    stay_in_qa = continuation_intent == "ask_more"
    exit_qa = continuation_intent in ["continue_task", "provide_info"]

    if verbose:
        logger.info(f"QA_CONTINUE | Intent: {continuation_intent}")

    return {
        **state,
        "continuation_intent": continuation_intent,
        "stay_in_qa_mode": stay_in_qa,
        "exit_qa_mode": exit_qa,
        "has_task_info_in_qa": continuation_intent == "provide_info",
    }


def restore_graph_position_node(
    state: AgentState,
    verbose: bool = False,
) -> AgentState:
    """
    Restore graph position when exiting Q&A mode.

    Clears Q&A state and returns to the saved position.
    """
    saved_position = state.get("saved_graph_position")

    if verbose:
        logger.info(f"QA_RESTORE | Restoring to: {saved_position}")

    return {
        **state,
        "qa_mode_active": False,
        "saved_graph_position": None,
        "should_enter_qa_mode": False,
        "exit_qa_mode": False,
        "stay_in_qa_mode": False,
        "qa_consecutive_questions": 0,
    }
