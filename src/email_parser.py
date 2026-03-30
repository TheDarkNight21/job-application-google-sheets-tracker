"""Parse job application confirmation emails using Claude API."""

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime

import anthropic

from src.gmail_client import Email


@dataclass
class Application:
    company: str
    position: str
    date_applied: str
    email_subject: str
    source_email_date: str
    message_id: str


SYSTEM_PROMPT = """You are an email classifier that identifies job application confirmation emails.

Given an email, determine if it is a job application confirmation (e.g., "thanks for applying",
"we received your application", "application submitted successfully", etc.).

Do NOT classify these as application confirmations:
- Rejection emails
- Interview invitations
- Job alerts or recommendations
- Newsletters
- Promotional emails
- Password reset or account creation emails

Respond with a JSON object. If it IS an application confirmation:
{
    "is_application": true,
    "company": "Company Name",
    "position": "Job Title or 'Unknown' if not mentioned"
}

If it is NOT an application confirmation:
{
    "is_application": false
}

Respond ONLY with the JSON object, no other text."""


def parse_emails(emails: list[Email]) -> list[Application]:
    """Parse a list of emails and return identified job applications."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    applications = []

    for email in emails:
        user_message = f"From: {email.sender}\nSubject: {email.subject}\nDate: {email.date.isoformat()}\n\nBody:\n{email.body}"

        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=256,
                system=SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": "{"},
                ],
            )

            result_text = "{" + response.content[0].text.strip()

            # Strip markdown code fences if present (e.g., ```json ... ```)
            fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", result_text, re.DOTALL)
            if fence_match:
                result_text = fence_match.group(1)

            result = json.loads(result_text)

            if result.get("is_application"):
                applications.append(
                    Application(
                        company=result.get("company", "Unknown"),
                        position=result.get("position", "Unknown"),
                        date_applied=email.date.strftime("%Y-%m-%d"),
                        email_subject=email.subject,
                        source_email_date=email.date.isoformat(),
                        message_id=email.message_id,
                    )
                )
        except (json.JSONDecodeError, anthropic.APIError, KeyError, IndexError) as e:
            print(f"  Warning: Failed to parse email '{email.subject}': {e}")
            continue

    return applications
