"""
Generic Prompt Templates

Templates for generating natural language in agent conversations.
All templates use agent.json persona and field metadata.
"""


def ask_field(field_name: str, question: str, persona: str = "", voice_mode: bool = False) -> str:
    """Generate a prompt to ask for a specific field.

    Args:
        field_name: Name of the field being asked about.
        question: The question text to present.
        persona: Reserved for future persona-based phrasing customization.
        voice_mode: Reserved for future voice-specific phrasing adjustments.
    """
    return question


def acknowledge_and_ask(
    extracted: dict,
    next_question: str,
    persona: str = "",
    voice_mode: bool = False,
) -> str:
    """Generate acknowledgment of extracted fields + next question."""
    if not extracted:
        return next_question

    if len(extracted) == 1:
        ack = "Got it, thanks!"
    else:
        ack = "Great, I've noted that down."

    if voice_mode:
        return f"{ack} {next_question}"
    return f"{ack}\n\n{next_question}"


def confirmation_summary(collected: dict, field_defs: list) -> str:
    """Generate a confirmation summary of all collected fields."""
    lines = ["Here's a summary of the information you've provided:\n"]

    for field in field_defs:
        name = field["name"]
        if name in collected and collected[name] is not None:
            display = field.get("description", name).title()
            value = collected[name]
            if isinstance(value, bool):
                value = "Yes" if value else "No"
            lines.append(f"  - **{display}**: {value}")

    lines.append("\nDoes everything look correct? (yes to confirm, or tell me what to change)")
    return "\n".join(lines)


def completion_message(template: str, collected: dict) -> str:
    """Format the completion message with collected field values."""
    try:
        return template.format(**collected)
    except KeyError:
        return template


def validation_error(field_name: str, error: str, question: str) -> str:
    """Generate a message for a validation error."""
    return f"I'm sorry, that doesn't seem right: {error}. {question}"
