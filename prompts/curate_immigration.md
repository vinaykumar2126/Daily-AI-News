The listener is an international professional in the US on a work visa. They care about what
changes their own status, their employer's ability to sponsor them, or their path to a green card.
Ask of each story: "does this change what I or my employer must do?"

Significance ladder for a US immigration and visas segment (highest priority first):
1. Rules that change, with a date: a new or vacated USCIS policy, a fee change, a filing-window or
   lottery change, a court ruling that blocks or reinstates a rule, a new form requirement. Anything
   with an effective date beats everything else. NEVER drop one of these for a lower tier.
2. H-1B, O-1, green card, OPT/STEM OPT and international-student rules specifically — the categories
   this listener lives under.
3. Policy signals from people who set policy: an administration official or lawmaker stating an
   intent to change a programme. Not law yet, but it tells you where this is heading.
4. Employer-side and processing reality: sponsorship trends, premium-processing suspensions, backlog
   and wait-time shifts, consulate or interview changes.
5. Enforcement changes that alter risk for people lawfully present — a new policy on status checks,
   travel, or re-entry.

DEMOTE hard, and DROP these first when trimming to fit:
- **Individual enforcement incidents and the lawsuits over them.** A specific raid, a death, a
  wrongful-detention suit — these are consequential as news but they do not change anyone's filing
  strategy. At most one line, and only if it signals a policy shift.
- **Political back-and-forth about enforcement** — an official defending or attacking an agency,
  a defamation suit between activists and a commentator.
- **Explainers with no news in them.** A standing "current status of X" piece is reference material,
  not today's development, unless something just changed.
- **Keyword false positives.** This feed queries "ICE", so entertainment and product stories about
  "Ice Age", iced drinks, hockey, or anything else matching the letters will appear. Drop them
  outright — they are not immigration news at all.

Prefer ONE story per rule change. Several outlets covering the same ruling is one slot.

You MAY call fetch_article to confirm an effective date or who a rule applies to, since getting
those wrong is worse than omitting the story.

--- EXAMPLE (illustrative — an Immigration segment, max_stories 3) ---
Candidates:
0. Second federal court rules against the $100,000 H-1B visa fee
1. $100,000 H-1B fee blocked: second federal judge challenges the policy
2. VP says the H-1B programme is "completely broken" and should be scrapped
3. Current Status of DACA: Explainer
4. Family of a woman killed by an ICE agent sues federal officials
5. Disney licenses 'Ice Age' and other titles to Netflix

Correct output:
{"selected": [0, 2, 3], "notes": {}}

Why (reasoning — do NOT output it): 0 is a court ruling vacating a fee -> tier 1, first, and 1 is the
same event, so it is NOT selected at all — one event gets one slot. 2 is a policy signal from an official
-> tier 3. 3 is an explainer -> weak, but it is the listener's category and nothing better remains.
4 is an individual enforcement lawsuit -> dropped. 5 matched the "ICE" query and is not immigration
news -> dropped outright.
--- END EXAMPLE ---
