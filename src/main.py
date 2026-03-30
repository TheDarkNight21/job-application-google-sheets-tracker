"""Orchestrator: fetch emails, parse applications, update Google Sheet."""

import argparse
import sys

from dotenv import load_dotenv

from src.gmail_client import fetch_recent_emails
from src.email_parser import parse_emails
from src.sheets_client import run_sheets_update


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Track job applications from Gmail to Google Sheets")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be added without writing to the sheet")
    parser.add_argument("--hours", type=int, default=24, help="How many hours back to scan (default: 24)")
    args = parser.parse_args()

    # Step 1: Fetch recent emails
    print(f"Fetching emails from the last {args.hours} hours...")
    emails = fetch_recent_emails(hours=args.hours)
    print(f"  Found {len(emails)} emails in inbox")

    if not emails:
        print("\nNo emails to process. Done.")
        return

    # Step 2: Parse for application confirmations
    print("Parsing emails for application confirmations...")
    applications = parse_emails(emails)
    print(f"  Identified {len(applications)} application confirmation(s)")

    if not applications:
        print("\nNo new applications found. Done.")
        return

    # Step 3: Dry run or update sheet
    if args.dry_run:
        print("\n=== DRY RUN — would add these applications ===")
        for app in applications:
            print(f"  - {app.position} @ {app.company} ({app.date_applied})")
        print("\nNo changes made (dry run).")
        return

    print("Updating Google Sheet...")
    added, skipped, stats = run_sheets_update(applications)

    # Step 4: Print summary
    print(f"\n{'=' * 40}")
    print("=== Application Tracker Summary ===")
    print(f"{'=' * 40}")
    print(f"Emails scanned: {len(emails)}")
    print(f"New applications found: {added}")

    if added > 0:
        new_apps = applications[:added] if skipped == 0 else [a for a in applications]
        for app in new_apps:
            print(f"  - {app.position} @ {app.company} ({app.date_applied})")

    print(f"Duplicates skipped: {skipped}")
    print(f"Total applications tracked: {stats['total']}")

    if stats.get("statuses"):
        print(f"\nStatus breakdown:")
        for status, count in stats["statuses"].items():
            print(f"  {status}: {count}")


if __name__ == "__main__":
    main()
