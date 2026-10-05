"""Quality check of the condition AI (plan 9.3): ~40 messages the dictionary may
not know, sent to ONE backend at a time, with what each should give.

    $env:PYTHONPATH = "src"
    .venv\\Scripts\\python.exe tmp\\condition_ai_smoke.py --backend local
    .venv\\Scripts\\python.exe tmp\\condition_ai_smoke.py --backend local --model qwen3:0.6b
    .venv\\Scripts\\python.exe tmp\\condition_ai_smoke.py --backend huggingface     # needs HF_TOKEN

Per message: the condition the AI named (or why it did not), the time, and a verdict
against `expect`: a word the name or a synonym should contain, "-" when nothing
should be identified, "?" when any plausible condition is fine (judge it yourself).
Summary: correct, wrong or invented names, invalid JSON / errors, mean time.
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from dataclasses import replace

from backend.ai import condition_ai
from backend.ai.conditions import _normalize, resolve_query
from backend.config import settings

# (message, expect)
CASES: list[tuple[str, str]] = [
    # paraphrases of a condition
    ("tiroida care merge prea repede", "hipertiroid"),
    ("tiroida lenta", "hipotiroid"),
    ("zahar mare in sange", "diabet"),
    ("tensiune mare", "hipertensiune"),
    ("inima bate neregulat", "aritmie"),
    ("pietre la rinichi", "litiaz"),
    ("durere de cap care vine si trece, cu greata si sensibilitate la lumina", "migren"),
    ("articulatiile umflate si dureroase dimineata", "artrit"),
    # other languages
    ("high blood pressure", "hipertensiune"),
    ("kidney stones", "litiaz"),
    ("irritable bowel syndrome", "colon iritabil"),
    ("hay fever", "alergi"),
    ("insomnia", "insomni"),
    # big typos
    ("hipertiroidizm", "hipertiroid"),
    ("diabeet zaharat", "diabet"),
    ("gastrita cronika", "gastrit"),
    ("artroza genunchilor", "artroz"),
    # popular names
    ("junghi la stomac", "?"),
    ("raceala", "rece"),
    ("bataturi la picior", "?"),
    ("cuperoza", "rozace"),
    # several segments
    ("hemoroizi, constipatie", "hemoroi"),
    ("tuse seaca, dureri in gat", "?"),
    ("ameteli, zgomote in urechi", "?"),
    # symptoms only: a plausible condition is expected
    ("am febra si tuse de 3 zile", "?"),
    ("ma doare burta si am diaree", "?"),
    ("obosesc repede, sunt palid si ametesc", "?"),
    ("mancarimi pe piele si pete rosii", "?"),
    ("nu pot sa adorm si sunt agitat", "?"),
    ("ma ustura cand urinez", "?"),
    ("dureri de spate dupa ce stau mult pe scaun", "?"),
    # no health problem: must stay unidentified
    ("ce plante sunt bune?", "-"),
    ("buna ziua", "-"),
    ("multumesc", "-"),
    ("cat costa o consultatie", "-"),
    ("vreau o reteta de prajitura", "-"),
    ("care e capitala Frantei", "-"),
    ("asdf qwerty", "-"),
    ("ce faci", "-"),
    ("vreau sa slabesc", "?"),
]


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("local", "huggingface"), default="local")
    parser.add_argument("--model", help="model name for the chosen backend (default: from the settings)")
    parser.add_argument("--timeout", type=int, default=60, help="seconds per request (default 60: the first local call loads the model)")
    args = parser.parse_args()

    overrides = {"condition_ai_backends": (args.backend,), "condition_ai_timeout_seconds": args.timeout}
    if args.model:
        overrides["condition_ai_local_model" if args.backend == "local" else "condition_ai_hf_model"] = args.model
    condition_ai.settings = replace(settings, **overrides)
    model = condition_ai._provider(args.backend).model
    print(f"backend={args.backend} model={model} messages={len(CASES)}\n")

    correct = wrong = failures = 0
    times: list[float] = []
    for message, expect in CASES:
        condition_ai.clear_cache()
        started = time.perf_counter()
        result = condition_ai.identify_conditions(resolve_query(message))
        elapsed = time.perf_counter() - started
        times.append(elapsed)
        names = "; ".join(f"{', '.join(answer['terms'])}" for answer in result.answers) or f"({result.reason})"
        if result.reason not in (condition_ai.IDENTIFIED, condition_ai.NONE):
            verdict, failures = "FAIL", failures + 1
        elif expect == "?":
            verdict = "judge" if result.identified else "none"
        elif expect == "-":
            ok = not result.identified
            verdict, correct, wrong = ("ok", correct + 1, wrong) if ok else ("WRONG", correct, wrong + 1)
        else:
            blob = _normalize(" ".join(term for answer in result.answers for term in answer["terms"]))
            ok = _normalize(expect) in blob
            verdict, correct, wrong = ("ok", correct + 1, wrong) if ok else ("WRONG", correct, wrong + 1)
        print(f"[{verdict:>5}] {elapsed:5.1f}s  {message!r}  ->  {names}")

    print(f"\nchecked: ok={correct} wrong={wrong}; failures (no valid JSON / unavailable)={failures}")
    print(f"time: mean={statistics.mean(times):.1f}s median={statistics.median(times):.1f}s max={max(times):.1f}s")
    print("'judge'/'none' rows (expected '?') need your own reading: is the condition plausible?")


if __name__ == "__main__":
    main()
