# Application Google Sheet Tracker

## Project Overview
Python-based GitHub Action that runs daily, scans Gmail for job application confirmation emails, parses them with Claude API, and logs them to a Google Sheet.

## Commands
- Run locally: `python -m src.main`
- Dry run: `python -m src.main --dry-run`
- Install deps: `pip install -r requirements.txt`
- Gmail setup: `python scripts/setup_gmail_oauth.py`

## Architecture
- `src/gmail_client.py` — Gmail API client (OAuth2 refresh token)
- `src/email_parser.py` — Claude API email parsing
- `src/sheets_client.py` — Google Sheets API client (Service Account)
- `src/main.py` — Orchestrator

## Conventions
- Python 3.11+
- Dataclasses for data models
- All secrets via environment variables (never hardcoded)
- Google Sheets auth: Service Account (base64-encoded JSON in env var)
- Gmail auth: OAuth2 refresh token
