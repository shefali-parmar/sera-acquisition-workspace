"""Supported criteria are checked from records, not inferred recommendation prose."""

import json

import pytest

from sera.catalog import load_practices, search
from sera.models import Filters
from sera.recommendation_fit import build_fit_context, fit_claim_issues, format_fit_context


@pytest.fixture
def records():
    return {p.id: p.model_dump() for p in load_practices()}


def goals(filters):
    return "Prefer a smooth transition.\nApplied filters: " + filters.model_dump_json()


def context(records, filters=None, question="Compare the selected candidates.", prior=None):
    return build_fit_context(
        {pid: records[pid] for pid in ["SERA-001", "SERA-025"]},
        goals(filters or Filters()),
        question,
        prior or [],
    )


def row(result, pid):
    return next(r for r in result["rows"] if r["practice_id"] == pid)


def test_real_catalog_strict_boundary_and_patient_minimum(records):
    filters = Filters(
        specialties=["Dermatology"],
        states=["CA"],
        max_price=650000,
        max_price_inclusive=False,
        min_patients=1000,
    )
    result = context(records, filters)
    river = row(result, "SERA-001")
    assert any("under $650,000" in label for label in river["failed"])
    assert any("recorded 850" in label for label in river["failed"])
    inclusive = context(records, filters.model_copy(update={"max_price_inclusive": True}))
    assert any("up to $650,000" in label for label in row(inclusive, "SERA-001")["matched"])
    assert len(row(inclusive, "SERA-001")["failed"]) == 1


@pytest.mark.parametrize(
    "question, expected, inclusive",
    [
        ("What if my asking-price budget drops to $1 million?", 1000000, True),
        ("Budget cap: 650000.", 650000, True),
        ("Keep the practice asking price below $650k.", 650000, False),
        ("Asking price < $650,000", 650000, False),
        ("At most $1.5m for the practice.", 1500000, True),
        ("Maximum budget $0", 0, True),
        ("$1.5 million asking-price budget", 1500000, True),
    ],
)
def test_narrow_current_price_expressions_override_snapshot(records, question, expected, inclusive):
    result = context(records, Filters(max_price=2000000), question)
    assert result["filters"]["max_price"] == expected
    assert result["filters"]["max_price_inclusive"] is inclusive


def test_latest_question_overrides_prior_wrappers_and_initial_filters(records):
    old = "Current buyer goals: under $5 million\nRequest: Under $900,000; at least 1,200 active patients.\nRequired practice IDs to retrieve with get_practice_details: ['SERA-001']"
    result = context(
        records, Filters(max_price=2000000), "Up to $1 million; minimum 1,000 patients.", [old]
    )
    assert result["filters"]["max_price"] == 1000000
    assert result["filters"]["max_price_inclusive"] is True
    assert result["filters"]["min_patients"] == 1000
    carried = context(records, Filters(max_price=2000000), "Which records should I request?", [old])
    assert carried["filters"]["max_price"] == 900000
    assert carried["filters"]["min_patients"] == 1200


def test_plain_legacy_goals_seed_only_supported_narrow_bounds(records):
    result = build_fit_context(
        {"SERA-001": records["SERA-001"]},
        "$1.5 million asking-price budget; at least 1000 patients",
        "Review Riverbend.",
        [],
    )
    assert result["filters"]["max_price"] == 1500000
    assert result["filters"]["min_patients"] == 1000
    assert row(result, "SERA-001")["failed"]
    unsupported = build_fit_context(
        {"SERA-001": records["SERA-001"]},
        "California dermatology with excellent growth potential",
        "Review Riverbend.",
        [],
    )
    assert unsupported["filters"] is None


def test_preferences_do_not_become_patient_or_price_requirements(records):
    result = context(
        records,
        Filters(max_price=1500000),
        "I prefer at least 2,000 active patients and ideally under $500k.",
    )
    assert result["filters"]["min_patients"] == 0
    assert result["filters"]["max_price"] == 1500000
    hard = context(
        records, Filters(), "I prefer leased premises, but require at least 1,000 active patients."
    )
    assert hard["filters"]["min_patients"] == 1000


def test_missing_price_is_unverified_even_when_discovery_allows_it(records):
    result = build_fit_context(
        {"SERA-002": records["SERA-002"]},
        goals(Filters(max_price=1000000, include_undisclosed=True)),
        "Review the target.",
        [],
    )
    torrey = row(result, "SERA-002")
    assert torrey["unverified"] == ["Budget unverified — asking price undisclosed"]
    assert not torrey["failed"]
    assert fit_claim_issues("Torrey Pines Family Dentistry is within your budget.", result)


@pytest.mark.parametrize(
    "question",
    [
        "Under $1m and under $2m.",
        "At least 1,000 active patients and minimum 2,000 patients.",
        "Property budget $500,000.",
    ],
)
def test_conflicting_or_ambiguous_scope_requires_clarification(records, question):
    result = context(records, Filters(max_price=1500000), question)
    assert result["clarification"]
    assert fit_claim_issues("Riverbend Dermatology meets all requirements.", result)


