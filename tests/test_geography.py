"""Real bundled Census coverage and distance behavior; no network or geocoder mocks."""

import json
import math

import pytest

from sera.catalog import load_practices
from sera.geography import (
    DATA_PATH,
    EARTH_RADIUS_MILES,
    Location,
    distance_miles,
    practice_location,
    resolve_origin,
)


def test_zip_preserves_leading_zero_and_takes_precedence():
    origin = resolve_origin("02108")
    assert origin.kind == "zip"
    assert origin.label == "ZIP 02108"
    assert 42 < origin.latitude < 43
    assert -72 < origin.longitude < -70
    assert resolve_origin("Boston, MA 02108") == origin
    assert resolve_origin("02108-1234") == origin


def test_city_state_and_state_full_names_resolve_identically():
    assert resolve_origin("Sacramento CA") == resolve_origin("Sacramento, California")
    assert resolve_origin(" ca ") == resolve_origin("California")
    assert resolve_origin("California").kind == "state"
    assert resolve_origin("District of Columbia").kind == "state"
    assert resolve_origin("Alaska").latitude > 60
    assert resolve_origin("Puerto Rico").latitude < 20


def test_unambiguous_city_and_catalog_common_names():
    assert resolve_origin("Albuquerque").label == "Albuquerque, NM"
    assert resolve_origin("Boise, ID").kind == "city"
    assert resolve_origin("Honolulu, HI").kind == "city"
    assert resolve_origin("Nashville, Tennessee").kind == "city"


@pytest.mark.parametrize("query", ["Portland", "Springfield", "Jacksonville, PA"])
def test_ambiguous_city_requires_clarification(query):
    with pytest.raises(ValueError, match="multiple places"):
        resolve_origin(query)


@pytest.mark.parametrize("query", ["", "  ", "99999", "1234", "Atlantis, CA", "London, UK"])
def test_unknown_location_is_safe_error(query):
    with pytest.raises(ValueError):
        resolve_origin(query)


def test_multiple_zip_codes_are_not_silently_selected():
    with pytest.raises(ValueError, match="one ZIP"):
        resolve_origin("02108 or 10001")


def test_boston_new_york_distance_and_city_point_zero():
    origin = resolve_origin("Boston, MA")
    miles = distance_miles(origin, "New York", "NY")
    assert miles is not None and 185 < miles < 200
    assert distance_miles(origin, "Boston", "MA") == 0
    assert distance_miles(origin, "Atlantis", "CA") is None
    assert practice_location("Atlantis", "CA") is None


def test_all_fifty_practices_have_city_points():
    records = load_practices()
    assert len(records) == 50
    origin = resolve_origin("10001")
    for practice in records:
        location = practice_location(practice.city, practice.state)
        assert location is not None, (practice.city, practice.state)
        assert distance_miles(origin, practice.city, practice.state) >= 0


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(91, 0), (-91, 0), (0, 181), (0, -181), (math.nan, 0), (0, math.inf), (True, 0)],
)
def test_invalid_coordinates_rejected(latitude, longitude):
    with pytest.raises(ValueError, match="coordinates"):
        Location("Invalid", latitude, longitude, "city")


def test_antipodal_boundary_is_finite():
    destination = practice_location("Boston", "MA")
    opposite = Location(
        "Opposite Boston", -destination.latitude, destination.longitude + 180, "city"
    )
    assert distance_miles(opposite, "Boston", "MA") == pytest.approx(math.pi * EARTH_RADIUS_MILES)


def test_bundled_national_coverage_and_valid_source_coordinates():
    data = json.loads(DATA_PATH.read_text())
    assert data["vintage"] == 2026
    assert len(data["states"]) == 52  # 50 states, District of Columbia, Puerto Rico.
    assert len(data["places"]) > 32000
    assert len(data["zctas"]) > 33000
    for collection in ("states", "places", "zctas"):
        for row in data[collection]:
            latitude, longitude = row[-2:]
            assert math.isfinite(latitude) and -90 <= latitude <= 90
            assert math.isfinite(longitude) and -180 <= longitude <= 180


@pytest.mark.parametrize(
    "query", ["Boston,MA", "Sacramento,CA", "New York,NY", "St. Louis,MO", "Sacramento,California"]
)
def test_city_state_comma_is_a_separator_without_requiring_a_space(query):
    assert resolve_origin(query) == resolve_origin(query.replace(",", ", "))
