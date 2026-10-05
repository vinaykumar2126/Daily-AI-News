This feed is not a ranking problem. The stocks source emits a small fixed set of summary rows —
typically one for the index moves and one for the watchlist — and the listener wants all of them.

Significance ladder for a markets segment (highest priority first):
1. Index moves (S&P 500, Nasdaq, Dow).
2. Watchlist moves (the listener's own tickers).
3. Anything else the source supplied, in the order it came.

**Normally you should select EVERY candidate, in that order.** When there are fewer candidates than
`max_stories` there is nothing to trim, and returning a short list — or an empty one — is wrong:
an empty selection is treated as a failure upstream and throws the whole segment onto a fallback
curator. If every candidate is a legitimate market summary, return every index.

Only drop a candidate here if it is genuinely not market data — an advertisement, a duplicate of a
row already selected, or a row with no numbers in it at all.

Do not call fetch_article for this feed. The numbers in the source are the whole story, and there is
nothing to verify in an index summary.

--- EXAMPLE (illustrative — a Markets segment, max_stories 4) ---
Candidates:
0. Index moves — S&P 500: 7,723 (+0.73%); Nasdaq Composite: 27,191 (+1.19%); Dow Jones: 51,177 (+0.49%)
1. Watchlist moves — GOOGL +1.56%; NVDA +1.34%; AMZN +1.33%; AAPL +1.02%; MSFT +0.92%

Correct output:
{"selected": [0, 1], "notes": {}}

Why (reasoning — do NOT output it): both rows are market data the listener asked for, and two is
under the cap of four, so nothing is trimmed. Selecting only one — or none, on the grounds that
there was "no ranking to do" — would silently drop half the segment.
--- END EXAMPLE ---
