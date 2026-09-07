"""Daily News Briefing pipeline (Cloud Run Job entrypoint).

  1. For each enabled feed in feeds.yaml: fetch + merge its sources, curate, and rewrite into
     a spoken segment with Gemini on Vertex AI.
  2. Compose the segments into one script (greeting + transitions + sign-off).
  3. Synthesize audio with Google Cloud Text-to-Speech (MP3).
  4. Email the MP3 (script in the body) back to the user over Gmail SMTP.
  5. Optionally archive the script + audio to a GCS bucket.

Configuration comes from environment variables (Secret Manager in the cloud, a local .env for
development); the feed catalog comes from feeds.yaml. Set DRY_RUN=1 to print the script and
skip audio + email. Set CURATOR=agentic to use the ADK curator instead of the deterministic one.
"""

from __future__ import annotations

import datetime as dt
import logging
import smtplib
import sys
from email.message import EmailMessage

import pipeline
from config import Config, load_dotenv, load_feeds

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("daily-news")

# Cloud TTS accepts at most 5000 bytes of input per request; stay well under it.
# Gemini TTS caps input.text at 4000 bytes per request; keep a safety margin.
TTS_MAX_BYTES = 3800


def _blen(s: str) -> int:
    """UTF-8 byte length (multi-byte chars like em-dashes count as >1)."""
    return len(s.encode("utf-8"))


def _byte_truncate(s: str, limit: int) -> str:
    """Truncate a string to at most `limit` UTF-8 bytes without splitting a char."""
    return s.encode("utf-8")[:limit].decode("utf-8", errors="ignore")


# --------------------------------------------------------------------------- #
# Audio synthesis
# --------------------------------------------------------------------------- #
def _chunk_text(text: str, limit: int = TTS_MAX_BYTES) -> list[str]:
    """Split text into <=limit-byte chunks on paragraph/sentence boundaries."""
    chunks: list[str] = []
    current = ""
    for para in text.split("\n"):
        candidate = f"{current}\n{para}" if current else para
        if _blen(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        if _blen(para) <= limit:
            current = para
        else:
            sentence = ""
            for token in para.replace(". ", ".\n").split("\n"):
                cand = f"{sentence} {token}".strip()
                if _blen(cand) <= limit:
                    sentence = cand
                else:
                    if sentence:
                        chunks.append(sentence)
                    sentence = _byte_truncate(token, limit)
            current = sentence
    if current:
        chunks.append(current)
    return [c for c in chunks if c.strip()]


def synthesize_mp3(cfg: Config, script: str) -> bytes:
    from google.cloud import texttospeech

    client = texttospeech.TextToSpeechClient()
    # model_name + input.prompt are Gemini-TTS-only. Send them only when TTS_MODEL is set,
    # so a plain/stable voice (Chirp3-HD, Neural2, ...) works with the same code path.
    voice_kwargs = {"language_code": cfg.tts_language, "name": cfg.tts_voice}
    if cfg.tts_model:
        voice_kwargs["model_name"] = cfg.tts_model
    voice = texttospeech.VoiceSelectionParams(**voice_kwargs)
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3
    )

    audio = bytearray()
    chunks = _chunk_text(script)
    log.info("Synthesizing %d TTS chunk(s) with voice %s", len(chunks), cfg.tts_voice)
    for chunk in chunks:
        input_kwargs = {"text": chunk}
        if cfg.tts_model and cfg.tts_prompt:
            input_kwargs["prompt"] = cfg.tts_prompt
        synthesis_input = texttospeech.SynthesisInput(**input_kwargs)
        response = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )
        audio.extend(response.audio_content)
    return bytes(audio)


# --------------------------------------------------------------------------- #
# Delivery
# --------------------------------------------------------------------------- #
def send_email(cfg: Config, script: str, mp3: bytes, date_str: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = f"Morning Briefing — {date_str}"
    msg["From"] = cfg.gmail_address
    msg["To"] = cfg.recipient
    msg.set_content(
        "Your daily briefing is attached as audio.\n\n"
        "Transcript below.\n\n"
        f"{script}\n"
    )
    msg.add_attachment(
        mp3,
        maintype="audio",
        subtype="mpeg",
        filename=f"briefing-{date_str}.mp3",
    )

    log.info("Emailing briefing to %s", cfg.recipient)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(cfg.gmail_address, cfg.gmail_app_password)
        server.send_message(msg)


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
        log.info("Archived to gs://%s/briefings/%s.*", cfg.gcs_bucket, date_str)
    except Exception as exc:  # noqa: BLE001
        log.warning("GCS archive failed (non-fatal): %s", exc)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def main() -> int:
    load_dotenv()
    cfg = Config()
    feeds = load_feeds()
    date = dt.date.today()
    date_str = date.isoformat()

    script = pipeline.generate_script(cfg, feeds, date=date)
    if not script.strip():
        log.info("No content across any feed today — nothing to send. Exiting cleanly.")
        return 0

    word_count = len(script.split())
    log.info("Composed briefing script (%d words)", word_count)

    if cfg.dry_run:
        print("\n" + "=" * 70 + "\n" + script + "\n" + "=" * 70 + "\n")
        log.info("DRY_RUN set — skipping audio + email.")
        return 0

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