def test_explicit_combined_budget_is_not_misapplied_as_practice_cap(records):
    result = context(
        records,
        Filters(max_price=1000000),
        "Can I buy Elmbrook's practice and property for a combined budget of $1.5m?",
    )
    assert not result["clarification"]
    assert result["filters"]["max_price"] is None
    assert result["notes"]
    assert not any("Asking price" in label for label in row(result, "SERA-025")["failed"])


def test_supported_criteria_agree_with_deterministic_search(records):
    filters = Filters(
        specialties=["Dermatology"],
        states=["CA"],
        max_price=1500000,
        min_patients=1000,
        min_years=10,
        min_sqft=1000,
        keyword="digital",
    )
    result = build_fit_context(records, goals(filters), "Review all supplied records.", [])
    fitting = {r["practice_id"] for r in result["rows"] if not r["failed"] and not r["unverified"]}
    assert fitting == {p.id for p in search(load_practices(), filters)} == {"SERA-025"}
    radius = Filters(
        distance_origin="95814", max_distance_miles=100, states=["AK"], city="Atlantis"
    )
    result = build_fit_context(records, goals(radius), "Compare supplied records.", [])
    fitting = {r["practice_id"] for r in result["rows"] if not r["failed"] and not r["unverified"]}
    assert fitting == {p.id for p in search(load_practices(), radius)}


def test_absent_supported_facts_are_unverified_not_known_failures(records):
    record = dict(
        records["SERA-001"], active_patients=None, founding_year=None, operatories=None, sqft=None
    )
    result = build_fit_context(
        {"SERA-001": record},
        goals(Filters(min_patients=1000, min_years=10, min_sqft=100, min_operatories=2)),
        "Review.",
        [],
    )
    assert not result["rows"][0]["failed"]
    assert len(result["rows"][0]["unverified"]) == 4


@pytest.mark.parametrize(
    "answer",
    [
        "Riverbend Dermatology meets all requirements.",
        "Riverbend Dermatology qualifies.",
        "I recommend Riverbend Dermatology as the acquisition target.",
        "Riverbend Dermatology is within your budget.",
    ],
)
def test_positive_contradicted_claims_are_rejected(records, answer):
    result = context(
        records, Filters(max_price=650000, max_price_inclusive=False, min_patients=1000)
    )
    assert fit_claim_issues(answer, result)


@pytest.mark.parametrize(
    "answer",
    [
        "Riverbend Dermatology does not meet all requirements.",
        "I do not recommend Riverbend Dermatology.",
        "Riverbend Dermatology is not within your budget.",
        "If you raise the cap, Riverbend Dermatology could qualify.",
        "I recommend reviewing Riverbend Dermatology's patient records.",
        "Riverbend Dermatology fails the patient minimum, whereas Elmbrook Skin Center meets all requirements.",
    ],
)
def test_negation_conditional_and_cross_candidate_contrasts_are_not_false_positives(
    records, answer
):
    result = context(records, Filters(max_price=1500000, min_patients=1000))
    if "budget" in answer:
        result = context(records, Filters(max_price=650000, max_price_inclusive=False))
    assert fit_claim_issues(answer, result) == []


def test_true_budget_fit_is_not_rejected_because_another_criterion_fails(records):
    result = context(records, Filters(max_price=1000000, min_patients=1000))
    assert (
        fit_claim_issues(
            "Riverbend Dermatology is within your budget but fails the patient minimum.", result
        )
        == []
    )


def test_last_structured_snapshot_is_authoritative_and_invalid_snapshot_not_silently_defaulted(
    records,
):
    initial = (
        "Applied filters: {}\nSome buyer text\nApplied filters: "
        + Filters(max_price=0).model_dump_json()
    )
    result = build_fit_context(records, initial, "Review.", [])
    assert result["filters"]["max_price"] == 0
    invalid = build_fit_context(records, 'Applied filters: {"max_price":-1}', "Review.", [])
    assert invalid["filters"] is None
    assert invalid["clarification"]


def test_visible_check_names_boundaries_and_does_not_claim_overall_verification(records):
    result = context(
        records, Filters(max_price=650000, max_price_inclusive=False, min_patients=1000)
    )
    rendered = format_fit_context(result)
    assert "Riverbend Dermatology" in rendered
    assert "Failed:" in rendered and "850" in rendered
    assert "under \\$650,000" in rendered
    assert "Asking-price checks exclude property price and total acquisition costs" in rendered
    assert "not overall fit or independent verification" in rendered
    assert "100%" not in rendered
    assert json.loads(json.dumps(result)) == result


