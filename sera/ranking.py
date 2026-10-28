"""Transparent ordering of already eligible practices, without model-generated scores."""

import math
import re

from sera.catalog import operating_years
from sera.models import Filters, Practice


def _words(value: str) -> str:
    return " ".join(re.findall(r"\w+", value.casefold()))


def _keyword_score(practice: Practice, keyword: str) -> float:
    query = _words(keyword)
    if not query:
        return 0.0
    name, specialty, description = map(
        _words, (practice.name, practice.specialty, practice.description)
    )
    if query in (name, specialty):
        return 1.0
    # Whole-word phrases avoid ranking, for example, "art" as a strong name hit in "Hart".
    phrase = f" {query} "
    if phrase in f" {name} ":
        return 0.75
    if phrase in f" {specialty} ":
        return 0.5
    if query in description or query in name or query in specialty:
        return 0.25
    return 0.0


def relevance_score(
    practice: Practice,
    filters: Filters,
    *,
    distance: float | None = None,
    has_origin: bool = False,
) -> float:
    """Average active, bounded components; this is an ordering aid, not match confidence.

    Keyword placement scores 1 for an exact name/specialty, .75 for a name phrase,
    .5 for a specialty phrase and .25 for another substring hit. A price cap adds
    proportional headroom (1 - asking price / cap). Active minimums add surplus
    above the minimum, saturated at twice that minimum. With a resolved origin,
    proximity is 1 / (1 + miles / 100), halving at 100 straight-line miles.

    Missing evidence contributes zero to its active component. Zero-dollar prices
    are known values; a zero cap gives a zero-dollar practice full headroom credit.
    Binary constraints already shared by eligible practices add no component.
    Without active components all scores tie. Call deterministic search first;
    this helper never changes eligibility, records, or filters and uses no buyer
    priorities, risk judgments, or AI output.
    """
    components: list[float] = []
    if _words(filters.keyword):
        components.append(_keyword_score(practice, filters.keyword))
    if filters.max_price is not None:
        price, cap = practice.asking_price, filters.max_price
        if price is None:
            components.append(0.0)
        elif cap == 0:
            components.append(1.0 if price == 0 else 0.0)
        else:
            components.append(max(0.0, min(1.0, 1 - price / cap)))
    minimums = (
        (filters.min_patients, practice.active_patients),
        (filters.min_years, operating_years(practice)),
        (filters.min_sqft, practice.sqft),
        (filters.min_operatories, practice.operatories),
    )
    for minimum, value in minimums:
        if minimum > 0:
            components.append(
                0.0 if value is None else max(0.0, min(1.0, (value - minimum) / minimum))
            )
    if has_origin:
        components.append(
            1 / (1 + distance / 100)
            if distance is not None and math.isfinite(distance) and distance >= 0
            else 0.0
        )
    return sum(components) / len(components) if components else 0.0


def relevance_key(
    practice: Practice,
    filters: Filters,
    *,
    distance: float | None = None,
    has_origin: bool = False,
) -> tuple[float, str, str]:
    """Ascending sort key: strongest relevance first, then stable name and ID ties."""
    return (
        -relevance_score(practice, filters, distance=distance, has_origin=has_origin),
        practice.name.casefold(),
        practice.id,
    )
