"""Gmail API client for fetching recent emails."""

import base64
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


@dataclass
class Email:
    message_id: str
    sender: str
    subject: str
    body: str
    date: datetime


def _build_credentials() -> Credentials:
    """Build Gmail credentials from environment variables."""
    credentials = Credentials(
        token=None,
        refresh_token=os.environ["GMAIL_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["GMAIL_CLIENT_ID"],
        client_secret=os.environ["GMAIL_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
    )
    credentials.refresh(Request())
    return credentials


def _extract_body(payload: dict) -> str:
    """Extract plain text body from a Gmail message payload."""
    # Simple message with body directly
    if payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

    # Multipart message — look for text/plain first, then text/html
    parts = payload.get("parts", [])
    text_part = None
    html_part = None

    for part in parts:
        mime_type = part.get("mimeType", "")
        if mime_type == "text/plain" and part.get("body", {}).get("data"):
            text_part = part
        elif mime_type == "text/html" and part.get("body", {}).get("data"):
            html_part = part
        elif mime_type.startswith("multipart/"):
            # Recurse into nested multipart
            nested = _extract_body(part)
            if nested:
                return nested

    chosen = text_part or html_part
    if chosen and chosen.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(chosen["body"]["data"]).decode("utf-8", errors="replace")

    return ""


def _parse_headers(headers: list[dict]) -> dict[str, str]:
    """Extract useful headers into a dict."""
    result = {}
    for header in headers:
        name = header.get("name", "").lower()
        if name in ("from", "subject", "date", "message-id"):
            result[name] = header.get("value", "")
    return result


def fetch_recent_emails(hours: int = 24) -> list[Email]:
    """Fetch emails from the inbox within the last `hours` hours."""
    credentials = _build_credentials()
    service = build("gmail", "v1", credentials=credentials)

    after_date = datetime.now(timezone.utc) - timedelta(hours=hours)
    query = f"in:inbox after:{after_date.strftime('%Y/%m/%d')}"

    emails = []
    page_token = None

    while True:
        response = (
            service.users()
            .messages()
            .list(userId="me", q=query, pageToken=page_token)
            .execute()
        )

        messages = response.get("messages", [])
        if not messages:
            break

        for msg_ref in messages:
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=msg_ref["id"], format="full")
                .execute()
            )

            headers = _parse_headers(msg.get("payload", {}).get("headers", []))
            body = _extract_body(msg.get("payload", {}))

            # Parse email date
            date = datetime.now(timezone.utc)
            if "date" in headers:
                try:
                    date = parsedate_to_datetime(headers["date"])
                except (ValueError, TypeError):
                    pass

            emails.append(
                Email(
                    message_id=headers.get("message-id", msg_ref["id"]),
                    sender=headers.get("from", ""),
                    subject=headers.get("subject", ""),
                    body=body[:5000],  # Truncate to avoid huge payloads
                    date=date,
                )
            )

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return emails
