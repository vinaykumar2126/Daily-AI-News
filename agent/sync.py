"""Refresh the realtime agent's knowledge with today's briefing.

Provider-neutral: builds today's context (reusing the pipeline) and hands it to the active
provider's `sync()`. This is what replaces the manual copy/paste — run it daily.

    python -m agent.sync                 # refresh the configured provider's knowledge
    python -m agent.sync --dry-run       # build + print today's doc, don't touch the provider
"""

from __future__ import annotations

import argparse
import logging

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
    feeds = load_feeds()

    ctx = agent_context.build_context(cfg, feeds)
    log.info("Built context: %d stories across feeds", len(ctx.get("stories", [])))

    if args.dry_run:
        print(agent_context.render_markdown(ctx))
        log.info("--dry-run: skipping provider sync.")
        return 0

    provider = create_provider(cfg)
    log.info("Syncing knowledge to provider: %s", provider.name)
    result = provider.sync(ctx)
    log.info("Done: %s", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