@pytest.mark.parametrize(
    "question",
    [
        "Under 1,000 patients.",
        "< 1000 patients.",
        "At most 3 practices.",
        "Under 10 years operating.",
        "Maximum 4 providers.",
    ],
)
def test_non_monetary_comparisons_never_become_price_caps(records, question):
    result = context(records, Filters(max_price=1500000), question)
    assert result["filters"]["max_price"] == 1500000
    assert not result["clarification"]


def test_explicit_price_cap_survives_property_separation_footer(records):
    result = context(
        records,
        Filters(max_price=2000000),
        "Asking price strictly under $1,150,000. Keep business and property prices separate; total costs are not established.",
    )
    assert result["filters"]["max_price"] == 1150000
    assert result["filters"]["max_price_inclusive"] is False
    assert not result["clarification"]


@pytest.mark.parametrize(
    "answer",
    [
        "I recommend Riverbend Dermatology within your budget, conditional on due diligence.",
        "Riverbend Dermatology qualifies subject to diligence.",
        "Riverbend Dermatology meets all requirements if due diligence is completed.",
    ],
)
def test_diligence_caveats_cannot_excuse_known_price_failures(records, answer):
    result = context(records, Filters(max_price=600000))
    assert fit_claim_issues(answer, result)


def test_explicit_hypothetical_cap_change_is_not_a_current_fit_claim(records):
    result = context(records, Filters(max_price=600000))
    assert (
        fit_claim_issues(
            "If the budget is raised to $700,000, Riverbend Dermatology could qualify.", result
        )
        == []
    )


def test_no_empty_fit_banner_without_assessed_criteria(records):
    result = build_fit_context(
        {"SERA-001": records["SERA-001"]}, "Prefer a good transition.", "Review.", []
    )
    assert result["filters"] is None
    assert format_fit_context(result) == ""


@pytest.mark.parametrize(
    "question",
    [
        "My practice asking-price budget is now $1 million.",
        "My asking-price budget now $1m.",
        "Lower cap to $1m.",
    ],
)
def test_common_budget_change_wording(records, question):
    result = context(records, Filters(max_price=2000000), question)
    assert result["filters"]["max_price"] == 1000000


def test_named_money_budget_claim_does_not_escape_known_failure(records):
    result = context(records, Filters(max_price=600000))
    assert fit_claim_issues(
        "Riverbend Dermatology is within your $600k budget, subject to diligence.", result
    )


def test_new_price_cannot_hide_invalid_original_filter_snapshot(records):
    result = build_fit_context(
        records, 'Applied filters: {"states":["XX"]}', "My budget is now $1m.", []
    )
    assert result["clarification"]


@pytest.mark.parametrize(
    "question",
    [
        "Annual revenue under $1m.",
        "Normalized EBITDA below $300k.",
        "Annual rent under $50k.",
        "Revenue must be at most $1 million.",
        "Base rent budget $50,000.",
    ],
)
def test_named_operating_metrics_do_not_become_asking_price_caps(records, question):
    result = context(records, Filters(max_price=1500000), question)
    assert result["filters"]["max_price"] == 1500000
    assert not result["clarification"]


def test_operating_metric_exclusion_preserves_separate_explicit_price_change(records):
    result = context(
        records,
        Filters(max_price=1500000),
        "Annual revenue under $1m; practice asking-price budget is now $900k.",
    )
    assert result["filters"]["max_price"] == 900000


def test_prior_hypothetical_is_not_a_permanent_budget_override(records):
    scenario = "If my budget were up to $700k, would Riverbend fit?"
    current_scenario = context(records, Filters(max_price=600000), scenario)
    assert current_scenario["filters"]["max_price"] == 700000
    later = context(records, Filters(max_price=600000), "Continue the comparison.", [scenario])
    assert later["filters"]["max_price"] == 600000
    actual_change = context(
        records,
        Filters(max_price=600000),
        "Continue the comparison.",
        ["My practice asking-price budget is now $700k."],
    )
    assert actual_change["filters"]["max_price"] == 700000


@pytest.mark.parametrize(
    "answer",
    [
        "Elmbrook Skin Center fails the asking-price cap.",
        "Elmbrook Skin Center is above your budget.",
        "Elmbrook Skin Center does not meet the price cap.",
        "Neither meets the asking-price budget.",
        "No candidate fits the price cap.",
    ],
)
def test_false_budget_failures_are_rejected(records, answer):
    result = context(records, Filters(max_price=1200000))
    assert fit_claim_issues(answer, result)


@pytest.mark.parametrize(
    "answer",
    [
        "Elmbrook Skin Center does not fail the asking-price cap.",
        "Elmbrook Skin Center is not above your budget.",
        "Neither qualifies for all buyer requirements.",
        "Neither meets all hard requirements.",
    ],
)
def test_negated_failures_and_unmodeled_global_requirements_are_not_rejected(records, answer):
    result = context(records, Filters(max_price=1200000))
    assert fit_claim_issues(answer, result) == []
