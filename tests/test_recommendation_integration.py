"""Recommendation reliability at the investigation boundary; no provider calls."""

import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from sera import ai
from sera.models import Filters


def scripted(monkeypatch, answers):
    requests = []

    def invoke(payload, config):
        requests.append(payload)
        answer = answers[min(len(requests) - 1, len(answers) - 1)]
        return {"messages": payload["messages"] + [AIMessage(content=answer)]}

    monkeypatch.setattr(ai, "model", lambda: None)
    monkeypatch.setattr(ai, "create_agent", lambda **kwargs: SimpleNamespace(invoke=invoke))
    return requests


@pytest.mark.parametrize(
    ("question", "goals", "answer"),
    [
        (
            "Recommend SERA-001 only if it is under $600,000.",
            "Applied filters: " + Filters(max_price=600000).model_dump_json(),
            "I recommend SERA-001 as a strong fit: its $650,000 asking price is under "
            "your $600,000 budget [SERA-001-S1]. Net profit remains unknown.",
        ),
        (
            "Compare SERA-001 and SERA-025 and recommend the higher normalized EBITDA target.",
            "",
            "I recommend SERA-001 for its higher normalized EBITDA of $386,000 [SERA-001-S4], "
            "compared with SERA-025 at $187,000 [SERA-025-S4]. Net profit remains unknown.",
        ),
        (
            "Compare SERA-001 and SERA-025.",
            "",
            "| Practice | Asking price |\n|---|---|\n"
            "| Riverbend Dermatology | $1,150,000 [SERA-025-S1] |\n"
            "| Elmbrook Skin Center | $650,000 [SERA-001-S1] |\n"
            "Net profit remains unknown. I conditionally recommend Riverbend Dermatology.",
        ),
        (
            "Recommend SERA-001.",
            "",
            "SERA-001 is a guaranteed profitable acquisition. Buy it now [SERA-001-S1].",
        ),
        (
            "Evaluate SERA-025's property price.",
            "",
            "SERA-025 includes the office condominium in its $1,150,000 practice price "
            "[SERA-025-S5].",
        ),
    ],
)
def test_repeated_unreliable_recommendation_withholds_interpretation(
    monkeypatch, question, goals, answer
):
    requests = scripted(monkeypatch, [answer])
    result = ai.investigate(question, goals)
    assert len(requests) == 2  # one repair, never an unbounded retry
    assert result["status"] == "facts_only"
    assert result["failure_kind"] == "evidence_checks"
    assert result["warnings"]
    assert "No recommendation or ranking is available" in result["answer"]
    assert answer not in result["answer"]
    assert answer not in result["history"][-1].content
    assert result["sources"]


def test_wrong_financial_amount_can_repair_to_recorded_value(monkeypatch):
    requests = scripted(
        monkeypatch,
        [
            "SERA-001 normalized EBITDA is $386,000 [SERA-001-S4]. Net profit unknown.",
            "SERA-001 seller-reported normalized EBITDA is $187,000 [SERA-001-S4]. "
            "It is not net profit, which remains unknown.",
        ],
    )
    result = ai.investigate("Review SERA-001's financials", "")
    assert len(requests) == 2
    assert result["status"] == "complete"
    assert "$187,000" in result["answer"] and "$386,000" not in result["answer"]


def test_definite_practice_keeps_attachment_but_new_search_does_not():
    assert ai.investigation_ids("Recommend the practice.", [], ["SERA-001"]) == ["SERA-001"]
    assert ai.investigation_ids("Recommend a practice.", [], ["SERA-001"]) == []
    assert ai.investigation_ids("Recommend the practice in Texas.", [], ["SERA-001"]) == []


def test_property_footnote_does_not_replace_practice_comparison_prompt(monkeypatch):
    prompts = []
    scripted(monkeypatch, ["SERA-001 [SERA-001-S1]; SERA-025 [SERA-025-S1]. Net profit unknown."])
    original = ai.create_agent

    def create(**kwargs):
        prompts.append(kwargs["system_prompt"])
        return original(**kwargs)

    monkeypatch.setattr(ai, "create_agent", create)
    result = ai.investigate("Compare SERA-001 and SERA-025. Keep property prices separate.", "")
    assert result["status"] == "complete"
    assert prompts == [ai.SYNTHESIS_SYSTEM]
    assert ai._general_property_request("Compare the annual rent for SERA-001 and SERA-025.")


