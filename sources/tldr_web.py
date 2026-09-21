"""TLDR AI web source: parse the current AI edition from tldr.tech (no email).

Entry point: https://tldr.tech/api/latest/ai redirects to the latest dated issue
(e.g. https://tldr.tech/ai/2026-09-18), server-rendered as HTML. This gives us the
real, current AI edition with clean per-story structure — no IMAP, no marketing/
re-engagement confusion, and real article URLs (anthropic.com/..., claude.com/blog/...)
instead of opaque Google News redirects.

Per-story markup (stable across issues):

    <article class="mt-3">
      <a class="font-bold" href="REAL_URL"><h3>Title (12 minute read)</h3></a>
      <div class="newsletter-html">Description...</div>
    </article>

Categories are standalone headers: <h3 class="text-center font-bold">Deep Dives & Analysis</h3>.
Sponsored items are titled "... (Sponsor)" — we drop those precisely at the source.

Params:
  url:               override the entry URL (default the api/latest/ai endpoint)
  max_items:         cap total stories kept (default: no cap)
  exclude_categories: list of category names to skip (case-insensitive)
  include_categories: if set, keep only these categories (case-insensitive)
  keep_sponsors:     bool, default False (drop "(Sponsor)" items)
"""

from __future__ import annotations

import datetime as dt
import logging
import re
import urllib.request

from sources.base import Source, Story, register_source

log = logging.getLogger("daily-news.sources.tldr_web")

_LATEST_AI = "https://tldr.tech/api/latest/ai"
_UA = "Mozilla/5.0 (compatible; DailyNews/1.0; +https://tldr.tech)"

# Categories TLDR uses for the AI edition. Any text-center+font-bold header that isn't the
# date title is treated as a category, so new/renamed sections are picked up automatically;
# this list is just for reference/docs.
KNOWN_CATEGORIES = (
    "Headlines & Launches",
    "Deep Dives & Analysis",
    "Engineering & Research",
    "Miscellaneous",
    "Quick Links",
)

# Trailing parenthetical on a title: "(12 minute read)", "(Sponsor)", "(GitHub Repo)".
_META_PAREN = re.compile(r"\s*\(([^()]*)\)\s*$")
_READ_MIN = re.compile(r"(\d+)\s*minute read", re.I)
_ISSUE_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def _has_class(tag, *needed: str) -> bool:
    classes = tag.get("class") or []
    return all(c in classes for c in needed)


def _split_title_meta(raw_title: str) -> tuple[str, str, int | None]:
    """('How Claude ... (12 minute read)') -> ('How Claude ...', '12 minute read', 12).

    Returns (clean_title, meta_text, read_minutes|None). meta_text is '' when there is no
    trailing parenthetical.
    """
    m = _META_PAREN.search(raw_title)
    if not m:
        return raw_title.strip(), "", None
    meta = m.group(1).strip()
    clean = raw_title[: m.start()].strip()
    rm = _READ_MIN.search(meta)
    read_minutes = int(rm.group(1)) if rm else None
    return clean, meta, read_minutes


def _parse_issue(html: str, final_url: str = "") -> tuple[list[Story], dt.datetime | None]:
    """Pure parser: HTML string -> (raw stories, issue_date). No network, no filtering.

    Every <article class="mt-3"> becomes a Story tagged with its section in extra["category"]
    and (when present) extra["read_minutes"] and extra["sponsor"]. Sponsor dropping and
    category/max filtering happen in fetch(), so this stays easy to unit-test.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")

    # Issue date: prefer the resolved URL, fall back to the page's date header/title.
    issue_date: dt.datetime | None = None
    for text in (final_url, soup.title.get_text() if soup.title else "", html[:4000]):
        m = _ISSUE_DATE.search(text or "")
        if m:
            try:
                issue_date = dt.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                break
            except ValueError:
                pass

    # Walk categories and articles in document order so each article gets its section.
    def _is_category(tag) -> bool:
        return (
            tag.name in ("h1", "h2", "h3")
            and _has_class(tag, "text-center", "font-bold")
            and tag.get_text(" ", strip=True) != ""
            and not tag.get_text(" ", strip=True).upper().startswith("TLDR AI")
        )

    def _is_article(tag) -> bool:
        return tag.name == "article" and tag.find("a", class_="font-bold") is not None

    stories: list[Story] = []
    current_category = ""
    for tag in soup.find_all(lambda t: _is_category(t) or _is_article(t)):
        if _is_category(tag):
            current_category = tag.get_text(" ", strip=True)
            continue

        link = tag.find("a", class_="font-bold")
        raw_title = link.get_text(" ", strip=True)
        if not raw_title:
            continue
        url = link.get("href", "").strip()
        desc_el = tag.find("div", class_="newsletter-html")
        body = desc_el.get_text(" ", strip=True) if desc_el else ""

        clean_title, meta, read_minutes = _split_title_meta(raw_title)
        is_sponsor = meta.strip().lower() == "sponsor"

        extra: dict = {"category": current_category}
        if read_minutes is not None:
            extra["read_minutes"] = read_minutes
        if meta and read_minutes is None:
            extra["kind"] = meta  # e.g. "GitHub Repo", "Sponsor"
        if is_sponsor:
            extra["sponsor"] = True

        stories.append(
            Story(
                title=clean_title,
                body=body,
                url=url,
                published_at=issue_date,
                source="TLDR AI",
                extra=extra,
            )
        )
    return stories, issue_date


@register_source("tldr_web")
class TldrWebSource(Source):
    """params: url, max_items, include_categories, exclude_categories, keep_sponsors."""

    label = "TLDR AI"

    def _load_html(self, url: str) -> tuple[str, str]:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=20) as resp:
            final_url = resp.geturl()
            charset = resp.headers.get_content_charset() or "utf-8"
            html = resp.read().decode(charset, errors="replace")
        return html, final_url

    def fetch(self) -> list[Story]:
        url = self.params.get("url", _LATEST_AI)
        max_items = self.params.get("max_items")
        keep_sponsors = bool(self.params.get("keep_sponsors", False))
        include = {c.lower() for c in self.params.get("include_categories", []) or []}
        exclude = {c.lower() for c in self.params.get("exclude_categories", []) or []}

        try:
            html, final_url = self._load_html(url)
        except Exception as exc:  # noqa: BLE001
            log.warning("TLDR AI fetch failed for %s: %s", url, exc)
            return []

        raw, issue_date = _parse_issue(html, final_url)

        kept: list[Story] = []
        dropped_sponsors = 0
        for story in raw:
            if not keep_sponsors and story.extra.get("sponsor"):
                dropped_sponsors += 1
                continue
            cat = story.extra.get("category", "").lower()
            if include and cat not in include:
                continue
            if cat in exclude:
                continue
            kept.append(story)
            if max_items and len(kept) >= int(max_items):
                break

        log.info(
            "TLDR AI: %d stories (issue %s, dropped %d sponsor(s)) from %s",
            len(kept),
            issue_date.date().isoformat() if issue_date else "?",
            dropped_sponsors,
            final_url,
        )
        return kept
