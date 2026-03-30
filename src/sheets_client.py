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

# Stats are written starting at column I (column index 8, 0-based)
STATS_COL = "I"
STATS_COL_INDEX = 8  # 0-based column index for I
STATS_START_ROW = 1

# --- Colors (RGB 0-1 float) ---
# Dark green for header row (A1:G1)
HEADER_GREEN = {"red": 0.22, "green": 0.46, "blue": 0.11}
# Lighter green for "Applied" status cells
STATUS_GREEN = {"red": 0.42, "green": 0.66, "blue": 0.31}
# Orange for stats section headers
STATS_ORANGE = {"red": 0.90, "green": 0.57, "blue": 0.22}
# White text
WHITE = {"red": 1.0, "green": 1.0, "blue": 1.0}
# Black text
BLACK = {"red": 0.0, "green": 0.0, "blue": 0.0}


def _build_service():
    """Build Google Sheets API service from base64-encoded service account credentials."""
    creds_b64 = os.environ["GOOGLE_SHEETS_CREDENTIALS"]
    creds_json = json.loads(base64.b64decode(creds_b64))
    credentials = Credentials.from_service_account_info(creds_json, scopes=SCOPES)
    return build("sheets", "v4", credentials=credentials)


def _get_sheet_id() -> str:
    return os.environ["GOOGLE_SHEET_ID"]


def _get_sheet_gid(service, spreadsheet_id: str, sheet_name: str = "jobs") -> int:
    """Get the internal sheet GID (sheetId) for batchUpdate requests."""
    spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for sheet in spreadsheet.get("sheets", []):
        if sheet["properties"]["title"] == sheet_name:
            return sheet["properties"]["sheetId"]
    return 0  # Default to first sheet


def _make_cell_format(bg_color=None, text_color=None, bold=False, h_align=None):
    """Build a CellFormat dict for batchUpdate."""
    fmt = {}
    if bg_color:
        fmt["backgroundColor"] = bg_color
    text_fmt = {}
    if text_color:
        text_fmt["foregroundColor"] = text_color
    if bold:
        text_fmt["bold"] = True
    if text_fmt:
        fmt["textFormat"] = text_fmt
    if h_align:
        fmt["horizontalAlignment"] = h_align
    return fmt


def _repeat_cell_request(sheet_gid, start_row, end_row, start_col, end_col, cell_format):
    """Build a repeatCell request for batchUpdate."""
    fields = []
    if "backgroundColor" in cell_format:
        fields.append("userEnteredFormat.backgroundColor")
    if "textFormat" in cell_format:
        tf = cell_format["textFormat"]
        if "foregroundColor" in tf:
            fields.append("userEnteredFormat.textFormat.foregroundColor")
        if "bold" in tf:
            fields.append("userEnteredFormat.textFormat.bold")
    if "horizontalAlignment" in cell_format:
        fields.append("userEnteredFormat.horizontalAlignment")

    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_gid,
                "startRowIndex": start_row,
                "endRowIndex": end_row,
                "startColumnIndex": start_col,
                "endColumnIndex": end_col,
            },
            "cell": {"userEnteredFormat": cell_format},
            "fields": ",".join(fields),
        }
    }


def _merge_cell_request(sheet_gid, start_row, end_row, start_col, end_col):
    """Build a mergeCells request."""
    return {
        "mergeCells": {
            "range": {
                "sheetId": sheet_gid,
                "startRowIndex": start_row,
                "endRowIndex": end_row,
                "startColumnIndex": start_col,
                "endColumnIndex": end_col,
            },
            "mergeType": "MERGE_ALL",
        }
    }


def _data_validation_dropdown(sheet_gid, start_row, end_row, col, values):
    """Build a setDataValidation request for a dropdown."""
    return {
        "setDataValidation": {
            "range": {
                "sheetId": sheet_gid,
                "startRowIndex": start_row,
                "endRowIndex": end_row,
                "startColumnIndex": col,
                "endColumnIndex": col + 1,
            },
            "rule": {
                "condition": {
                    "type": "ONE_OF_LIST",
                    "values": [{"userEnteredValue": v} for v in values],
                },
                "showCustomUi": True,
                "strict": False,
            },
        }
    }


def ensure_headers(service, sheet_id: str) -> None:
    """Ensure the first row has the correct headers."""
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id, range="jobs!A1:G1"
    ).execute()

    existing = result.get("values", [[]])[0]
    if existing != HEADERS:
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range="jobs!A1:G1",
            valueInputOption="RAW",
            body={"values": [HEADERS]},
        ).execute()


def get_existing_message_ids(service, sheet_id: str) -> set[str]:
    """Read all Message ID values (column G) to detect duplicates."""
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id, range="jobs!G2:G"
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
        range="jobs!A:G",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()

    return len(rows)


