"""Distance changes the location constraint while preserving deterministic eligibility."""

import json
from datetime import date

import pytest
from pydantic import ValidationError

from sera.catalog import load_practices, search
from sera.geography import distance_miles, resolve_origin
from sera.models import Filters
from sera.search_location import (
    optional_origin,
    origin_query,
    resolve_filter_origin,
    validate_distance_filters,
)


@pytest.fixture
def target():
    return load_practices()[0].model_copy(
        update={
            "id": "TARGET",
            "name": "Target practice",
            "city": "Boston",
            "state": "MA",
            "specialty": "Dermatology",
            "status": "Listed for sale",
            "asking_price": 500_000,
            "active_patients": 2000,
            "founding_year": 2000,
            "sqft": 2000,
            "operatories": 5,
            "description": "Digital records and an established patient panel.",
        }
    )


def test_explicit_zip_overrides_city_and_state_origin():
    filters = Filters(distance_origin="02108", city="New York", states=["NY"])
    assert origin_query(filters) == "02108"
    assert resolve_filter_origin(filters) == resolve_origin("02108")
    combined = filters.model_copy(update={"distance_origin": "Boston, MA 02108"})
    assert resolve_filter_origin(combined) == resolve_origin("02108")


def test_origin_falls_back_to_city_and_then_single_state():
    city = Filters(city=" Boston ", states=["MA"], max_distance_miles=100)
    assert origin_query(city) == "Boston, MA"
    assert resolve_filter_origin(city) == resolve_origin("Boston, MA")
    state = Filters(states=["MA"], max_distance_miles=100)
    assert origin_query(state) == "MA"
    assert validate_distance_filters(state) == resolve_origin("Massachusetts")
    assert origin_query(Filters(states=["MA", "RI"])) == ""
    assert resolve_filter_origin(Filters()) is None


def test_radius_crosses_city_and_state_boundaries(target):
    providence = target.model_copy(update={"id": "NEARBY", "city": "Providence", "state": "RI"})
    new_york = target.model_copy(update={"id": "FAR", "city": "New York", "state": "NY"})
    records = [target, providence, new_york]
    exact = Filters(city="Boston", states=["MA"])
    assert [practice.id for practice in search(records, exact)] == ["TARGET"]
    radius = exact.model_copy(update={"max_distance_miles": 60})
    assert [practice.id for practice in search(records, radius)] == ["TARGET", "NEARBY"]
    # An explicit ZIP takes precedence even when exact-location fields describe NY.
    zip_radius = Filters(
        distance_origin="02108", city="New York", states=["NY"], max_distance_miles=60
    )
    assert [practice.id for practice in search(records, zip_radius)] == ["TARGET", "NEARBY"]


@pytest.mark.parametrize(
    "change",
    [
        {"specialty": "Orthodontics"},
        {"status": "Availability unknown"},
        {"asking_price": 900_000},
        {"asking_price": None},
        {"active_patients": 999},
        {"active_patients": None},
        {"founding_year": date.today().year - 5},
        {"founding_year": None},
        {"sqft": 999},
        {"sqft": None},
        {"operatories": 2},
        {"operatories": None},
        {"description": "Paper records"},
    ],
)
def test_radius_preserves_every_other_hard_filter(target, change):
    nearby = target.model_copy(update={"city": "Providence", "state": "RI"})
    excluded = nearby.model_copy(update={"id": "EXCLUDED", **change})
    filters = Filters(
        city="Boston",
        states=["MA"],
        max_distance_miles=60,
        specialties=["Dermatology"],
        statuses=["Listed for sale"],
        max_price=800_000,
        min_patients=1000,
        min_years=10,
        min_sqft=1000,
        min_operatories=3,
        keyword="digital",
    )
    assert search([nearby, excluded], filters) == [nearby]


def test_radius_boundary_is_inclusive_without_rounding(target):
    nearby = target.model_copy(update={"city": "Providence", "state": "RI"})
    exact_distance = distance_miles(resolve_origin("Boston, MA"), nearby.city, nearby.state)
    assert exact_distance is not None and 35 < exact_distance < 55
    boundary = Filters(distance_origin="Boston, MA", max_distance_miles=exact_distance)
    assert search([nearby], boundary) == [nearby]
    just_outside = boundary.model_copy(update={"max_distance_miles": exact_distance - 0.000001})
    assert search([nearby], just_outside) == []


@pytest.mark.parametrize(
    "criteria",
    [
        {"distance_origin": "99999", "max_distance_miles": 100},
        {"distance_origin": "Atlantis, MA", "max_distance_miles": 100},
        {"city": "Springfield", "max_distance_miles": 100},
        {"states": ["MA", "RI"], "max_distance_miles": 100},
        {"max_distance_miles": 100},
        {"distance_origin": "99999"},
    ],
)
def test_invalid_or_missing_distance_origin_fails_closed(target, criteria):
    with pytest.raises(ValueError):
        search([target], Filters(**criteria))


def test_unknown_practice_city_is_excluded_from_radius(target):
    unknown = target.model_copy(update={"city": "Atlantis", "state": "MA"})
    assert search([unknown], Filters(distance_origin="Boston, MA", max_distance_miles=100)) == []


def test_exact_location_without_radius_does_not_require_geocoding(target):
    filters = Filters(city="Atlantis", states=["MA"])
    assert validate_distance_filters(filters) is None
    assert optional_origin(filters) is None
    assert search([target], filters) == []


@pytest.mark.parametrize("radius", [0, 0.5, -1, 10001, float("nan"), float("inf")])
def test_radius_has_safe_finite_positive_bounds(radius):
    with pytest.raises(ValidationError):
        Filters(distance_origin="02108", max_distance_miles=radius)


def test_legacy_filters_json_restores_exact_location_defaults():
    legacy_json = json.dumps({"states": ["CA"], "city": "Sacramento", "include_undisclosed": True})
    filters = Filters.model_validate_json(legacy_json)
    assert filters.distance_origin == ""
    assert filters.max_distance_miles is None
    records = load_practices()
    expected = [
        practice
        for practice in records
        if practice.city == "Sacramento"
        and practice.state == "CA"
        and practice.status in filters.statuses
    ]
    assert expected
    assert search(records, filters) == expected
    assert Filters.model_validate_json(filters.model_dump_json()) == filters
