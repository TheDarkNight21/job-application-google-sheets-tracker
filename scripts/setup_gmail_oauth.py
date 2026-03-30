"""
One-time local script to obtain a Gmail OAuth2 refresh token.

Usage:
    1. Go to Google Cloud Console → APIs & Services → Credentials
    2. Create an OAuth 2.0 Client ID (Desktop App type)
    3. Download the client secret JSON, or note the Client ID and Client Secret
    4. Run this script: python scripts/setup_gmail_oauth.py
    5. Follow the prompts — a browser window will open for authorization
    6. Copy the printed values into your GitHub repository secrets
"""

import json
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def main():
    print("=== Gmail OAuth2 Setup ===\n")
    print("You need a Google Cloud OAuth 2.0 Client ID (Desktop App type).")
    print("Get one at: https://console.cloud.google.com/apis/credentials\n")

    choice = input("Do you have a client_secret.json file? (y/n): ").strip().lower()

    if choice == "y":
        path = input("Enter path to client_secret.json: ").strip()
        try:
            flow = InstalledAppFlow.from_client_secrets_file(path, SCOPES)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error reading file: {e}")
            sys.exit(1)
    else:
        client_id = input("Enter Client ID: ").strip()
        client_secret = input("Enter Client Secret: ").strip()

        if not client_id or not client_secret:
            print("Error: Client ID and Client Secret are required.")
            sys.exit(1)

        client_config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        }
        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)

    print("\nOpening browser for authorization...")
    print("(If the browser doesn't open, check the terminal for a URL)\n")

    credentials = flow.run_local_server(port=0)

    print("\n=== Success! Add these as GitHub repository secrets ===\n")
    print(f"GMAIL_CLIENT_ID={credentials.client_id}")
    print(f"GMAIL_CLIENT_SECRET={credentials.client_secret}")
    print(f"GMAIL_REFRESH_TOKEN={credentials.refresh_token}")
    print("\nDone! You can now close this terminal.")


if __name__ == "__main__":
    main()