def update_stats(service, sheet_id: str) -> dict:
    """Calculate and write summary statistics. Returns stats dict."""
    # Read all data rows
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id, range="jobs!A2:G"
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
            # Support both M/DD/YYYY and YYYY-MM-DD formats
            for fmt in ("%m/%d/%Y", "%-m/%-d/%Y", "%Y-%m-%d"):
                try:
                    applied_date = datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    continue
            else:
                continue
            if applied_date >= week_ago:
                this_week += 1
            if applied_date >= month_ago:
                this_month += 1
        except (ValueError, TypeError):
            pass

    # Build stats block matching the Google Sheet layout
    top_companies = companies.most_common(5)
    stats_values = [
        ["STATS", ""],
        ["Total Applications", str(total)],
        ["This Week", str(this_week)],
        ["This Month", str(this_month)],
        ["", ""],
        ["STATS BREAKDOWN", ""],
    ]

    for status, count in statuses.most_common():
        stats_values.append([status, str(count)])

    stats_values.append(["", ""])
    stats_values.append(["TOP COMPANIES", ""])

    for company, count in top_companies:
        stats_values.append([company, str(count)])

    # Write stats to columns I-J
    end_row = STATS_START_ROW + len(stats_values) - 1
    stats_range = f"jobs!{STATS_COL}{STATS_START_ROW}:J{end_row}"

    # Clear old stats first
    service.spreadsheets().values().clear(
        spreadsheetId=sheet_id, range=f"jobs!{STATS_COL}:{chr(ord(STATS_COL) + 1)}"
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
        "stats_values": stats_values,
    }


def apply_formatting(service, spreadsheet_id: str, total_data_rows: int, stats_values: list) -> None:
    """Apply all cell formatting: colors, bold, alignment, dropdowns, merges."""
    sheet_gid = _get_sheet_gid(service, spreadsheet_id, "jobs")
    requests = []

    # ========================================
    # 1. HEADER ROW (A1:G1) — dark green bg, white bold text, centered
    # ========================================
    header_fmt = _make_cell_format(
        bg_color=HEADER_GREEN, text_color=WHITE, bold=True, h_align="CENTER"
    )
    requests.append(_repeat_cell_request(sheet_gid, 0, 1, 0, 7, header_fmt))

    # ========================================
    # 2. STATUS COLUMN (D2:D{last_row}) — green bg, white bold text, centered + dropdown
    # ========================================
    if total_data_rows > 0:
        last_data_row = 1 + total_data_rows  # 0-based: row 1 = index 1
        status_fmt = _make_cell_format(
            bg_color=STATUS_GREEN, text_color=WHITE, bold=True, h_align="CENTER"
        )
        requests.append(_repeat_cell_request(sheet_gid, 1, last_data_row, 3, 4, status_fmt))

        # Add dropdown validation for Status column
        status_options = ["Applied", "Interview", "Offer", "Rejected", "Withdrawn"]
        requests.append(_data_validation_dropdown(
            sheet_gid, 1, last_data_row, 3, status_options
        ))

    # ========================================
    # 3. STATS SECTION (columns I-J) formatting
    # ========================================
    # Find which rows are section headers (STATS, STATS BREAKDOWN, TOP COMPANIES)
    section_header_labels = {"STATS", "STATS BREAKDOWN", "TOP COMPANIES"}

    for i, row_vals in enumerate(stats_values):
        sheet_row = i  # 0-based row index (stats start at row 1 = index 0)
        label = row_vals[0] if row_vals else ""

        if label in section_header_labels:
            # Orange bg, white bold text, centered — merge I and J
            section_fmt = _make_cell_format(
                bg_color=STATS_ORANGE, text_color=WHITE, bold=True, h_align="CENTER"
            )
            requests.append(_repeat_cell_request(
                sheet_gid, sheet_row, sheet_row + 1, STATS_COL_INDEX, STATS_COL_INDEX + 2, section_fmt
            ))
            # Merge the two cells
            requests.append(_merge_cell_request(
                sheet_gid, sheet_row, sheet_row + 1, STATS_COL_INDEX, STATS_COL_INDEX + 2
            ))
        elif label:
            # Data row — label left-aligned, value bold + centered
            label_fmt = _make_cell_format(bold=False, h_align="LEFT")
            requests.append(_repeat_cell_request(
                sheet_gid, sheet_row, sheet_row + 1, STATS_COL_INDEX, STATS_COL_INDEX + 1, label_fmt
            ))

            value_fmt = _make_cell_format(bold=True, h_align="CENTER")
            requests.append(_repeat_cell_request(
                sheet_gid, sheet_row, sheet_row + 1, STATS_COL_INDEX + 1, STATS_COL_INDEX + 2, value_fmt
            ))

    # ========================================
    # 4. Execute all formatting
    # ========================================
    if requests:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests},
        ).execute()


def run_sheets_update(new_apps: list[Application]) -> tuple[int, int, dict]:
    """
    Full sheets update: ensure headers, dedup, append, update stats, apply formatting.
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

    # Apply formatting to match the expected sheet style
    total_data_rows = stats["total"]
    apply_formatting(service, sheet_id, total_data_rows, stats["stats_values"])

    return added, skipped, stats
