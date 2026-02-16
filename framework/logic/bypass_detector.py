"""
Bypass Intent Detection

Detects when users want to skip/bypass optional fields in conversational flow.
Uses a two-tier approach:
1. Fast regex patterns for common bypass phrases (~0.01ms)
2. LLM fallback for ambiguous cases (~2s)
"""

import re
import logging
import requests
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


# Tier 1: Fast regex patterns for common bypass phrases
BYPASS_PATTERNS = [
    # Direct skip/pass
    r'\b(skip|pass)\b',
    r'\bno\s+thanks?\b',
    r'\bthat\'?s\s+(all|it|everything)\b',

    # Simple negatives (more flexible - no $ anchor to avoid whitespace issues)
    r'^\s*(no|nope|nah)\s*$',  # Standalone "no" with flexible whitespace
    r'^\s*no\s*$',  # Extra pattern for just "no"
    r'\bnot?\s+needed\b',
    r'\bdon\'?t\s+have\s+(any|one|it)\b',
    r'\bI\s+don\'?t\s+have\b',
    r'\bnothing\b',

    # "I don't want" variations (CRITICAL - user reported these failed)
    r'\bI\s+do\s+not\s+want\b',
    r'\bI\s+don\'?t\s+want\b',
    r'\bdo\s+not\s+want\b',
    r'\bdon\'?t\s+want\b',
    r'\bnot\s+interested\b',
    r'\bI\s+would\s+rather\s+not\b',
    r'\bI\'?d\s+rather\s+not\b',

    # Completion indicators
    r'\bwe\'?re\s+done\b',
    r'\bthat\'?s\s+enough\b',
    r'\bno\s+comments?\b',
    r'\bno\s+special\s+requests?\b',

    # Polite declines
    r'\bI\'?m\s+(good|fine|okay|ok)\b',
    r'\bnone\s+needed\b',
    r'\bnot\s+necessary\b',

    # Continuation/completion indicators (high confidence)
    r'\blet\'?s\s+(proceed|continue|move\s+on|move\s+forward)\b',
    r'\bread+y\s+to\s+(proceed|continue|move\s+on)\b',
    r'\ball\s+set\b',
    r'\bgood\s+to\s+go\b',
    r'\bthat\s+covers\s+it\b',
    r'\bthat\s+should\s+(do\s+it|work)\b',
    r'\bmove\s+on\b',
    r'\bmove\s+forward\b',
    r'\bnext\s+(please|step|field)\b',  # "next" with context word to avoid "next week"
    r'\bwe\s+can\s+move\s+on\b',
    r'\bonward\b',
]

# Compile patterns for performance
COMPILED_BYPASS_PATTERNS = [re.compile(pattern, re.IGNORECASE) for pattern in BYPASS_PATTERNS]


def detect_bypass_intent_fast(user_message: str, verbose: bool = False) -> Optional[bool]:
    """
    Fast tier-1 bypass detection using regex patterns.

    Args:
        user_message: User's response text
        verbose: Enable verbose logging

    Returns:
        True if bypass detected with high confidence
        False if definitely NOT a bypass
        None if ambiguous (needs LLM)

    Performance: ~0.01ms
    """
    message_lower = user_message.lower().strip()

    if verbose:
        logger.info(f"BYPASS_FAST | Checking message: '{message_lower}' (len={len(message_lower)})")

    # Very short messages need special handling
    # BUT: "no" is a valid bypass, so check patterns first for 2-char messages
    if len(message_lower) < 2:
        # Single character responses likely not bypass
        if verbose:
            logger.info(f"BYPASS_FAST | Message too short (<2 chars) → NOT bypass")
        return False

    # Check positive bypass patterns
    for i, pattern in enumerate(COMPILED_BYPASS_PATTERNS):
        if pattern.search(message_lower):
            if verbose:
                logger.info(f"BYPASS_FAST | Pattern #{i} MATCHED: {BYPASS_PATTERNS[i]}")
                logger.info(f"BYPASS_FAST | → BYPASS detected (confidence=1.0)")
            return True

    # Check if message looks like actual content (longer, specific)
    # If it's more than a few words and doesn't match bypass patterns, it's likely content
    word_count = len(message_lower.split())
    if word_count > 5:
        # Long message without bypass keywords = likely providing content
        if verbose:
            logger.info(f"BYPASS_FAST | Message is long ({word_count} words) with no bypass patterns → PROVIDE")
        return False

    # Short message without clear bypass or content indicators = ambiguous
    # Let LLM decide
    if verbose:
        logger.info(f"BYPASS_FAST | Message is ambiguous ({word_count} words, no clear patterns) → LLM needed")
    return None


