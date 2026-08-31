"""Daily AI News Briefing pipeline.

Runs as a Cloud Run Job (triggered daily by Cloud Scheduler):

  1. Fetch the latest TLDR AI newsletter from Gmail over IMAP.
  2. Rewrite it into a spoken-word briefing with Claude Haiku (Vertex AI, with an
     Anthropic-API fallback).
  3. Synthesize audio with Google Cloud Text-to-Speech (MP3).
  4. Email the MP3 (script in the body) back to the user over Gmail SMTP.
  5. Optionally archive the script + audio to a GCS bucket.

All configuration comes from environment variables. In Cloud Run these are injected
from Secret Manager (see deploy.sh); for local testing a .env file is loaded if present.
"""

from __future__ import annotations

import datetime as dt
import email
import imaplib
import logging
import os
import smtplib
import sys
from email.header import decode_header
from email.message import EmailMessage
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("daily-news")

# Cloud TTS accepts at most 5000 bytes of input per request; stay well under it.
TTS_MAX_CHARS = 4500


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
def _load_dotenv() -> None:
    """Load a local .env for development. No-op in the cloud (no file present)."""
    env_path = Path(__file__).with_name(".env")
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class Config:
    def __init__(self) -> None:
        self.gmail_address = self._req("GMAIL_ADDRESS")
        self.gmail_app_password = self._req("GMAIL_APP_PASSWORD")
        self.recipient = os.environ.get("RECIPIENT", self.gmail_address)

        self.tldr_sender = os.environ.get("TLDR_SENDER", "dan@tldrnewsletter.com")
        self.tldr_subject_contains = os.environ.get("TLDR_SUBJECT_CONTAINS", "TLDR AI")
        self.imap_lookback_days = int(os.environ.get("IMAP_LOOKBACK_DAYS", "3"))

        # LLM: Vertex AI first, Anthropic API as fallback.
        self.use_vertex = os.environ.get("USE_VERTEX", "1") == "1"
        self.gcp_project = os.environ.get(
            "GOOGLE_CLOUD_PROJECT", os.environ.get("GCP_PROJECT", "")
        )
        self.vertex_region = os.environ.get("VERTEX_REGION", "us-east5")
        self.vertex_model = os.environ.get("VERTEX_MODEL", "claude-haiku-4-5@20251001")
        self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self.anthropic_model = os.environ.get(
            "ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"
        )

        # Text-to-Speech
        self.tts_language = os.environ.get("TTS_LANGUAGE", "en-US")
        self.tts_voice = os.environ.get("TTS_VOICE", "en-US-Neural2-D")

        # Optional archive
        self.gcs_bucket = os.environ.get("GCS_BUCKET", "")

    @staticmethod
    def _req(name: str) -> str:
        value = os.environ.get(name)
        if not value:
            raise RuntimeError(f"Missing required environment variable: {name}")
        return value


# --------------------------------------------------------------------------- #
# Step 1: fetch the TLDR AI newsletter over IMAP
# --------------------------------------------------------------------------- #
def _decode(value: str) -> str:
    parts = decode_header(value)
    out = []
    for text, enc in parts:
        if isinstance(text, bytes):
            out.append(text.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out)


def _extract_body(msg: email.message.Message) -> str:
    """Return plain-text body, falling back to HTML stripped to text."""
    plain, html = None, None
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if "attachment" in disp:
                continue
            try:
                payload = part.get_payload(decode=True)
            except Exception:
                continue
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if ctype == "text/plain" and plain is None:
                plain = decoded
            elif ctype == "text/html" and html is None:
                html = decoded
    else:
        payload = msg.get_payload(decode=True)
        charset = msg.get_content_charset() or "utf-8"
        text = payload.decode(charset, errors="replace") if payload else ""
        if msg.get_content_type() == "text/html":
            html = text
        else:
            plain = text

    if plain and plain.strip():
        return plain
    if html:
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style"]):
                tag.decompose()
            return soup.get_text("\n")
        except Exception:
            return html
    return ""


def fetch_latest_tldr(cfg: Config) -> str | None:
    """Return the plain-text body of the most recent TLDR AI email, or None."""
    since = (
        dt.date.today() - dt.timedelta(days=cfg.imap_lookback_days)
    ).strftime("%d-%b-%Y")

    log.info("Connecting to Gmail IMAP as %s", cfg.gmail_address)
    imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    try:
        imap.login(cfg.gmail_address, cfg.gmail_app_password)
        imap.select("INBOX", readonly=True)

        typ, data = imap.search(
            None, "FROM", f'"{cfg.tldr_sender}"', "SINCE", since
        )
        ids = data[0].split() if data and data[0] else []

        if not ids:
            # Fall back to a subject-based search if the sender didn't match.
            typ, data = imap.search(
                None, "SUBJECT", f'"{cfg.tldr_subject_contains}"', "SINCE", since
            )
            ids = data[0].split() if data and data[0] else []

        if not ids:
            log.warning(
                "No TLDR email found (sender=%s, subject~=%s, since=%s)",
                cfg.tldr_sender,
                cfg.tldr_subject_contains,
                since,
            )
            return None

        latest_id = ids[-1]
        typ, msg_data = imap.fetch(latest_id, "(RFC822)")
        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)
        subject = _decode(msg.get("Subject", ""))
        log.info("Fetched email: %r", subject)
        return _extract_body(msg)
    finally:
        try:
            imap.logout()
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# Step 2: rewrite with Claude
# --------------------------------------------------------------------------- #
def build_prompt(source: str) -> str:
    template = Path(__file__).with_name("prompt_template.md").read_text()
    return template.replace("{{SOURCE}}", source)


