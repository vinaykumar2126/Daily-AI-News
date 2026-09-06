"""Cross-run memory: what the digest has surfaced before.

A stateless daily job can't say "Y beats last week's X" because it never saw X. This module
persists a compact record after each run and reads recent history back, so the agentic curator
can connect today's launches to prior coverage. Backed by a local JSON file, mirrored to GCS
when GCS_BUCKET is set so it survives across Cloud Run executions.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
from pathlib import Path

log = logging.getLogger("daily-news.memory")

_LOCAL_PATH = Path(__file__).with_name(".digest_memory.json")
_GCS_BLOB = "memory/digest_history.json"


def _bucket():
    name = os.environ.get("GCS_BUCKET")
    if not name:
        return None
    try:
        from google.cloud import storage

        return storage.Client().bucket(name)
    except Exception as exc:  # noqa: BLE001
        log.warning("GCS memory unavailable, using local only: %s", exc)
        return None


def _load_all() -> list[dict]:
    bucket = _bucket()
    if bucket is not None:
        try:
            blob = bucket.blob(_GCS_BLOB)
            if blob.exists():
                return json.loads(blob.download_as_text())
        except Exception as exc:  # noqa: BLE001
            log.warning("GCS memory read failed: %s", exc)
    if _LOCAL_PATH.exists():
        try:
            return json.loads(_LOCAL_PATH.read_text())
        except Exception:  # noqa: BLE001
            return []
    return []


def _save_all(records: list[dict]) -> None:
    text = json.dumps(records, indent=2, ensure_ascii=False)
    try:
        _LOCAL_PATH.write_text(text)
    except Exception as exc:  # noqa: BLE001
        log.warning("local memory write failed: %s", exc)
    bucket = _bucket()
    if bucket is not None:
        try:
            bucket.blob(_GCS_BLOB).upload_from_string(text, content_type="application/json")
        except Exception as exc:  # noqa: BLE001
            log.warning("GCS memory write failed: %s", exc)


def append_record(date: str, items: list[dict]) -> None:
    """Append one day's surfaced items: [{title, url, source}, ...]. Replaces same-date record."""
    records = [r for r in _load_all() if r.get("date") != date]
    records.append({"date": date, "items": items})
    records.sort(key=lambda r: r.get("date", ""))
    _save_all(records)
    log.info("Recorded %d items to memory for %s", len(items), date)


def recent_history(days: int = 30) -> list[dict]:
    """Return records from the last `days` days, oldest first."""
    cutoff = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    return [r for r in _load_all() if r.get("date", "") >= cutoff]
