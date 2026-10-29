"""Conversation regression tests for the phone-call agent.

The other evals grade the morning script. This one grades what the agent says once the listener
starts talking back: asking for comparisons the sources don't make, "correcting" a fact with a
wrong number, interrupting mid-sentence. Each case in evals/conversations/*.yaml is a frozen
knowledge doc plus a scripted call; the listener's lines are fixed, the agent's replies are
generated fresh from agent/prompts/anchor.md, and every generated reply is graded two ways:

  numbers_grounded — code-only: every number it says must appear in the knowledge or the call
  criteria         — LLM judge (temperature 0): pass/fail on the case's written rules

LLM replies vary run to run, so each case runs several times and reports a pass rate. The run
exits non-zero if any case falls below --min-pass-rate, so it can gate a prompt or model change.

    python -m evals.conversation                     # all cases, 5 runs each
    python -m evals.conversation --case wrong-correction-40b --runs 1 -v

Approximation, on purpose: the live call runs inside ElevenLabs, whose own model and retrieval
we can't replay locally. This replays the same persona prompt and knowledge through Gemini, so it
tests the instructions, not ElevenLabs' runtime. An interrupted agent turn is replayed the way
ElevenLabs records it — cut off at what was played, ending in "...".
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from config import Config, load_dotenv
from evals.numbers import check_numbers_grounded

log = logging.getLogger("daily-news.evals.conversation")

CASES_DIR = Path(__file__).resolve().parent / "conversations"
_ANCHOR = Path(__file__).resolve().parent.parent / "agent" / "prompts" / "anchor.md"

# The judge must give the same reading twice; the agent should vary like it does on a real call.
_JUDGE_CONFIG = {"response_mime_type": "application/json", "temperature": 0.0}

# Gemini wants the conversation to open on a user turn; on a real call the agent speaks first.
_CALL_CONNECTED = "(The call has connected.)"

_JUDGE_PROMPT = """You are grading one reply from a voice agent on a live phone call. The agent
must only state facts found in its KNOWLEDGE. Grade the AGENT REPLY against each CRITERION, using
the knowledge and the conversation so far. A criterion passes only if the reply clearly meets it.

Respond ONLY with JSON of this exact shape:
{{"criteria": [{{"id": <int>, "pass": <true|false>, "reason": "<one sentence>"}}]}}

KNOWLEDGE:
{knowledge}

CONVERSATION SO FAR:
{history}

AGENT REPLY:
{reply}