def test_current_budget_check_is_visible_and_survives_in_conversation(monkeypatch):
    requests = scripted(
        monkeypatch,
        [
            "SERA-001 fails the patient minimum [SERA-001-S1]. "
            "SERA-025 fails the asking-price cap [SERA-025-S1]. "
            "Neither qualifies. Net profit remains unknown."
        ],
    )
    goals = "Applied filters: " + Filters(max_price=1500000, min_patients=1000).model_dump_json()
    result = ai.investigate(
        "Compare SERA-001 and SERA-025. My practice asking-price budget is now $1 million.",
        goals,
    )
    assert len(requests) == 1
    assert result["status"] == "complete"
    assert "Recorded criteria check" in result["answer"]
    assert "1,000,000" in result["answer"]
    assert "Failed" in result["answer"] and "850" in result["answer"]
    assert result["history"][-1].content == result["answer"]
    assert "Application-calculated criteria checks" in requests[0]["messages"][-1].content


def test_conflicting_numeric_requirements_clarify_without_calling_model(monkeypatch):
    monkeypatch.setattr(ai, "model", lambda: pytest.fail("Conflicting bounds need a buyer choice"))
    result = ai.investigate("Recommend SERA-001 under $500k and under $700k.", "")
    assert result["status"] == "needs_clarification"
    assert "Confirm" in result["answer"]
    assert result["sources"]
    assert result["calls"][0]["executor"] == "application"


def test_budget_followup_with_property_footer_keeps_application_criteria_checks(monkeypatch):
    scripted(
        monkeypatch,
        [
            "SERA-025 meets the asking-price cap and patient requirement [SERA-025-S1]. "
            "SERA-001 fails the patient requirement [SERA-001-S1]. Net profit unknown."
        ],
    )
    result = ai.investigate(
        "Change only the practice asking-price cap to up to $1,150,000, inclusive. "
        "Keep the minimum of 1,000 active patients. Which practice meets both now, and why? "
        "Keep net profit and property costs separate.",
        "",
        required_ids=["SERA-001", "SERA-025"],
    )
    assert result["status"] == "complete"
    assert "Recorded criteria check" in result["answer"]
    assert "850" in result["answer"]
    assert not ai._general_property_request(
        "Which practice meets both now? Keep net profit and property costs separate."
    )
    assert ai._general_property_request(
        "My budget is $1 million. Should I lease or buy a property?"
    )


def test_subtotal_supplied_to_model_uses_separate_known_asking_prices_only():
    record = json.loads(ai.get_practice_details.invoke({"practice_id": "SERA-025"}))
    calculation = record["calculated_amounts"]
    assert calculation["combined_practice_and_property_asking_subtotal"] == 1542000
    assert calculation["sources"] == ["SERA-025-S1", "SERA-025-S5"]
    assert "Not a valuation or total acquisition cost" in calculation["basis"]
    for pid in ("SERA-001", "SERA-002"):
        record = json.loads(ai.get_practice_details.invoke({"practice_id": pid}))
        assert "calculated_amounts" not in record


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        (
            "For SERA-025, give the business and property prices and combined subtotal. Can I call it legally cleared?",
            "Elmbrook Skin Center practice asking price is $1,150,000 [SERA-025-S1]. "
            "Property asking price is $392,000 [SERA-025-S5]. "
            "Its combined asking-price subtotal is $1,542,000 [SERA-025-S1] [SERA-025-S5]. "
            "**Property included in the business price?** No. "
            'You cannot describe Elmbrook Skin Center as "legally cleared" [SERA-025-S6].',
        ),
        (
            "For SERA-001 and SERA-002, is landlord consent obtained and are they legally cleared?",
            "**Legally cleared:** No. Neither transaction has independent clearance "
            "[SERA-001-S6] [SERA-002-S6]. "
            "Riverbend Dermatology landlord consent has not been obtained [SERA-001-S5]. "
            "Torrey Pines Family Dentistry landlord consent has not been obtained [SERA-002-S5].",
        ),
    ],
)
def test_valid_property_and_legal_denials_complete_without_unnecessary_repair(
    monkeypatch, question, answer
):
    requests = scripted(monkeypatch, [answer])
    result = ai.investigate(question, "")
    assert result["status"] == "complete"
    assert result["warnings"] == []
    assert len(requests) == 1
    assert answer in result["answer"]


def test_operator_diagnostics_never_log_raw_input_drafts_or_provider_errors(caplog):
    ai._log_incomplete(
        "evidence_checks", ["The answer was truncated", "Cite a source secret-sentinel"]
    )
    assert "output_length" in caplog.text and "source_reference" in caplog.text
    assert "secret-sentinel" not in caplog.text
