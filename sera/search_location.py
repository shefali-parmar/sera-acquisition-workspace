"""Resolve an explicit or unambiguous search location without online geocoding."""

from sera.geography import Location, resolve_origin
from sera.models import Filters


def origin_query(filters: Filters) -> str:
    if filters.distance_origin.strip():
        return filters.distance_origin.strip()
    if filters.city.strip():
        return (
            f"{filters.city.strip()}, {filters.states[0]}"
            if len(filters.states) == 1
            else filters.city.strip()
        )
    return filters.states[0] if len(filters.states) == 1 else ""


def resolve_filter_origin(filters: Filters) -> Location | None:
    query = origin_query(filters)
    return resolve_origin(query) if query else None


def validate_distance_filters(filters: Filters) -> Location | None:
    """Keep ordinary exact-location search working for towns absent from the gazetteer."""
    if not filters.distance_origin.strip() and filters.max_distance_miles is None:
        return None
    origin = resolve_filter_origin(filters)
    if origin is None:
        raise ValueError("Add a ZIP code, city and state, or one state to measure distance from.")
    return origin


def optional_origin(filters: Filters) -> Location | None:
    """Only ranking may omit an unresolved implicit city; radius validation must fail closed."""
    try:
        return resolve_filter_origin(filters)
    except ValueError:
        return None
