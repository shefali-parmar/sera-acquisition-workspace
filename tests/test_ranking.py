"""Relevance changes ordering only and exposes deterministic, bounded tradeoffs."""

from datetime import date

import pytest

from sera.catalog import load_practices, search
from sera.models import Filters
from sera.ranking import relevance_key, relevance_score


@pytest.fixture
def practice():
    return load_practices()[0]


def test_without_scoring_criteria_names_and_ids_break_ties(practice):
    alpha = practice.model_copy(update={"id": "A", "name": "alpha"})
    same_later = practice.model_copy(update={"id": "C", "name": "Same"})
    same_first = practice.model_copy(update={"id": "B", "name": "same"})
    filters = Filters(specialties=[practice.specialty], states=[practice.state])
    assert relevance_score(practice, filters) == 0
    assert sorted([same_later, alpha, same_first], key=lambda p: relevance_key(p, filters)) == [
        alpha,
        same_first,
        same_later,
    ]


def test_keyword_placement_ranks_exact_then_name_then_specialty_then_description(practice):
    variants = [
        practice.model_copy(update={"name": "Digital", "specialty": "Other", "description": ""}),
        practice.model_copy(
            update={"name": "Digital Valley", "specialty": "Other", "description": ""}
        ),
        practice.model_copy(
            update={"name": "Valley", "specialty": "Digital dentistry", "description": ""}
        ),
        practice.model_copy(
            update={"name": "Valley", "specialty": "Other", "description": "Digital records"}
        ),
    ]
    filters = Filters(keyword="  DIGITAL  ")
    assert [relevance_score(p, filters) for p in variants] == [1, 0.75, 0.5, 0.25]
    exact_specialty = practice.model_copy(update={"specialty": "Digital"})
    assert relevance_score(exact_specialty, filters) == 1
    partial_word = practice.model_copy(update={"name": "Digitalis", "description": ""})
    assert relevance_score(partial_word, filters) == 0.25


def test_budget_headroom_handles_known_zero_and_undisclosed_prices(practice):
    filters = Filters(max_price=1_000_000, include_undisclosed=True)
    zero, lower, capped, undisclosed = [
        practice.model_copy(update={"asking_price": price})
        for price in (0, 250_000, 1_000_000, None)
    ]
    assert [relevance_score(p, filters) for p in (zero, lower, capped, undisclosed)] == [
        1,
        0.75,
        0,
        0,
    ]
    assert relevance_score(zero, Filters(max_price=0)) == 1
    assert relevance_score(undisclosed, Filters(max_price=0)) == 0
    assert relevance_score(lower, Filters(max_price=0)) == 0


@pytest.mark.parametrize(
    ("filter_name", "record_name"),
    [("min_patients", "active_patients"), ("min_sqft", "sqft"), ("min_operatories", "operatories")],
)
def test_minimum_surplus_is_bounded_and_unknown_does_not_help(practice, filter_name, record_name):
    filters = Filters(**{filter_name: 10})
    for value, expected in [(None, 0), (5, 0), (10, 0), (15, 0.5), (20, 1), (100, 1)]:
        record = practice.model_copy(update={record_name: value})
        assert relevance_score(record, filters) == expected


def test_operating_years_uses_the_catalog_definition(practice):
    filters = Filters(min_years=10)
    for age, expected in [(10, 0), (15, 0.5), (20, 1), (30, 1)]:
        record = practice.model_copy(update={"founding_year": date.today().year - age})
        assert relevance_score(record, filters) == expected
    assert relevance_score(practice.model_copy(update={"founding_year": None}), filters) == 0


def test_components_have_equal_weight_and_unknowns_remain_in_denominator(practice):
    record = practice.model_copy(update={"asking_price": 250_000, "active_patients": 1500})
    filters = Filters(max_price=1_000_000, min_patients=1000)
    assert relevance_score(record, filters) == (0.75 + 0.5) / 2
    unknown = record.model_copy(update={"active_patients": None})
    assert relevance_score(unknown, filters) == 0.75 / 2


def test_proximity_only_counts_when_an_origin_was_resolved(practice):
    filters = Filters()
    assert relevance_score(practice, filters, distance=0) == 0
    assert relevance_score(practice, filters, distance=10000) == 0
    assert relevance_score(practice, filters, distance=0, has_origin=True) == 1
    assert relevance_score(practice, filters, distance=100, has_origin=True) == 0.5
    assert relevance_score(practice, filters, distance=200, has_origin=True) == pytest.approx(1 / 3)
    for invalid in (None, -1, float("nan"), float("inf")):
        assert relevance_score(practice, filters, distance=invalid, has_origin=True) == 0


def test_ordering_preserves_hard_matches_and_does_not_mutate_inputs():
    records = load_practices()
    filters = Filters(max_price=2_000_000, min_patients=1000, include_undisclosed=True)
    before = [p.model_dump() for p in records]
    filter_before = filters.model_dump()
    matches = search(records, filters)
    ranked = sorted(matches, key=lambda p: relevance_key(p, filters))
    assert {p.id for p in ranked} == {p.id for p in matches}
    assert [p.model_dump() for p in records] == before
    assert filters.model_dump() == filter_before
    assert all(0 <= relevance_score(p, filters) <= 1 for p in records)
    assert ranked == sorted(reversed(matches), key=lambda p: relevance_key(p, filters))


def test_no_priorities_or_outcome_judgments_enter_ranking(practice):
    # Revenue, EBITDA and legal disclosures are not search criteria or relevance signals.
    altered = practice.model_copy(
        update={"annual_revenue": 999_999_999, "legal_disclosures": "Unrelated interpretation"}
    )
    filters = Filters(max_price=5_000_000, min_patients=100)
    assert relevance_key(practice, filters) == relevance_key(altered, filters)
