"""Evaluation plumbing tests do not call or score a live model."""

import json

from scripts.evaluate import check_fields, run_case
from sera.catalog import ROOT


def test_case_contracts():
    cases = json.loads((ROOT / "evaluation/cases.json").read_text())
    assert len(cases) == 11
    assert len({case["id"] for case in cases}) == 11
    assert all(case["request"] for case in cases)
    assert next(case for case in cases if case["id"] == "A04")["follow_up_to"] == "A03"


def test_field_checks_are_order_independent_and_detect_errors():
    assert check_fields({"states": ["CA", "TX"]}, {"states": ["TX", "CA"]}) == []
    assert check_fields({"max_price": 2000000}, {"max_price": 1500000})


def test_offline_runner_never_calls_ai(monkeypatch):
    from sera import ai

    def forbidden(*args, **kwargs):
        raise AssertionError("Offline runner attempted an AI call")

    monkeypatch.setattr(ai, "extract_filters", forbidden)
    monkeypatch.setattr(ai, "investigate", forbidden)
    cases = json.loads((ROOT / "evaluation/cases.json").read_text())
    results = [run_case(case, False, {}) for case in cases]
    assert [result["status"] for result in results] == ["passed"] * 5 + ["skipped"] * 6
