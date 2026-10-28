"""Replace the loader with an authorized feed later; search stays deterministic."""

import json
from collections.abc import Iterable
from datetime import date
from functools import lru_cache
from pathlib import Path

from sera.geography import distance_miles
from sera.models import Filters, Practice
from sera.search_location import validate_distance_filters

ROOT = Path(__file__).resolve().parent.parent


def load_practices(path: Path = ROOT / "data/practices.json") -> list[Practice]:
    """Reuse validated records until the source file changes; callers get isolated copies."""
    path = Path(path).resolve()
    stat = path.stat()
    return [
        record.model_copy(deep=True)
        for record in _load_records(path, stat.st_mtime_ns, stat.st_size)
    ]


@lru_cache(maxsize=4)
def _load_records(path: Path, modified_ns: int, size: int) -> tuple[Practice, ...]:
    # File metadata is part of the cache key, so editing JSON invalidates cached data.
    records = tuple(Practice.model_validate(record) for record in json.loads(path.read_text()))
    if len({record.id for record in records}) != len(records):
        raise ValueError("Duplicate practice IDs")
    return records


def operating_years(practice: Practice) -> int | None:
    return None if practice.founding_year is None else date.today().year - practice.founding_year


def budget_fit(practice: Practice, budget: int | None, inclusive: bool = True) -> str:
    if practice.asking_price is None:
        return "Budget unverified — price undisclosed"
    if budget is None:
        return "No budget specified"
    return (
        "Within asking-price budget"
        if (practice.asking_price <= budget if inclusive else practice.asking_price < budget)
        else "Above asking-price budget"
    )


def search(records: Iterable[Practice], filters: Filters) -> list[Practice]:
    """AND across filters, OR within selections; unknown facts never meet minimums."""
    # Normalize once per search, rather than repeating work for every practice.
    specialties, states, statuses = map(
        set, (filters.specialties, filters.states, filters.statuses)
    )
    city, keyword = filters.city.strip().casefold(), filters.keyword.strip().casefold()
    origin = validate_distance_filters(filters)

    def matches(practice: Practice) -> bool:
        if specialties and practice.specialty not in specialties:
            return False
        if filters.max_distance_miles is None and states and practice.state not in states:
            return False
        if filters.max_distance_miles is None and city and practice.city.casefold() != city:
            return False
        if filters.max_distance_miles is not None:
            distance = distance_miles(origin, practice.city, practice.state)
            if distance is None or distance > filters.max_distance_miles:
                return False
        if practice.status not in statuses:
            return False
        if practice.asking_price is None:
            if not filters.include_undisclosed:
                return False
        elif filters.max_price is not None:
            if practice.asking_price > filters.max_price or (
                not filters.max_price_inclusive and practice.asking_price == filters.max_price
            ):
                return False

        minimums = (
            (filters.min_patients, practice.active_patients),
            (filters.min_years, operating_years(practice)),
            (filters.min_sqft, practice.sqft),
            (filters.min_operatories, practice.operatories),
        )
        if any(minimum and (value is None or value < minimum) for minimum, value in minimums):
            return False
        return (
            not keyword
            or keyword in f"{practice.name} {practice.description} {practice.specialty}".casefold()
        )

    return [practice for practice in records if matches(practice)]


DENTAL_SPECIALTIES = {"General dentistry", "Orthodontics", "Endodontics"}


def room_summary(practice: Practice) -> str:
    """Use the relevant clinical room type instead of implying medical operatories are missing."""
    if practice.specialty in DENTAL_SPECIALTIES:
        return (
            f"{practice.operatories} operatories"
            if practice.operatories is not None
            else "Unknown operatories"
        )
    operations = practice.operations
    if operations is not None and operations.exam_rooms is not None:
        return f"{operations.exam_rooms} exam rooms"
    return "Exam room count not supplied"


def profile_text(profile) -> str:
    """Expose every supplied profile field and its provenance to exports and tools."""
    if profile is None:
        return "Profile not supplied"
    fields = []
    for key, value in profile.model_dump().items():
        if value is None:
            continue  # Conditional lease / ownership fields are not evidence gaps.
        if isinstance(value, dict):
            value = ", ".join(f"{k}: {v}" for k, v in value.items())
        elif isinstance(value, list):
            value = "; ".join(value)
        fields.append(f"{key.replace('_', ' ')}: {value}")
    return "; ".join(fields)


def fact_sheet(practice: Practice) -> dict[str, str]:
    """Recorded facts only; no model is involved."""
    years = operating_years(practice)
    return {
        "Specialty / location": f"{practice.specialty} · {practice.city}, {practice.state}",
        "Founded / approximate years": f"{practice.founding_year or 'Unknown'} / {years if years is not None else 'Unknown'}",
        "Ownership and transition history": "\n".join(practice.history) or "Unknown",
        "Availability": f"{practice.status}: {practice.availability_evidence} ({practice.availability_source}, {practice.availability_date})",
        "Asking price": money(practice.asking_price),
        "Reported annual revenue (not profit)": f"{money(practice.annual_revenue, missing='Unknown')}; period: {practice.revenue_period or 'Unknown'}",
        "Active patients": f"{practice.active_patients if practice.active_patients is not None else 'Unknown'}; period: {practice.patient_period or 'Unknown'}",
        "Size": f"{practice.sqft if practice.sqft is not None else 'Unknown'} sq ft; {room_summary(practice)}",
        "Financial profile (fictional seller model, not audited)": profile_text(
            practice.financials
        ),
        "Operations profile (fictional)": profile_text(practice.operations),
        "Premises / property profile (fictional)": profile_text(practice.premises),
        "Property pricing boundary": (
            "Practice asking price excludes real estate. Any property offer is separately priced."
            if practice.premises
            else "Property inclusion is not established; premises profile not supplied."
        ),
        "Seller legal disclosures": practice.legal_disclosures,
        "Independent legal research": practice.legal_research_status,
        "Local crime statistics": evidence_text(practice.crime),
        "Mean patient household income (aggregate patient evidence)": evidence_text(
            practice.patient_household_income
        ),
        "Area household income (not patient income)": evidence_text(practice.area_household_income),
        "Missing evidence": ", ".join(
            k
            for k in [
                "founding_year",
                "asking_price",
                "annual_revenue",
                "active_patients",
                "sqft",
                "operatories",
                "revenue_period",
                "patient_period",
                "crime",
                "patient_household_income",
                "area_household_income",
            ]
            if getattr(practice, k) is None
            and (k != "operatories" or practice.specialty in DENTAL_SPECIALTIES)
        )
        or "No missing fields in this summary; independent verification still required",
        "Sources (all fictional)": "\n".join(
            f"{s.id}: {s.label}; {s.kind}; {s.date}" for s in practice.sources
        ),
    }


def evidence_text(value: dict | None) -> str:
    return (
        "Unknown — no supplied evidence"
        if value is None
        else "; ".join(f"{k}: {v}" for k, v in value.items())
    )


def money(value: int | None, missing: str = "Price undisclosed") -> str:
    return missing if value is None else f"${value:,.0f}"
