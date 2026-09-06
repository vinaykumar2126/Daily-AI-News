"""Stocks source via yfinance: daily moves for indices + a watchlist.

Emits compact Stories carrying the raw numbers ("what moved and why" is left to the
rewrite prompt). Params:

  indices:   list of index symbols (e.g. ["^GSPC", "^IXIC", "^DJI"])
  watchlist: list of tickers (e.g. ["NVDA", "GOOGL", ...])
"""

from __future__ import annotations

import datetime as dt
import logging

from sources.base import Source, Story, register_source

log = logging.getLogger("daily-news.sources.stocks")

_INDEX_NAMES = {
    "^GSPC": "S&P 500",
    "^IXIC": "Nasdaq Composite",
    "^DJI": "Dow Jones",
    "^RUT": "Russell 2000",
}


def _pct_move(symbol: str) -> tuple[float, float] | None:
    """Return (last_close, pct_change_vs_prev_close) or None if unavailable."""
    import yfinance as yf

    try:
        hist = yf.Ticker(symbol).history(period="5d")
    except Exception as exc:  # noqa: BLE001
        log.warning("yfinance failed for %s: %s", symbol, exc)
        return None
    closes = hist.get("Close")
    if closes is None or len(closes) < 2:
        return None
    last = float(closes.iloc[-1])
    prev = float(closes.iloc[-2])
    if prev == 0:
        return None
    return last, (last - prev) / prev * 100.0


@register_source("stocks")
class StocksSource(Source):
    label = "Markets"

    def fetch(self) -> list[Story]:
        indices = self.params.get("indices", [])
        watchlist = self.params.get("watchlist", [])
        today = dt.datetime.now()

        index_lines: list[str] = []
        for sym in indices:
            move = _pct_move(sym)
            if not move:
                continue
            last, pct = move
            name = _INDEX_NAMES.get(sym, sym)
            index_lines.append(f"{name}: {last:,.0f} ({pct:+.2f}%)")

        mover_lines: list[tuple[str, float]] = []
        for sym in watchlist:
            move = _pct_move(sym)
            if not move:
                continue
            _, pct = move
            mover_lines.append((sym, pct))

        stories: list[Story] = []
        if index_lines:
            stories.append(
                Story(
                    title="Index moves",
                    body="; ".join(index_lines),
                    published_at=today,
                    source=self.label,
                )
            )
        if mover_lines:
            # Sort by absolute move so the biggest swings lead.
            mover_lines.sort(key=lambda x: abs(x[1]), reverse=True)
            body = "; ".join(f"{sym} {pct:+.2f}%" for sym, pct in mover_lines)
            stories.append(
                Story(
                    title="Watchlist moves",
                    body=body,
                    published_at=today,
                    source=self.label,
                    extra={"movers": mover_lines},
                )
            )
        log.info("Stocks: %d summary story(ies)", len(stories))
        return stories
