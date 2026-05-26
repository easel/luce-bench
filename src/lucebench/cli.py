"""Command-line entry point: ``lucebench --area X --url Y --model Z``.

Minimal dispatcher around lucebench.runner. The full-featured
multi-area runner from luce-dflash (parallelism, forge, agent areas,
sampling-from-card, per-area max_tokens defaults) is the bigger
brother; this CLI exists so external users can `pip install
luce-bench` and benchmark any OpenAI-compatible endpoint.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from pathlib import Path
from typing import Any

from lucebench import __version__
from lucebench.areas import ds4_eval, humaneval
from lucebench.runner import run_case

AREAS = {
    "ds4-eval": {
        "load": ds4_eval.load_ds4_eval_cases,
        "grade": ds4_eval.grade_case,
        "default_max_tokens": ds4_eval.DS4_EVAL_MAX_TOKENS,
        "default_thinking": True,
    },
    "code": {
        "load": humaneval.load_humaneval_cases,
        "grade": humaneval.grade_humaneval_case,
        "default_max_tokens": 2048,
        "default_thinking": False,
    },
}


def select_cases(cases: list[dict], *, questions: int | None = None,
                 case_id: str | None = None,
                 case_index: int | None = None,
                 sources: list[str] | None = None) -> list[dict]:
    """Filter cases by id / index / source / count."""
    out = list(cases)
    if sources:
        out = [c for c in out if c.get("source") in sources]
    if case_id:
        out = [c for c in out if c.get("id") == case_id]
    if case_index is not None:
        out = out[case_index:case_index + 1] if 0 <= case_index < len(out) else []
    if questions:
        out = out[:questions]
    return out


def format_row(idx: int, row: dict, graded: dict) -> str:
    src = row.get("source") or "?"
    cid = row.get("case_id") or "?"
    verdict = "PASS" if graded.get("pass") else "FAIL"
    given = graded.get("given") or "?"
    correct = graded.get("correct") or "?"
    wall = row.get("wall_seconds") or 0
    timings = row.get("timings") or {}
    tps = timings.get("decode_tokens_per_sec") or 0
    return (f"  {idx:3d} {verdict} {src:14s} {cid:24s} "
            f"given={given:20s} correct={correct:20s} "
            f"wall={wall:.2f}s {tps:.0f}tps")


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="lucebench",
        description="Capability benchmarks for chat-completion endpoints.",
    )
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    ap.add_argument("--url", default="http://127.0.0.1:8080",
                    help="Server base URL (default: http://127.0.0.1:8080).")
    ap.add_argument("--model", default="default",
                    help="Model identifier sent in the request body.")
    ap.add_argument("--area", required=True, choices=sorted(AREAS),
                    help="Evaluation area to run.")
    ap.add_argument("--questions", type=int, default=None,
                    help="Limit to first N cases (after other filters).")
    ap.add_argument("--case-id", default=None,
                    help="Run only the case with this ID.")
    ap.add_argument("--case-index", type=int, default=None,
                    help="Run only the case at this position (after source filter).")
    ap.add_argument("--sources", default=None,
                    help="Comma-separated source filter (e.g. AIME2025,GPQA Diamond).")
    ap.add_argument("--max-tokens", type=int, default=None,
                    help="Per-request decode cap (overrides area default).")
    ap.add_argument("--think", dest="think", action="store_true", default=None)
    ap.add_argument("--no-think", dest="think", action="store_false")
    ap.add_argument("--temperature", type=float, default=None)
    ap.add_argument("--top-p", type=float, default=None)
    ap.add_argument("--top-k", type=int, default=None)
    ap.add_argument("--timeout", type=int, default=300,
                    help="Per-request wall timeout (s).")
    ap.add_argument("--auth-env", default=None,
                    help="Env var name to read auth bearer token from "
                         "(e.g. OPENAI_API_KEY, OPENROUTER_API_KEY).")
    ap.add_argument("--json-out", type=Path, default=None,
                    help="Write the per-case rows as a JSON array to this path.")
    args = ap.parse_args()

    cfg = AREAS[args.area]
    cases = cfg["load"]()
    sources = ([s.strip() for s in args.sources.split(",")]
               if args.sources else None)
    selected = select_cases(
        cases,
        questions=args.questions,
        case_id=args.case_id,
        case_index=args.case_index,
        sources=sources,
    )
    if not selected:
        ap.error("no cases selected by the supplied filters")

    max_tokens = args.max_tokens if args.max_tokens is not None else cfg["default_max_tokens"]
    think = args.think if args.think is not None else cfg["default_thinking"]

    auth_header = ""
    if args.auth_env:
        token = os.environ.get(args.auth_env, "")
        if not token:
            ap.error(f"--auth-env {args.auth_env}: env var is empty or unset")
        auth_header = f"Bearer {token}"

    print(f"[lucebench] v{__version__} area={args.area} cases={len(selected)} "
          f"url={args.url} model={args.model} think={think} max_tokens={max_tokens}",
          flush=True)

    rows: list[dict[str, Any]] = []
    for idx, case in enumerate(selected, start=1):
        row = run_case(
            url=args.url, case=case,
            timeout_s=args.timeout, max_tokens=max_tokens, think=think,
            model=args.model, auth_header=auth_header,
            temperature=args.temperature, top_p=args.top_p, top_k=args.top_k,
        )
        graded = cfg["grade"](case, row)
        row["pass"] = graded.get("pass", False)
        row["graded"] = graded
        rows.append(row)
        print(format_row(idx, row, graded), flush=True)

    pass_n = sum(1 for r in rows if r["pass"])
    rate = 100 * pass_n / len(rows) if rows else 0
    walls = [r.get("wall_seconds") or 0 for r in rows]
    print(f"\n[lucebench] pass_rate={rate:.2f}% ({pass_n}/{len(rows)}) "
          f"wall_total={sum(walls):.0f}s wall_median={statistics.median(walls):.1f}s",
          flush=True)

    if args.json_out:
        # Drop the raw _response blob from JSON-out by default to keep file size sane.
        terse = [{k: v for k, v in r.items() if k != "_response"} for r in rows]
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps({
            "lucebench_version": __version__,
            "area": args.area, "url": args.url, "model": args.model,
            "think": think, "max_tokens": max_tokens,
            "n": len(rows), "pass": pass_n, "pass_rate": rate,
            "rows": terse,
        }, indent=2))
        print(f"[lucebench] wrote {len(rows)} rows to {args.json_out}", flush=True)

    return 0 if pass_n == len(rows) or os.environ.get("LUCEBENCH_PASS_RATE_GATE") is None else 1


if __name__ == "__main__":
    sys.exit(main())
