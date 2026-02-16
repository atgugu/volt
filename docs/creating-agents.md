# Creating Agents

## Agent Factory (Fastest Path)

Generate a complete agent from a natural language description:

```bash
curl -X POST http://localhost:10821/agents/create \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Create an agent that collects a bug report with title, severity, steps to reproduce, and expected behavior"}'
```

The factory:
1. Sends your prompt to the LLM with a meta-prompt containing the full agent schema
2. Parses and validates the generated JSON
3. Auto-assigns validators (e.g., fields named "email" get the email validator)
4. Writes `agent.json` to `agents/{agent_id}/`
5. Registers the agent immediately -- no restart needed

The response includes the generated configuration and the agent ID, ready for conversations.

> [!TIP]
> You can also manage agents via API: `GET /agents` to list, `GET /agents/{id}/export` to export, and `DELETE /agents/{id}` to remove.

## Manual Creation (Full Control)

### Directory Structure

```
agents/
└── my_agent/
    ├── __init__.py             # Required (can be empty)
    ├── agent.json              # Required: agent definition
    ├── custom_nodes.py         # Optional: custom processing logic
    └── custom_validators.py    # Optional: custom field validators
```

### agent.json Schema

```json
{
  "name": "string (required) - Display name",
  "id": "string (required) - Unique identifier (snake_case)",
  "description": "string (required) - What this agent does",
  "version": "string (optional) - Semantic version",
  "greeting": "string (optional) - First message to user",
  "persona": "string (optional) - LLM persona for responses",

  "fields": [
    {
      "name": "string (required) - Field identifier (snake_case)",
      "type": "string (required) - string|number|boolean|text|email|phone",
      "required": "boolean (default: true)",
      "order": "number (optional) - Collection order, lower = first",
      "description": "string (optional) - Human-readable description",
      "question": "string (required) - Question to ask the user",
      "validator": "string (optional) - Validator name: name|email|phone|number|text",
      "validator_config": "object (optional) - Validator parameters",
      "extraction_hints": "array (optional) - Keywords that help extraction",
      "condition": "string (optional) - Condition for activation: 'field == value'"
    }
  ],

  "completion": {
    "message": "string (optional) - Template with {field_name} placeholders",
    "action": "string (optional) - log|webhook:<url>|custom"
  }
}
```

> [!NOTE]
> The minimum required keys are `name`, `id`, `description`, and `fields`. Each field must have `name`, `type`, and `question`.

### Real-World Example

<details>
<summary>Full profile_collector/agent.json</summary>

```json
{
  "name": "User Profile Collection",
  "id": "profile_collector",
  "description": "Collects user profile information through a friendly conversation",
  "version": "1.0.0",
  "greeting": "Hi! I'd like to help set up your profile. What's your name?",
  "persona": "friendly and professional assistant",

  "fields": [
    {
      "name": "full_name",
      "type": "string",
      "required": true,
      "order": 0,
      "description": "User's full name",
      "question": "What is your full name?",
      "validator": "name",
      "extraction_hints": ["name", "called", "I'm", "I am"]
    },
    {
      "name": "email",
      "type": "string",
      "required": true,
      "order": 1,
      "description": "User's email address",
      "question": "What is your email address?",
      "validator": "email"
    },
    {
      "name": "phone",
      "type": "string",
      "required": true,
      "order": 2,
      "description": "User's phone number",
      "question": "What phone number should we use?",
      "validator": "phone"
    },
    {
      "name": "age",
      "type": "number",
      "required": false,
      "order": 3,
      "description": "User's age",
      "question": "How old are you? Feel free to skip this one if you prefer.",
      "validator": "number",
      "validator_config": {
        "min": 13,
        "max": 120
      }
    },
    {
      "name": "interests",
      "type": "text",
      "required": false,
      "order": 4,
      "description": "User's interests or hobbies",
      "question": "What are your main interests or hobbies?"
    }
  ],

  "completion": {
    "message": "Your profile has been created successfully, {full_name}! We'll send a confirmation to {email}.",
    "action": "log"
  }
}
```

