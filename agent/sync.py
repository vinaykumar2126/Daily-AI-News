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
    args = ap.parse_args()

    load_dotenv()
    cfg = Config()
    observability.setup(cfg)
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
    return 0


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