def rewrite_with_claude(cfg: Config, source: str) -> str:
    prompt = build_prompt(source)

    if cfg.use_vertex:
        try:
            from anthropic import AnthropicVertex

            client = AnthropicVertex(
                project_id=cfg.gcp_project, region=cfg.vertex_region
            )
            log.info("Rewriting via Vertex AI model %s", cfg.vertex_model)
            resp = client.messages.create(
                model=cfg.vertex_model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text.strip()
        except Exception as exc:  # noqa: BLE001
            if not cfg.anthropic_api_key:
                raise
            log.warning("Vertex path failed (%s); falling back to Anthropic API", exc)

    from anthropic import Anthropic

    client = Anthropic(api_key=cfg.anthropic_api_key)
    log.info("Rewriting via Anthropic API model %s", cfg.anthropic_model)
    resp = client.messages.create(
        model=cfg.anthropic_model,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


# --------------------------------------------------------------------------- #
# Step 3: synthesize audio with Cloud TTS
# --------------------------------------------------------------------------- #
def _chunk_text(text: str, limit: int = TTS_MAX_CHARS) -> list[str]:
    """Split text into <=limit-char chunks on paragraph/sentence boundaries."""
    chunks: list[str] = []
    current = ""
    for para in text.split("\n"):
        candidate = f"{current}\n{para}" if current else para
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        # Paragraph itself may exceed the limit: split on sentences.
        if len(para) <= limit:
            current = para
        else:
            sentence = ""
            for token in para.replace(". ", ".\n").split("\n"):
                cand = f"{sentence} {token}".strip()
                if len(cand) <= limit:
                    sentence = cand
                else:
                    if sentence:
                        chunks.append(sentence)
                    sentence = token[:limit]
            current = sentence
    if current:
        chunks.append(current)
    return [c for c in chunks if c.strip()]


def synthesize_mp3(cfg: Config, script: str) -> bytes:
    from google.cloud import texttospeech

    client = texttospeech.TextToSpeechClient()
    voice = texttospeech.VoiceSelectionParams(
        language_code=cfg.tts_language, name=cfg.tts_voice
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3
    )

    audio = bytearray()
    chunks = _chunk_text(script)
    log.info("Synthesizing %d TTS chunk(s) with voice %s", len(chunks), cfg.tts_voice)
    for chunk in chunks:
        synthesis_input = texttospeech.SynthesisInput(text=chunk)
        response = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )
        audio.extend(response.audio_content)
    return bytes(audio)


# --------------------------------------------------------------------------- #
# Step 4: email the clip
# --------------------------------------------------------------------------- #
def send_email(cfg: Config, script: str, mp3: bytes, date_str: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = f"AI Morning Briefing — {date_str}"
    msg["From"] = cfg.gmail_address
    msg["To"] = cfg.recipient
    msg.set_content(
        "Your daily AI briefing is attached as audio.\n\n"
        "Transcript below.\n\n"
        f"{script}\n"
    )
    msg.add_attachment(
        mp3,
        maintype="audio",
        subtype="mpeg",
        filename=f"ai-briefing-{date_str}.mp3",
    )

    log.info("Emailing briefing to %s", cfg.recipient)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(cfg.gmail_address, cfg.gmail_app_password)
        server.send_message(msg)


# --------------------------------------------------------------------------- #
# Step 5 (optional): archive to GCS
# --------------------------------------------------------------------------- #
def archive_to_gcs(cfg: Config, script: str, mp3: bytes, date_str: str) -> None:
    if not cfg.gcs_bucket:
        return
    try:
        from google.cloud import storage

        client = storage.Client()
        bucket = client.bucket(cfg.gcs_bucket)
        bucket.blob(f"briefings/{date_str}.txt").upload_from_string(
            script, content_type="text/plain"
        )
        bucket.blob(f"briefings/{date_str}.mp3").upload_from_string(
            mp3, content_type="audio/mpeg"
        )
        log.info("Archived script + audio to gs://%s/briefings/%s.*", cfg.gcs_bucket, date_str)
    except Exception as exc:  # noqa: BLE001
        log.warning("GCS archive failed (non-fatal): %s", exc)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def main() -> int:
    _load_dotenv()
    cfg = Config()
    date_str = dt.date.today().isoformat()

    source = fetch_latest_tldr(cfg)
    if not source or not source.strip():
        log.info("No source material today — nothing to send. Exiting cleanly.")
        return 0

    script = rewrite_with_claude(cfg, source)
    word_count = len(script.split())
    log.info("Generated briefing script (%d words)", word_count)

    mp3 = synthesize_mp3(cfg, script)
    log.info("Synthesized audio (%d KB)", len(mp3) // 1024)

    send_email(cfg, script, mp3, date_str)
    archive_to_gcs(cfg, script, mp3, date_str)

    log.info("Done: briefing for %s delivered.", date_str)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        log.exception("Pipeline failed: %s", exc)
        sys.exit(1)
