"""Gmail newsletter source: fetch the latest matching newsletter over IMAP.

Refactored from the original main.py fetch_latest_tldr/_extract_body/_decode. Emits a
single Story whose body is the newsletter's plain text — the curator/rewrite step does the
rest. Credentials come from the environment (GMAIL_ADDRESS / GMAIL_APP_PASSWORD).
"""

from __future__ import annotations

import datetime as dt
import email
import imaplib
import logging
import os
from email.header import decode_header

from sources.base import Source, Story, register_source

log = logging.getLogger("daily-news.sources.gmail")


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


@register_source("gmail_newsletter")
class GmailNewsletterSource(Source):
    """Fetch the most recent newsletter matching a sender (or subject) over IMAP.

    params:
      sender:            From address or display name to match (required-ish)
      subject_contains:  fallback subject match if the sender search finds nothing
      lookback_days:     how far back to search (default 3)
    """

    label = "newsletter"

    def fetch(self) -> list[Story]:
        address = os.environ.get("GMAIL_ADDRESS")
        password = os.environ.get("GMAIL_APP_PASSWORD")
        if not address or not password:
            raise RuntimeError("GMAIL_ADDRESS / GMAIL_APP_PASSWORD not set")

        sender = self.params.get("sender", "")
        subject_contains = self.params.get("subject_contains", "")
        lookback_days = int(self.params.get("lookback_days", 3))
        since = (dt.date.today() - dt.timedelta(days=lookback_days)).strftime("%d-%b-%Y")

        log.info("Connecting to Gmail IMAP as %s", address)
        imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        try:
            imap.login(address, password)
            imap.select("INBOX", readonly=True)

            ids = []
            if sender:
                _, data = imap.search(None, "FROM", f'"{sender}"', "SINCE", since)
                ids = data[0].split() if data and data[0] else []
            if not ids and subject_contains:
                _, data = imap.search(
                    None, "SUBJECT", f'"{subject_contains}"', "SINCE", since
                )
                ids = data[0].split() if data and data[0] else []

            if not ids:
                log.warning(
                    "No newsletter found (sender=%s, subject~=%s, since=%s)",
                    sender,
                    subject_contains,
                    since,
                )
                return []

            latest_id = ids[-1]
            _, msg_data = imap.fetch(latest_id, "(RFC822)")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            subject = _decode(msg.get("Subject", ""))
            log.info("Fetched newsletter: %r", subject)
            body = _extract_body(msg)
            if not body.strip():
                return []
            return [
                Story(
                    title=subject or (sender or "Newsletter"),
                    body=body,
                    source=sender or self.label,
                )
            ]
        finally:
            try:
                imap.logout()
            except Exception:
                pass