</details>

This example demonstrates:
- 5 fields (3 required, 2 optional)
- Multiple validators (`name`, `email`, `phone`, `number`)
- Validator config with `min`/`max` constraints
- Extraction hints to improve LLM accuracy
- Completion template with field placeholders

## Field Types

| Type | Description | Regex Fast-Path |
|------|-------------|-----------------|
| `string` | General text | No |
| `number` | Integer value | Yes -- extracts digits |
| `boolean` | Yes/No | Yes -- matches yes/no patterns |
| `text` | Long-form text | No |
| `email` | Email address | Yes -- email pattern |
| `phone` | Phone number | Yes -- digit extraction |

> [!TIP]
> Fields with regex fast-path types are extracted in ~0.001s instead of ~2-3s via LLM. Use specific types when possible.

## Built-in Validators

| Name | Validates | Config Options |
|------|-----------|----------------|
| `name` | Person names (2-100 chars, no special chars) | -- |
| `email` | Email format | -- |
| `phone` | Phone digits (7-15 digits) | `min_digits`, `max_digits` |
| `number` | Numeric value | `min`, `max` |
| `text` | Text length | `min_length`, `max_length` |

## Conditional Fields

Fields can be activated based on other field values:

```json
{
  "name": "category",
  "type": "string",
  "required": true,
  "order": 0,
  "question": "Is this a bug report or a feature request?"
},
{
  "name": "severity",
  "type": "string",
  "required": true,
  "order": 1,
  "question": "How severe is the bug?",
  "condition": "category == bug"
},
{
  "name": "priority",
  "type": "string",
  "required": true,
  "order": 1,
  "question": "What priority is this feature?",
  "condition": "category == feature"
}
```

When `category` is "bug", the user sees `severity`. When "feature", they see `priority`. Both are skipped otherwise.

## Completion Actions

### Log (default)

```json
{"action": "log"}
```

Logs collected data to the console.

### Webhook

```json
{"action": "webhook:https://api.example.com/submit"}
```

POSTs collected data as JSON to the URL.

### Custom

```json
{"action": "custom"}
```

Calls `on_complete(collected_fields)` from your `custom_nodes.py`.

## Custom Nodes

For agents needing custom processing, create `custom_nodes.py`:

```python
# agents/my_agent/custom_nodes.py

def on_complete(collected_fields: dict) -> dict:
    """Called when all fields are collected and confirmed."""
    # Your custom logic here
    return {"status": "success", "data": collected_fields}
```

## Custom Validators

For domain-specific validation, create `custom_validators.py`:

```python
# agents/my_agent/custom_validators.py
from framework.logic.validators.base import BaseValidator

class ZipCodeValidator(BaseValidator):
    def validate(self, value, **kwargs):
        import re
        if re.match(r'^\d{5}(-\d{4})?$', str(value)):
            return True, None
        return False, "Please provide a valid ZIP code (e.g., 12345)."
```

Register it in `__init__.py`:

```python
from framework.logic.validators import register_validator
from .custom_validators import ZipCodeValidator
register_validator("zipcode", ZipCodeValidator())
```

## Testing Your Agent

After creating an agent (via factory or manually), test it with curl:

```bash
# 1. Verify the agent is registered
curl http://localhost:10821/agents | python -m json.tool

# 2. Start a conversation
curl -X POST http://localhost:10821/conversation/start \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "my_agent"}'

# 3. Send messages (use session_id from step 2)
curl -X POST http://localhost:10821/conversation/message \
  -H "Content-Type: application/json" \
  -d '{"session_id": "SESSION_ID", "message": "John Smith"}'

# 4. Check status and collected fields
curl http://localhost:10821/conversation/SESSION_ID/status

# 5. After completion, view the results
curl http://localhost:10821/completions/SESSION_ID
```

You can also test in the web UI at `http://localhost:10821` -- your agent appears in the dropdown immediately.

## Examples

See `agents/profile_collector/` for a complete working example with validators, extraction hints, and optional fields.
