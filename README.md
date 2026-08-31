# Daily AI News Briefing

Every morning at 7 AM, this pipeline reads the TLDR AI newsletter from your Gmail, rewrites it
into a natural spoken-word script with Claude Haiku, turns it into audio with Google Cloud
Text-to-Speech, and emails the MP3 back to you — so you can listen on your phone. Runs entirely
on Google Cloud, independent of your laptop.

## How it works

```
Cloud Scheduler (7 AM cron)
        │  triggers
        ▼
Cloud Run Job (main.py)
   1. IMAP-fetch latest TLDR AI email from Gmail
   2. Rewrite → Claude Haiku 4.5 on Vertex AI   (prompt_template.md)
   3. Synthesize MP3 → Google Cloud TTS
   4. Email the MP3 back → Gmail SMTP
   5. (optional) archive to a GCS bucket
```

## Setup

1. **Gmail App Password** — Google Account → Security → 2-Step Verification → App passwords.
   (2FA must be on.) This one password is used for both reading (IMAP) and sending (SMTP).
2. **Confirm the newsletter sender** — open a real TLDR AI email and check the `From:` address;
   set `TLDR_SENDER` accordingly (default `dan@tldrnewsletter.com`).
3. **Edit `deploy.sh`** — set `PROJECT_ID`, `REGION`, and `TIMEZONE`.
4. **Deploy** — `bash deploy.sh` (enables APIs, builds the image, stores the secret, creates the
   Cloud Run Job + Scheduler trigger).
5. If Claude isn't enabled on Vertex in your region, enable it in Vertex AI Model Garden, or
   create an `anthropic-api-key` secret and uncomment the fallback line in `deploy.sh`.

## Local testing

```bash
.venv/bin/pip install -r requirements.txt
cp .env.example .env          # fill in GMAIL_ADDRESS + GMAIL_APP_PASSWORD, etc.
gcloud auth application-default login   # for Vertex + TTS credentials
.venv/bin/python main.py
```

You should receive the briefing email within a minute. Check the transcript reads naturally and
the audio has no mangled acronyms/numbers.

## Test the deployed job

```bash
gcloud run jobs execute daily-news --region <REGION>
gcloud run jobs executions list --job daily-news --region <REGION>
```

## Configuration

All settings are environment variables (see `.env.example`). Key ones:

| Variable | Purpose | Default |
| --- | --- | --- |
| `GMAIL_ADDRESS` / `GMAIL_APP_PASSWORD` | Gmail auth (IMAP + SMTP) | — (required) |
| `RECIPIENT` | Where the clip is emailed | `GMAIL_ADDRESS` |
| `TLDR_SENDER` | Newsletter `From:` to match | `dan@tldrnewsletter.com` |
| `VERTEX_MODEL` | Claude model on Vertex | `claude-haiku-4-5@20251001` |
| `TTS_VOICE` | Cloud TTS voice | `en-US-Neural2-D` |
| `GCS_BUCKET` | Optional archive bucket | _(off)_ |

## Cost

With GCP free credits it's effectively $0/day: the LLM runs on Vertex (billed to credits), TTS
stays within the free tier for a ~1,000-word script, and Cloud Run + Scheduler usage is negligible.
