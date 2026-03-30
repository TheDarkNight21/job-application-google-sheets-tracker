"""Google Sheets client for reading/writing application data."""

import base64
import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from src.email_parser import Application

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Sheet layout: Row 1 = headers, data starts at row 2
HEADERS = ["Date Applied", "Company", "Position", "Status", "Email Subject", "Source Email Date", "Message ID"]

# Stats are written starting at column I (column 9)
STATS_COL = "I"
STATS_START_ROW = 1


def _build_service():
    """Build Google Sheets API service from base64-encoded service account credentials."""
    creds_b64 = os.environ["GOOGLE_SHEETS_CREDENTIALS"]
    creds_json = json.loads(base64.b64decode(creds_b64))
    credentials = Credentials.from_service_account_info(creds_json, scopes=SCOPES)
    return build("sheets", "v4", credentials=credentials)


def _get_sheet_id() -> str:
    return os.environ["GOOGLE_SHEET_ID"]


def ensure_headers(service, sheet_id: str) -> None:
    """Ensure the first row has the correct headers."""
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id, range="Sheet1!A1:G1"
    ).execute()

    existing = result.get("values", [[]])[0]
    if existing != HEADERS:
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range="Sheet1!A1:G1",
            valueInputOption="RAW",
            body={"values": [HEADERS]},
        ).execute()


def get_existing_message_ids(service, sheet_id: str) -> set[str]:
    """Read all Message ID values (column G) to detect duplicates."""
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id, range="Sheet1!G2:G"
    ).execute()

    rows = result.get("values", [])
    return {row[0] for row in rows if row}


def append_applications(service, sheet_id: str, apps: list[Application]) -> int:
    """Append new application rows. Returns count of rows added."""
    if not apps:
        return 0

    rows = []
    for app in apps:
        rows.append([
            app.date_applied,
            app.company,
            app.position,
            "Applied",  # Default status
            app.email_subject,
            app.source_email_date,
            app.message_id,
        ])

    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range="Sheet1!A:G",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()

    return len(rows)


def update_stats(service, sheet_id: str) -> dict:
    """Calculate and write summary statistics. Returns stats dict."""
    # Read all data rows
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id, range="Sheet1!A2:G"
    ).execute()
    rows = result.get("values", [])

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    total = len(rows)
    this_week = 0
    this_month = 0
    companies = Counter()
    statuses = Counter()

    for row in rows:
        if len(row) < 4:
            continue

        date_str = row[0]
        company = row[1]
        status = row[3]

        companies[company] += 1
        statuses[status] += 1

        try:
            applied_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if applied_date >= week_ago:
                this_week += 1
            if applied_date >= month_ago:
                this_month += 1
        except (ValueError, TypeError):
            pass

    # Build stats block
    top_companies = companies.most_common(5)
    stats_values = [
        ["=== Stats ===", ""],
        ["Total Applications", str(total)],
        ["This Week", str(this_week)],
        ["This Month", str(this_month)],
        ["", ""],
        ["=== Status Breakdown ===", ""],
    ]

    for status, count in statuses.most_common():
        stats_values.append([status, str(count)])

    stats_values.append(["", ""])
    stats_values.append(["=== Top Companies ===", ""])

    for company, count in top_companies:
        stats_values.append([company, str(count)])

    # Write stats to columns I-J
    end_row = STATS_START_ROW + len(stats_values) - 1
    stats_range = f"Sheet1!{STATS_COL}{STATS_START_ROW}:J{end_row}"

    # Clear old stats first
    service.spreadsheets().values().clear(
        spreadsheetId=sheet_id, range=f"Sheet1!{STATS_COL}:{chr(ord(STATS_COL) + 1)}"
    ).execute()

    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=stats_range,
        valueInputOption="RAW",
        body={"values": stats_values},
    ).execute()

    return {
        "total": total,
        "this_week": this_week,
        "this_month": this_month,
        "statuses": dict(statuses),
        "top_companies": top_companies,
    }


def run_sheets_update(new_apps: list[Application]) -> tuple[int, int, dict]:
    """
    Full sheets update: ensure headers, dedup, append, update stats.
    Returns (added_count, skipped_count, stats).
    """
    service = _build_service()
    sheet_id = _get_sheet_id()

    ensure_headers(service, sheet_id)

    existing_ids = get_existing_message_ids(service, sheet_id)
    unique_apps = [app for app in new_apps if app.message_id not in existing_ids]
    skipped = len(new_apps) - len(unique_apps)

    added = append_applications(service, sheet_id, unique_apps)
    stats = update_stats(service, sheet_id)

    return added, skipped, stats
