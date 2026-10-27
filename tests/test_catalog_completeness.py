"""The fictional catalog is complete without implying real transaction verification."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from sera.models import Practice


@pytest.fixture(scope="module")
def catalog():
    path = Path(__file__).resolve().parents[1] / "data" / "practices.json"
    return [Practice.model_validate(item) for item in json.loads(path.read_text())]


def test_fifty_distinct_profiles_with_applicable_core_information(catalog):
    assert {item.id for item in catalog} == {f"SERA-{number:03}" for number in range(1, 51)}
    assert len({item.name.casefold() for item in catalog}) == 50
    assert [item.id for item in catalog if item.asking_price is None] == ["SERA-002"]
    for item in catalog:
        assert item.fictional
        assert item.founding_year and item.annual_revenue and item.revenue_period
        assert item.active_patients and item.patient_period and item.sqft
        assert item.status != "Availability unknown"
        assert item.financials and item.operations and item.premises
        assert item.crime and item.area_household_income and item.patient_household_income
        assert "Unknown" not in item.legal_disclosures
        assert "Simulated legal review" in item.legal_research_status
        assert "not an actual" in item.legal_research_status
        if item.specialty in {"General dentistry", "Orthodontics", "Endodontics"}:
            assert item.operatories and item.operations.exam_rooms is None
        else:
            assert item.operatories is None and item.operations.exam_rooms


def test_catalog_keeps_established_identities_and_numeric_facts(catalog):
    by_id = {item.id: item for item in catalog}
    first = by_id["SERA-001"]
    assert (first.name, first.asking_price, first.annual_revenue, first.sqft) == (
        "Riverbend Dermatology",
        650000,
        850000,
        1600,
    )
    assert first.crime["value"] == 1800
    assert first.patient_household_income["value"] == 92000
    assert first.area_household_income["value"] == 67000
    assert by_id["SERA-025"].name == "Elmbrook Skin Center"
    assert by_id["SERA-025"].asking_price == 1150000
    assert (
        "previously disclosed a lease-service-charge dispute" in by_id["SERA-002"].legal_disclosures
    )


def test_operating_statement_reconciles_without_double_counting_occupancy(catalog):
    for item in catalog:
        financials = item.financials
        assert (
            financials.normalized_ebitda
            + sum(
                (
                    financials.payroll_expense,
                    financials.supplies_expense,
                    financials.occupancy_expense,
                    financials.other_operating_expense,
                )
            )
            == item.annual_revenue
        )
        assert financials.owner_compensation_included is True
        assert "not net income" in financials.normalization_notes
        assert sum(item.operations.payer_mix.model_dump().values()) == 100
        assert item.operations.annual_visits >= item.active_patients
        premises = item.premises
        assert "invented address" in premises.address
        assert "no real inspection" in premises.review_status
        assert premises.property_included_in_practice_price is False
        if premises.occupancy == "Leased":
            assert premises.property_asking_price is None
            assert financials.occupancy_expense == premises.annual_base_rent + premises.annual_cam
            assert premises.landlord_consent_required is True
        else:
            assert premises.property_asking_price > 0
            assert premises.annual_base_rent is None and premises.annual_cam is None
            assert premises.lease_expires is None
            assert premises.landlord_consent_required is None


def test_each_profile_and_statistic_has_its_own_fictional_source(catalog):
    for item in catalog:
        sources = {source.id: source for source in item.sources}
        references = [
            item.availability_source,
            item.financials.source,
            item.operations.source,
            item.premises.source,
            item.crime["source"],
            item.area_household_income["source"],
            item.patient_household_income["source"],
        ]
        for reference in references:
            assert reference in sources and reference.startswith(item.id + "-S")
            assert sources[reference].label.startswith("Fictional")
        assert item.financials.source == item.id + "-S4"
        assert item.premises.source == item.id + "-S5"
        assert item.operations.source == item.id + "-S6"


@pytest.mark.parametrize("profile", ["financials", "premises", "operations"])
def test_profile_sources_cannot_borrow_another_practices_evidence(catalog, profile):
    data = catalog[0].model_dump()
    data[profile]["source"] = catalog[1].sources[0].id
    with pytest.raises(ValidationError, match="Profile evidence must reference"):
        Practice.model_validate(data)


def test_profile_accounting_and_payer_mix_reject_inconsistent_values(catalog):
    data = catalog[0].model_dump()
    data["financials"]["occupancy_expense"] += 1
    with pytest.raises(ValidationError, match="must equal annual revenue"):
        Practice.model_validate(data)
    data = catalog[0].model_dump()
    data["operations"]["payer_mix"]["commercial"] += 1
    with pytest.raises(ValidationError, match="total 100"):
        Practice.model_validate(data)
    data = catalog[0].model_dump()
    data["premises"]["property_asking_price"] = 500000
    with pytest.raises(ValidationError, match="Leased premises cannot"):
        Practice.model_validate(data)


def test_profiles_remain_optional_for_legacy_records(catalog):
    data = catalog[0].model_dump()
    for field in ("financials", "operations", "premises"):
        data.pop(field)
    record = Practice.model_validate(data)
    assert record.financials is None and record.operations is None and record.premises is None
