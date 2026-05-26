# luce-bench

Capability benchmarks for chat-completion endpoints. Sister of
[`luce-dflash`](https://github.com/luce-org/lucebox-hub)'s
`bench_http_capability.py`, extracted as a standalone PyPI package
so external users can `pip install luce-bench` and benchmark any
OpenAI-compatible endpoint.

**Status**: v0.2 — `ds4-eval`, `code`, `longctx`, `agent`, and
`forge` (tool-calling) areas landed; parallel execution + a
single-case multi-mode `lucebench-probe` CLI shipped. `swe-bench`
(verified-execution sandbox) is the remaining gap; not in scope for
the standalone bench package.

## Install

```bash
pip install luce-bench           # core, stdlib-only
pip install luce-bench[forge]    # + anthropic SDK for tool-calling eval
pip install luce-bench[dev]      # + pytest, ruff for contributors
```

Or with uv:

```bash
uv add luce-bench
```

## Quick start

```bash
# Run the ds4-eval-92 corpus against any OpenAI-compatible server
lucebench --url http://localhost:8080 --area ds4-eval --model my-model

# Single case, json-out for downstream analysis
lucebench --url http://localhost:8080 --area ds4-eval --case-id aime2025-02 \
  --json-out /tmp/aime02.json

# HumanEval-style code completion (10 prompts, decode-only parse check)
lucebench --url http://localhost:8080 --area code --model my-model

# Against OpenRouter with auth + sequential pacing
export OPENROUTER_API_KEY=sk-or-...
lucebench --url https://openrouter.ai/api --model qwen/qwen3.6-27b \
  --area ds4-eval --auth-env OPENROUTER_API_KEY --no-think
```

## What's benchmarked

| Area | Cases | Grader | Source |
|------|-------|--------|--------|
| `ds4-eval` | 92 (GPQA Diamond, SuperGPQA, AIME2025, COMPSEC) | strict `Answer: X` format extract | [antirez/ds4](https://github.com/antirez/ds4) (MIT) |
| `code` | 10 (mid-function completion) | `ast.parse(prompt + completion)` | [openai/human-eval](https://github.com/openai/human-eval) (MIT) port |
| `longctx` | 6 frontiers (2k → 64k tokens) | `^Risk:` prefix check | own ports |
| `agent` | N codex-style prompts paired with coding tasks | code-fence / json-tool / apply_patch detect | own ports |
| `forge` | 7+ tool-calling scenarios | error_type == None | [antoinezambelli/forge](https://github.com/antoinezambelli/forge) 0.7.1 (MIT) |

Each row in the result carries:

- `pass` (bool), `graded` (full grader output)
- `wall_seconds`, `http_status`, `error`
- `prompt_tokens`, `completion_tokens`, `timings` (when surfaced by the server)
- `content`, `reasoning_content`, `finish_reason`, `finish_details`

The default sampling shape is **send-nothing-explicit** — the server
gets to apply its own defaults (model card sampling, provider tuning,
etc). Passing `--temperature 0` would forcibly override that; bench
deliberately omits sampling fields unless the user sets them.

## Programmatic use

```python
from lucebench.areas import ds4_eval
from lucebench.runner import run_case

cases = ds4_eval.load_ds4_eval_cases()
case = next(c for c in cases if c["id"] == "aime2025-02")

row = run_case(
    url="http://localhost:8080",
    case=case,
    model="my-model",
    think=True,
)
graded = ds4_eval.grade_case(case, row)
print(graded["pass"], graded["given"], "/", graded["correct"])
```

## Why this exists

The luce-dflash project ships an internal bench harness with deep
integration into its model-card / thinking-budget machinery. That
makes the harness opinionated about which OpenAI fields to send and
which response fields to read. Most of those opinions are right for
OpenAI-shape endpoints in general — `luce-bench` carves the
provider-agnostic core out so other folks can use it without
adopting the dflash server.

## Attribution

This project redistributes evaluation fixtures from upstream MIT-
licensed projects. See `NOTICE` for full attribution; in short:

- ds4-eval cases — `antirez/ds4`, MIT
- HumanEval prompts — `openai/human-eval`, MIT
- forge eval scenarios (`[forge]` extra) — `antoinezambelli/forge`, MIT

The luce-bench code itself is Apache-2.0.

## Contributing

```bash
git clone https://github.com/easel/luce-bench
cd luce-bench
uv sync --extra dev
uv run pytest
uv run ruff check src tests
```

CI runs the same matrix on Python 3.10–3.13 + a wheel-build check
that verifies fixtures are bundled.
