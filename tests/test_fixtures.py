"""Smoke tests — fixtures load and basic graders behave as expected.

No network. No model. These guard against packaging accidents (missing
fixture data, broken imports).
"""

from __future__ import annotations

from lucebench import __version__
from lucebench.areas import ds4_eval, humaneval


def test_version_exposed():
    assert isinstance(__version__, str)
    assert __version__.count(".") >= 1


def test_ds4_eval_cases_load():
    cases = ds4_eval.load_ds4_eval_cases()
    assert len(cases) >= 90, f"expected ~92 ds4-eval cases, got {len(cases)}"
    sources = {c["source"] for c in cases}
    # All four canonical ds4 source families should be present.
    assert {"GPQA Diamond", "SuperGPQA", "AIME2025", "COMPSEC"} <= sources, sources


def test_ds4_eval_cases_have_required_fields():
    for c in ds4_eval.load_ds4_eval_cases():
        assert "id" in c, c
        assert "source" in c, c
        assert "answer" in c, c
        assert "kind" in c, c


def test_humaneval_cases_load():
    cases = humaneval.load_humaneval_cases()
    assert len(cases) >= 5, f"expected at least 5 HumanEval cases, got {len(cases)}"
    for c in cases:
        assert c["area"] == "code"
        assert c["kind"] == "code-completion"
        assert "prompt" in c


def test_grade_ds4_choice_pass():
    case = {"id": "x", "source": "GPQA Diamond", "kind": "choice",
            "answer": "B", "choices": ["A1", "A2", "A3", "A4"]}
    row = {"content": "I think the answer is B because...\nAnswer: B"}
    g = ds4_eval.grade_case(case, row)
    assert g["pass"] is True
    assert g["given"] == "B"


def test_grade_ds4_integer_fail():
    case = {"id": "x", "source": "AIME2025", "kind": "integer", "answer": 42}
    row = {"content": "After computing it carefully, Answer: 41"}
    g = ds4_eval.grade_case(case, row)
    assert g["pass"] is False
    assert g["given"] == "41"


def test_grade_ds4_integer_pass():
    case = {"id": "x", "source": "AIME2025", "kind": "integer", "answer": 42}
    row = {"content": "Step 1...\nStep 2...\nAnswer: 42"}
    g = ds4_eval.grade_case(case, row)
    assert g["pass"] is True


def test_grade_ds4_format_error():
    case = {"id": "x", "source": "AIME2025", "kind": "integer", "answer": 42}
    row = {"content": "no useful content"}
    g = ds4_eval.grade_case(case, row)
    # No integer in text at all -> format error.
    assert g["pass"] is False
    assert g["status"] == "format_error"
    assert g["given"] == "?"


def test_grade_ds4_integer_unmarked_permissive():
    # antirez/ds4's find_ds4_integer_answer falls back to the last
    # integer in text if there's no "Answer:" marker. That's intentional —
    # tracks here so any future tightening doesn't silently regress.
    case = {"id": "x", "source": "AIME2025", "kind": "integer", "answer": 42}
    row = {"content": "I think it's 42 but I'm not sure."}
    g = ds4_eval.grade_case(case, row)
    assert g["given"] == "42"
    assert g["pass"] is True


def test_grade_humaneval_pass():
    case = {"id": "x", "area": "code", "kind": "code-completion",
            "prompt": "def add(a, b):\n    "}
    row = {"content": "return a + b\n"}
    g = humaneval.grade_humaneval_case(case, row)
    assert g["pass"] is True
    assert g["given"] == "parse_ok"


def test_grade_humaneval_fail():
    case = {"id": "x", "area": "code", "kind": "code-completion",
            "prompt": "def add(a, b):\n    "}
    row = {"content": "this is not python @@"}
    g = humaneval.grade_humaneval_case(case, row)
    assert g["pass"] is False
