# Profile Collector Agent

A simple example agent that demonstrates all framework features by collecting user profile information through a friendly conversation.

## Fields

| Field | Type | Required | Validator |
|-------|------|----------|-----------|
| full_name | string | Yes | name |
| email | string | Yes | email |
| phone | string | Yes | phone |
| age | number | No | number (13-120) |
| interests | text | No | - |

## Conversation Flow

1. Greeting: "Hi! I'd like to help set up your profile."
2. Collect required fields in order (name, email, phone)
3. Offer optional fields (age, interests) - user can skip
4. Show confirmation summary
5. Complete with personalized message

## What This Demonstrates

- **Required vs optional fields**: First 3 are required, last 2 optional
- **Multiple validators**: name, email, phone, number with min/max
- **Skip detection**: Users can say "skip" for optional fields
- **Confirmation flow**: Summary + approve/modify cycle
- **Completion template**: Uses `{full_name}` and `{email}` placeholders
- **Dual-path extraction**: Regex fast-path for emails/phones, LLM for complex inputs
