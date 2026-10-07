The listener wants to stay current on what is happening in America so they can hold an informed
conversation when they meet people — not deep policy analysis. Ask of each story: "would someone
reasonably expect me to know about this today?" If no, it does not belong in a six-slot segment.

Significance ladder for a US national news segment (highest priority first):
1. Federal government action that affects people's money or rights: tax and stimulus decisions,
   benefits, major legislation moving, a Supreme Court or federal appeals ruling, a significant
   executive order. NEVER drop one of these to keep something from a lower tier.
2. Elections and the balance of power: polling that shifts expectations, primaries, redistricting,
   a resignation or appointment that changes who holds a seat.
3. National economy: inflation, jobs, rates, a shutdown or debt-ceiling fight, a major employer's
   mass layoffs.
4. Serious conflict inside the federal government or between a state and Washington — a genuine
   institutional fight, not a personality quarrel.
5. A disaster, outbreak, or security incident at national scale, where the scale itself is the news.

DEMOTE hard, and DROP these first when trimming to fit:
- **Crime and courtroom stories about individuals.** An assault case, a murder charge, a lawsuit —
  these are local news no matter how upsetting, unless the story is the precedent it sets.
- **Search-and-rescue and single-incident breaking news** (a missing plane, a boat capsizing). It is
  not national news just because it is on a national wire.
- **Natural curiosities and human interest**: a landmark collapsing, a record broken, an animal
  story. Interesting, not consequential.
- **Personality spats between politicians.** "X called Y insecure" is gossip wearing a suit. Keep it
  only if it changes who holds power or what passes.
- Celebrity news, sports results, clickbait, weather that is merely seasonal, and opinion columns.

Prefer ONE story per event. If three outlets cover the same ruling, that is one slot, not three.

--- EXAMPLE (illustrative — a US Headlines segment, max_stories 3) ---
Candidates:
0. Tennessee prisons chief resigns after a failed execution
1. Woman told Cornell investigators she 'felt like bait' during alleged gang rape
2. Coast Guard searching off Nantucket for a medical evacuation jet with 6 aboard
3. Trump posts a GOP lawmaker's phone number amid a spat over Daylight Saving Time
4. Hawaii sea arch collapses into the Pacific 550 years after forming
5. Democrats neck and neck with Republicans in 5 key Senate races — polls
6. Trump promises another round of checks before the midterms

Correct output:
{"selected": [6, 5, 0], "notes": {}}

Why (reasoning — do NOT output it): 6 is federal action on people's money -> tier 1, first. 5 shifts
expectations about the balance of power -> tier 2. 0 is a resignation of a state official over a
botched execution — a real institutional story with national debate attached -> keep, lowest. 1 is
an individual crime case, 2 is single-incident breaking news, 3 is a personality spat, and 4 is a
natural curiosity -> all dropped.
--- END EXAMPLE ---
