"""Evaluation harness for the briefing pipeline.

  checks.py   — cheap, code-only quality gates (no LLM)
  judge.py    — LLM-as-judge quality scores (faithfulness / coverage / relevance / ...)
  run.py      — score one curator on a golden day, print a scorecard
  compare.py  — run both curators head-to-head on the same golden day
  capture.py  — snapshot today's real sources into a golden set for repeatable evals
  conversation.py — regression tests for the phone-call agent (pushback, corrections, interruptions)
  numbers.py  — code-only check that every number the agent says appears in its sources
"""
