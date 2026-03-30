# Application Tracker: Gmail → Google Sheets

Automated job application tracker that runs daily via GitHub Actions. It scans your Gmail for application confirmation emails, extracts details using Claude AI, and logs everything to a Google Sheet.

```
Gmail Inbox → Claude AI Parser → Google Sheet
     ↑                                ↑
  (daily scan)                  (auto-updated stats)
```

## Features

- **Daily automated scans** via GitHub Actions (cron)
- **AI-powered parsing** — Claude identifies application confirmations and extracts company, position, and date
- **Duplicate detection** — won't add the same application twice
- **Live statistics** — total applications, weekly/monthly counts, status breakdown, top companies
- **Manual status tracking** — update the "Status" column yourself (Applied → Interview → Offer / Rejected)
- **Dry run mode** — preview what would be added without writing to the sheet
- **Fork-friendly** — set up your own tracker in minutes

## Quick Start

### 1. Fork this repository

Click "Fork" on GitHub to create your own copy.

### 2. Create a Google Cloud project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or use an existing one)
3. Enable these APIs:
   - [Gmail API](https://console.cloud.google.com/apis/library/gmail.googleapis.com)
   - [Google Sheets API](https://console.cloud.google.com/apis/library/sheets.googleapis.com)

### 3. Set up Gmail OAuth (for reading emails)

1. Go to **APIs & Services → Credentials**
2. Click **Create Credentials → OAuth Client ID**
3. Choose **Desktop App** as the application type
4. Download the JSON or note the **Client ID** and **Client Secret**
5. Go to **APIs & Services → OAuth consent screen**
   - Add yourself as a test user (required for unverified apps)

Then run the setup script locally:

```bash
pip install google-auth-oauthlib
python scripts/setup_gmail_oauth.py
```

This opens a browser for authorization. After granting access, it prints three values to save as GitHub Secrets.

### 4. Set up Google Sheets Service Account (for writing to sheets)

1. Go to **IAM & Admin → Service Accounts**
2. Click **Create Service Account** — give it any name
3. Click the created account → **Keys → Add Key → Create new key → JSON**
4. Base64-encode the downloaded JSON file:
   ```bash
   base64 -i your-service-account-key.json
   ```
5. Save the output as a GitHub Secret

### 5. Create your Google Sheet

1. Create a new Google Sheet
2. Copy the **Sheet ID** from the URL: `https://docs.google.com/spreadsheets/d/{THIS_PART}/edit`
3. Share the sheet with your service account email (found in the JSON key file, looks like `name@project.iam.gserviceaccount.com`) — give it **Editor** access
4. The script will auto-create headers on first run, but you can also set them manually:

| Date Applied | Company | Position | Status | Email Subject | Source Email Date | Message ID |
| ------------ | ------- | -------- | ------ | ------------- | ----------------- | ---------- |

### 6. Get an Anthropic API key

1. Go to [console.anthropic.com](https://console.anthropic.com/)
2. Create an API key

### 7. Add GitHub Secrets

Go to your fork → **Settings → Secrets and variables → Actions** and add:

| Secret                        | Value                                           |
| ----------------------------- | ----------------------------------------------- |
| `GMAIL_CLIENT_ID`           | From step 3                                     |
| `GMAIL_CLIENT_SECRET`       | From step 3                                     |
| `GMAIL_REFRESH_TOKEN`       | From step 3                                     |
| `GOOGLE_SHEETS_CREDENTIALS` | Base64-encoded service account JSON from step 4 |
| `GOOGLE_SHEET_ID`           | From step 5                                     |
| `ANTHROPIC_API_KEY`         | From step 6                                     |

### 8. Enable the workflow

Go to **Actions** tab in your fork → click **"I understand my workflows, go ahead and enable them"** → you can manually trigger the workflow or wait for the daily cron.

## Usage

### Manual trigger

Go to Actions → "Track Job Applications" → "Run workflow"

### Local development

```bash
# Install dependencies
pip install -r requirements.txt

# Create .env from template
cp .env.example .env
# Fill in your values in .env

# Dry run (preview only, no sheet changes)
python -m src.main --dry-run

# Full run
python -m src.main

# Scan more than 24 hours back
python -m src.main --hours 72
```

### Google Sheet layout

**Columns A–G** (application data):

| Date Applied | Company | Position | Status | Email Subject | Source Email Date | Message ID |
| ------------ | ------- | -------- | ------ | ------------- | ----------------- | ---------- |

**Columns I–J** (auto-updated stats):

- Total applications
- This week / this month
- Status breakdown (Applied, Interview, Rejected, Offer, etc.)
- Top companies applied to

**Status column** — manually update to track progress:

- `Applied` (default)
- `Interview`
- `Offer`
- `Rejected`
- `Withdrawn`

## Customization

- **Cron schedule**: Edit `.github/workflows/track-applications.yml` — the `cron` field uses UTC
- **AI model**: Edit `src/email_parser.py` — change the `model` parameter (default: `claude-haiku-4-5-20251001`)
- **Email filter**: Edit `src/gmail_client.py` — modify the Gmail query in `fetch_recent_emails()`
- **Sheet columns**: Edit `src/sheets_client.py` — modify `HEADERS` and the row-building logic

## Architecture

```
src/
├── main.py            # Orchestrator — ties everything together
├── gmail_client.py    # Gmail API — fetches recent inbox emails
├── email_parser.py    # Claude API — identifies application confirmations
└── sheets_client.py   # Google Sheets API — reads/writes/deduplicates
```

## Cost hello

- **GitHub Actions**: Free for public repos, 2000 min/month for private repos
- **Gmail API**: Free
- **Google Sheets API**: Free
- **Claude API**: ~$0.01–0.05 per run (depends on email volume; uses Haiku for cost efficiency)
