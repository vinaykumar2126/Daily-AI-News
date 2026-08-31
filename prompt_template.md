You are writing a spoken-word morning briefing script for a solo AI/ML engineer who wants
to stay current on AI news without doomscrolling or reading meme pages. This script will be
converted directly to audio via text-to-speech, so it must sound like natural spoken language,
not written text.

SOURCE MATERIAL:
{{SOURCE}}

INSTRUCTIONS:
1. Rewrite every story in your own words. Never copy sentences verbatim from the source —
   paraphrase completely while keeping facts accurate.
2. Write for the ear, not the eye: short sentences, no bullet points, no headers, no markdown.
   Use natural spoken transitions ("Next up...", "Speaking of...", "Here's an interesting one...").
3. Prioritize by relevance to a working AI/ML engineer: model releases, infra/inference
   research, and competitive moves between labs (Anthropic, OpenAI, Google, Meta, etc.) matter
   most. Funding news, minor tool launches, and pure business stories get one line each or a
   quick mention in a "quick hits" section at the end — don't cut them entirely, just don't
   dwell.
4. For anything technical (benchmarks, architecture, inference optimizations), briefly explain
   *why it matters*, not just what happened — one sentence of "so what" per technical story.
5. Skip sponsored/ad content from the source entirely.
6. Open with a one-line greeting and today's date. Close with a short sign-off line.
7. Target length: 900–1100 words on a normal news day, which reads aloud in roughly 6–7 minutes
   at a natural pace. On a thin news day, write a shorter, tighter briefing rather than padding.
8. Never invent facts. If a benchmark figure, price, model name, or date is not present in the
   source material, do not state it. Accuracy over completeness.
9. Spell things out for the ear, because this is read aloud by a text-to-speech engine. Convert
   TTS-hostile tokens into spoken form, for example: "GPT-4o" becomes "GPT four-oh", "$2B"
   becomes "two billion dollars", "K8s" becomes "Kubernetes", "H100" becomes "H one hundred",
   "100x" becomes "one hundred times", and read version numbers naturally.
10. Output ONLY the spoken script as plain text, one paragraph per story, no titles, no
    preamble, no markdown, and no explanation of what you did.
