"""Offline Census area-point lookup and approximate straight-line distances.

No visitor locations are sent to a geocoding service. Gazetteer representative
points approximate area centers; a fictional practice uses its city's point.
"""

import json
import math
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

DATA_PATH = Path(__file__).resolve().parent.parent / "data/geography_2026.json"
EARTH_RADIUS_MILES = 3958.7613


@dataclass(frozen=True)
class Location:
    label: str
    latitude: float
    longitude: float
    kind: Literal["zip", "city", "state"]

    def __post_init__(self) -> None:
        if (
            isinstance(self.latitude, bool)
            or isinstance(self.longitude, bool)
            or not isinstance(self.latitude, (int, float))
            or not isinstance(self.longitude, (int, float))
            or not math.isfinite(self.latitude)
            or not math.isfinite(self.longitude)
            or not -90 <= self.latitude <= 90
            or not -180 <= self.longitude <= 180
        ):
            raise ValueError("Location coordinates must be finite latitude/longitude values.")
        if self.kind not in {"zip", "city", "state"}:
            raise ValueError("Location kind must be zip, city, or state.")


def _key(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).casefold()
    return " ".join(re.sub(r"[^\w\s]", "", value, flags=re.UNICODE).split())


@lru_cache(maxsize=1)
def _lookups() -> tuple[dict, dict, dict]:
    data = json.loads(DATA_PATH.read_text())
    states, places, zips = {}, {}, {}
    for code, name, latitude, longitude in data["states"]:
        location = Location(name, latitude, longitude, "state")
        states[_key(code)] = (code, location)
        states[_key(name)] = (code, location)
    # Common names of three Census places used in the fictional catalog.
    aliases = {
        ("ID", "Boise City"): "Boise",
        ("HI", "Urban Honolulu"): "Honolulu",
        ("TN", "Nashville-Davidson"): "Nashville",
    }
    for code, official, short, latitude, longitude in data["places"]:
        display = aliases.get((code, short), short)
        location = Location(f"{display}, {code}", latitude, longitude, "city")
        for name in {official, short, display}:
            entries = places.setdefault(_key(name), [])
            if (code, location) not in entries:
                entries.append((code, location))
    for code, latitude, longitude in data["zctas"]:
        zips[code] = Location(f"ZIP {code}", latitude, longitude, "zip")
    return states, places, zips


def _one_place(candidates: list[tuple[str, Location]], query: str) -> Location:
    if len(candidates) == 1:
        return candidates[0][1]
    if candidates:
        options = ", ".join(sorted({entry[1].label for entry in candidates})[:6])
        raise ValueError(
            f"“{query}” matches multiple places ({options}). "
            "Use a ZIP code, or add the state if it was omitted."
        )
    raise ValueError(
        "Location not found. Enter a U.S. ZIP code, city and state (e.g. Boston, MA), "
        "or state name/abbreviation."
    )


def resolve_origin(query: str) -> Location:
    """Resolve ZIP first, then state, then an unambiguous city with optional state.

    A ZIP in a combined location such as ``Boston, MA 02108`` takes precedence.
    ZIP coverage is Census ZCTAs; PO-box-only and new USPS ZIPs may be absent.
    Ambiguous city names are never resolved by arbitrary ordering/population.
    """
    if not isinstance(query, str) or not query.strip() or len(query) > 200:
        raise ValueError("Enter a U.S. ZIP code, city and state, or state.")
    query = query.strip()
    states, places, zips = _lookups()
    codes = set(re.findall(r"(?<!\d)\d{5}(?!\d)", query))
    if len(codes) > 1:
        raise ValueError("Enter one ZIP code for the distance origin.")
    if codes:
        code = codes.pop()
        if code not in zips:
            raise ValueError(
                f"ZIP {code} is not in the bundled Census ZIP areas. "
                "Try a nearby ZIP code or city and state."
            )
        return zips[code]
    normalized = _key(query)
    if normalized in states:
        return states[normalized][1]
    # Match the longest state name suffix to allow both comma and space forms.
    for state_name in sorted(states, key=len, reverse=True):
        suffix = " " + state_name
        if normalized.endswith(suffix):
            city = normalized[: -len(suffix)]
            code = states[state_name][0]
            return _one_place([entry for entry in places.get(city, []) if entry[0] == code], query)
    return _one_place(places.get(normalized, []), query)


def practice_location(city: str, state: str) -> Location | None:
    """Return a city's area point, never invent coordinates for an unknown place."""
    try:
        location = resolve_origin(f"{city}, {state}")
        return location if location.kind == "city" else None
    except ValueError:
        return None


def distance_miles(origin: Location, city: str, state: str) -> float | None:
    """Great-circle miles to the practice's city point; this is not driving distance."""
    destination = practice_location(city, state)
    if destination is None:
        return None
    latitude1, latitude2 = map(math.radians, (origin.latitude, destination.latitude))
    delta_latitude = latitude2 - latitude1
    delta_longitude = math.radians(destination.longitude - origin.longitude)
    haversine = math.sin(delta_latitude / 2) ** 2 + (
        math.cos(latitude1) * math.cos(latitude2) * math.sin(delta_longitude / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(min(1.0, max(0.0, haversine))))
