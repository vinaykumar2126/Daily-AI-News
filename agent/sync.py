"""Refresh the realtime agent's knowledge with today's briefing.

Provider-neutral: builds today's context (reusing the pipeline) and hands it to the active
provider's `sync()`. This is what replaces the manual copy/paste — run it daily.

    python -m agent.sync                 # refresh the configured provider's knowledge
    python -m agent.sync --dry-run       # build + print today's doc, don't touch the provider
"""

from __future__ import annotations

import argparse
import logging

import observability
from agent import context as agent_context
from agent.providers import create_provider
from config import Config, load_dotenv, load_feeds

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("daily-news.agent.sync")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="build + print, don't update the provider")
    ap.add_argument(
        "--call",
        nargs="?",
        const="",
        metavar="NUMBER",
        help="after syncing, ring this number (default USER_PHONE_NUMBER) and connect the agent",
    )
    ap.add_argument(
        "--call-only",
        nargs="?",
        const="",
        metavar="NUMBER",
        help="ring without refreshing knowledge first — for testing the telephony wiring alone",
    )
    args = ap.parse_args()

    load_dotenv()
    cfg = Config()
    observability.setup(cfg)

    # Telephony-only path: skip the pipeline entirely. Rebuilding the briefing costs ~2 minutes and
    # real tokens, which is a poor way to find out whether a phone number is wired up.
    if args.call_only is not None:
        try:
            _place_call(create_provider(cfg), args.call_only or None)
        finally:
            observability.flush()
        return 0

    feeds = load_feeds()

    with observability.span(
        "daily_news.agent_sync",
        curator=cfg.curator,
        feeds=len(feeds),
        dry_run=args.dry_run,
        provider=cfg.realtime_provider,
    ):
        # Reuses gather_stories / build_segments_from_stories, so the pipeline spans come along.
        ctx = agent_context.build_context(cfg, feeds)
        log.info("Built context: %d stories across feeds", len(ctx.get("stories", [])))
        observability.set_attrs(stories=len(ctx.get("stories", [])))

        if args.dry_run:
            print(agent_context.render_markdown(ctx))
            log.info("--dry-run: skipping provider sync.")
            observability.set_attrs(outcome="dry_run")
            return 0

        provider = create_provider(cfg)
        log.info("Syncing knowledge to provider: %s", provider.name)
        with observability.span("provider_sync", provider=provider.name):
            result = provider.sync(ctx)
        log.info("Done: %s", result)
        observability.set_attrs(outcome="synced")

        if args.call is not None:
            _place_call(provider, args.call or None)
    return 0


def _place_call(provider, to_number: str | None) -> dict:
    """Ring the listener and connect them to the agent, after the knowledge refresh."""
    log.info("Placing outbound call via %s", provider.name)
    with observability.span("outbound_call", provider=provider.name):
        result = provider.place_outbound_call(to_number)
        observability.set_attrs(
            conversation_id=result.get("conversation_id"), call_sid=result.get("call_sid")
        )
    log.info("Call result: %s", result)
    return result


if __name__ == "__main__":
    try:
        code = main()
    except Exception as exc:  # noqa: BLE001
        log.exception("Agent sync failed: %s", exc)
        code = 1
    finally:
        # Batched spans would otherwise never leave this short-lived process.
        observability.flush()
    raise SystemExit(code)