def detect_bypass_intent_llm(
    user_message: str,
    field_name: str,
    endpoint: str = "http://localhost:8000",
    verbose: bool = False
) -> Tuple[bool, float]:
    """
    Tier-2 bypass detection using LLM for ambiguous cases.

    Args:
        user_message: User's response text
        field_name: Name of the optional field being asked about
        endpoint: LLM service endpoint
        verbose: Enable verbose logging

    Returns:
        (is_bypass: bool, confidence: float)

    Performance: ~2s
    """
    # Format field name for display
    field_display = field_name.replace("_", " ").title()

    prompt = f"""You are analyzing whether a user wants to SKIP/BYPASS providing optional information in a conversation.

Context: The bot asked "Would you like to provide {field_display}? (Optional - you can skip this if not needed)"
User's response: "{user_message}"

Classify the user's intent as either:
- BYPASS: User wants to skip this optional field and move to the next step
- PROVIDE: User is providing information or wants to provide information

Examples of BYPASS (user wants to skip and move on):
- "no"
- "skip"
- "I'm good"
- "that's all"
- "nope"
- "no thanks"
- "not needed"
- "let's proceed"
- "ready to proceed"
- "continue"
- "move on"
- "next"
- "all set"
- "good to go"
- "that covers it"

Examples of PROVIDE (user giving info or wants to give info):
- "yes" (wants to provide)
- "tomorrow" (providing actual content)
- "I have a child seat" (providing specific requirement)
- "can you explain what that means?" (asking for clarification before providing)
- "let me think about it" (will provide later)

IMPORTANT: Phrases like "proceed", "continue", "move on", "next" indicate the user is DONE and wants to BYPASS this field to move forward.

Answer with ONLY one word: BYPASS or PROVIDE"""

    try:
        response = requests.post(
            f"{endpoint}/generate",
            json={
                "prompt": prompt,
                "max_tokens": 10,
                "temperature": 0.1,
                "stop": ["\n", ".", ","]
            },
            timeout=10
        )

        if response.status_code == 200:
            result = response.json()
            generated_text = result.get("generated_text", "").strip().upper()

            if verbose:
                logger.info(f"BYPASS_DETECTOR | LLM response: '{generated_text}'")

            # Parse response
            if "BYPASS" in generated_text:
                return (True, 0.9)
            elif "PROVIDE" in generated_text:
                return (False, 0.9)
            else:
                # Unclear response from LLM - default to NOT bypass (safer)
                if verbose:
                    logger.warning(f"BYPASS_DETECTOR | Unclear LLM response: '{generated_text}', defaulting to PROVIDE")
                return (False, 0.5)
        else:
            logger.error(f"BYPASS_DETECTOR | LLM service error: {response.status_code}")
            # Default to NOT bypass when LLM fails
            return (False, 0.3)

    except Exception as e:
        logger.error(f"BYPASS_DETECTOR | LLM request failed: {e}")
        # Default to NOT bypass when LLM fails (safer - won't lose user's input)
        return (False, 0.3)


def detect_bypass_intent(
    user_message: str,
    field_name: str,
    endpoint: str = "http://localhost:8000",
    verbose: bool = False
) -> Tuple[bool, float]:
    """
    Detect if user wants to bypass/skip an optional field.

    Uses two-tier approach:
    1. Fast regex patterns (~0.01ms)
    2. LLM fallback for ambiguous cases (~2s)

    Args:
        user_message: User's response text
        field_name: Name of the optional field being asked about
        endpoint: LLM service endpoint
        verbose: Enable verbose logging

    Returns:
        (is_bypass: bool, confidence: float)

    Examples:
        >>> detect_bypass_intent("skip", "comments")
        (True, 1.0)

        >>> detect_bypass_intent("no thanks", "do_date")
        (True, 1.0)

        >>> detect_bypass_intent("tomorrow at 3pm", "do_date")
        (False, 0.95)

        >>> detect_bypass_intent("I'm good", "comments")
        (True, 0.9)  # LLM fallback
    """
    if verbose:
        logger.info(f"BYPASS_DETECTOR | Checking: '{user_message}' for field: {field_name}")

    # Tier 1: Fast regex detection
    fast_result = detect_bypass_intent_fast(user_message, verbose=verbose)

    if fast_result is True:
        # High-confidence bypass
        if verbose:
            logger.info(f"BYPASS_DETECTOR | Fast detection: BYPASS (confidence=1.0)")
        return (True, 1.0)

    elif fast_result is False:
        # High-confidence NOT bypass (user providing content)
        if verbose:
            logger.info(f"BYPASS_DETECTOR | Fast detection: PROVIDE (confidence=0.95)")
        return (False, 0.95)

    else:
        # Ambiguous - use LLM
        if verbose:
            logger.info(f"BYPASS_DETECTOR | Fast detection: AMBIGUOUS, using LLM...")
        return detect_bypass_intent_llm(user_message, field_name, endpoint, verbose)


if __name__ == "__main__":
    # Test bypass detection
    print("=== Bypass Detection Tests ===\n")

    test_cases = [
        # Clear bypass cases (should use fast detection)
        ("skip", "comments", True),
        ("no thanks", "do_date", True),
        ("that's all", "do_hour", True),
        ("nope", "comments", True),
        ("nothing", "comments", True),
        ("I don't have any", "comments", True),

        # Clear provide cases (should use fast detection)
        ("tomorrow at 3pm", "do_date", False),
        ("I need pickup at 5:30 AM please", "pu_hour", False),
        ("Please make sure the car is clean", "comments", False),

        # Ambiguous cases (will use LLM fallback)
        ("I'm good", "comments", True),  # Common ambiguous bypass
        ("ok", "comments", None),  # Could go either way
        ("fine", "do_date", None),  # Could go either way
    ]

    for message, field, expected in test_cases:
        is_bypass, confidence = detect_bypass_intent(message, field, verbose=True)
        status = "PASS" if (expected is None or is_bypass == expected) else "FAIL"
        print(f"{status} '{message}' -> {'BYPASS' if is_bypass else 'PROVIDE'} (conf: {confidence:.2f})")
        print()