CRITERIA:
{criteria}
"""


@dataclass
class Turn:
    role: str  # "agent" | "listener"
    text: str = ""  # empty agent text = generate and grade this reply
    expect: list[str] = field(default_factory=list)


@dataclass
class Case:
    id: str
    rule: str
    knowledge: str
    turns: list[Turn]
    path: Path


def load_cases(names: list[str] | None = None) -> list[Case]:
    cases = []
    for path in sorted(CASES_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        if names and data["id"] not in names:
            continue
        turns = [Turn(t["role"], (t.get("text") or "").strip(), t.get("expect") or []) for t in data["turns"]]
        cases.append(Case(data["id"], data["rule"], data["knowledge"].strip(), turns, path))
    if names and len(cases) != len(set(names)):
        missing = set(names) - {c.id for c in cases}
        raise SystemExit(f"unknown case(s): {', '.join(sorted(missing))}")
    return cases


def _system_prompt(knowledge: str) -> str:
    return f"{_ANCHOR.read_text().strip()}\n\n# Today's knowledge base\n\n{knowledge}"


def _format_history(history: list[tuple[str, str]]) -> str:
    return "\n".join(f"{'Agent' if r == 'agent' else 'Listener'}: {t}" for r, t in history) or "(none)"


class Runner:
    def __init__(self, cfg: Config, temperature: float) -> None:
        from google import genai

        self.cfg = cfg
        self.temperature = temperature
        self.client = genai.Client(vertexai=True, project=cfg.gcp_project, location=cfg.gemini_region)

    def agent_reply(self, case: Case, history: list[tuple[str, str]]) -> str:
        from google.genai import types

        contents = [types.Content(role="user", parts=[types.Part(text=_CALL_CONNECTED)])]
        for role, text in history:
            contents.append(
                types.Content(role="model" if role == "agent" else "user", parts=[types.Part(text=text)])
            )
        resp = self.client.models.generate_content(
            model=self.cfg.gemini_model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=_system_prompt(case.knowledge), temperature=self.temperature
            ),
        )
        return (resp.text or "").strip()

    def judge(self, case: Case, history: list[tuple[str, str]], reply: str, expect: list[str]) -> list[dict]:
        prompt = _JUDGE_PROMPT.format(
            knowledge=case.knowledge,
            history=_format_history(history),
            reply=reply,
            criteria="\n".join(f"{i}. {c}" for i, c in enumerate(expect, 1)),
        )
        try:
            resp = self.client.models.generate_content(
                model=self.cfg.gemini_model, contents=prompt, config=_JUDGE_CONFIG
            )
            graded = {int(c["id"]): c for c in json.loads(resp.text)["criteria"]}
        except Exception as exc:  # noqa: BLE001 — a broken judge must fail the run, not pass it
            log.warning("judge failed on %s: %s", case.id, exc)
            graded = {}
        return [
            {
                "criterion": text,
                "pass": bool(graded.get(i, {}).get("pass", False)),
                "reason": graded.get(i, {}).get("reason", "judge returned no verdict"),
            }
            for i, text in enumerate(expect, 1)
        ]

    def run_once(self, case: Case) -> dict:
        """Play the call once. Returns {passed, failures:[...], transcript:[...]}."""
        history: list[tuple[str, str]] = []
        failures: list[str] = []
        for turn in case.turns:
            if turn.role == "listener" or turn.text:
                history.append((turn.role, turn.text))
                continue
            reply = self.agent_reply(case, history)
            sources = [case.knowledge] + [t for _, t in history]
            numbers = check_numbers_grounded(reply, sources)
            if not numbers.passed:
                failures.append(f"turn {len(history) + 1}: {numbers.detail}")
            for row in self.judge(case, history, reply, turn.expect):
                if not row["pass"]:
                    failures.append(f"turn {len(history) + 1}: {row['criterion']} -> {row['reason']}")
            history.append(("agent", reply))
        return {"passed": not failures, "failures": failures, "transcript": history}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--case", action="append", help="run only this case id (repeatable)")
    ap.add_argument("--runs", type=int, default=5, help="plays per case (default 5)")
    ap.add_argument(
        "--min-pass-rate", type=float, default=1.0,
        help="fail if any case passes fewer than this share of runs (default 1.0 = every run)",
    )
    ap.add_argument("-v", "--verbose", action="store_true", help="print every generated transcript")
    args = ap.parse_args()

    load_dotenv()
    os.environ.setdefault("EVAL_MODE", "1")
    cfg = Config()
    # The live agent's temperature lives in ElevenLabs; 0.7 leans toward a chattier agent than
    # the judges so a run surfaces the slips a real call would.
    runner = Runner(cfg, float(os.environ.get("CONVO_EVAL_TEMPERATURE", "0.7")))

    worst = 1.0
    for case in load_cases(args.case):
        results = [runner.run_once(case) for _ in range(args.runs)]
        passes = sum(r["passed"] for r in results)
        rate = passes / len(results)
        worst = min(worst, rate)
        mark = "PASS" if rate >= args.min_pass_rate else "FAIL"
        print(f"{mark}  {case.id:<28} {passes}/{len(results)}   {case.rule}")
        for n, r in enumerate(results, 1):
            for f in r["failures"]:
                print(f"        run {n}: {f}")
            if args.verbose:
                for role, text in r["transcript"]:
                    print(f"        [{n}] {role:>8}: {text}")
                print()

    ok = worst >= args.min_pass_rate
    print(f"\n{'All cases passed' if ok else 'Some cases fell below'} the {args.min_pass_rate:.0%} bar.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
