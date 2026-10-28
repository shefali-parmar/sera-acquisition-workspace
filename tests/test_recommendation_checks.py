"""Known bad claims and valid contrasts; no model or network calls."""

import pytest

from sera.catalog import load_practices
from sera.recommendation_checks import record_claim_issues


@pytest.fixture
def records():
    return {
        p.id: p.model_dump()
        for p in load_practices()
        if p.id in {"SERA-001", "SERA-002", "SERA-025"}
    }


@pytest.mark.parametrize(
    "answer",
    [
        "SERA-001 has normalized EBITDA of $386,000 [SERA-001-S4].",
        "Riverbend Dermatology has $386k normalized EBITDA [SERA-001-S4].",
        "SERA-001 asking price is $1.15 million [SERA-001-S1].",
        "SERA-001 annual revenue is $650,000 [SERA-001-S1].",
        "SERA-001 has 1,525 active patients [SERA-001-S1].",
        "SERA-001 annual base rent is $96,000 [SERA-001-S5].",
        "SERA-001 CAM is $9.6m [SERA-001-S5].",
        "SERA-002 asking price is $0 [SERA-002-S1].",
        "SERA-001 property asking price is $650k [SERA-001-S5].",
    ],
)
def test_rejects_unambiguous_wrong_record_amounts(records, answer):
    assert record_claim_issues(answer, records)


@pytest.mark.parametrize(
    "answer",
    [
        "SERA-001 has normalized EBITDA of $187,000 [SERA-001-S4].",
        "Riverbend Dermatology has $187k normalized EBITDA [SERA-001-S4].",
        "SERA-001 asking price is $.65 million [SERA-001-S1].",
        "SERA-001 annual revenue is $0.85M [SERA-001-S1].",
        "SERA-001 has 850 active patients [SERA-001-S1].",
        "SERA-001 annual base rent is $43.2 thousand [SERA-001-S5].",
        "SERA-001 monthly rent is $3,600 [SERA-001-S5].",
        "SERA-001 CAM is $9.6k [SERA-001-S5].",
        "SERA-001 total annual rent and CAM is $52,800 [SERA-001-S5].",
        "SERA-001 normalized EBITDA is 187000 [SERA-001-S4].",
        "SERA-001 normalized EBITDA for calendar year 2025 is $187k [SERA-001-S4].",
        "SERA-001 has lower EBITDA of $187k [SERA-001-S4], compared with SERA-025 at $386k [SERA-025-S4].",
        "SERA-001 asking price is $650k, below your $700k budget [SERA-001-S1].",
        "SERA-001 asking price is $500k lower than the other practice [SERA-001-S1] [SERA-025-S1].",
        "SERA-001 revenue per patient is $1,000 [SERA-001-S1].",
        "If SERA-001 asking price falls to $600k, reassess the acquisition budget.",
        "Confirm SERA-001 annual rent of $60k before using that hypothetical scenario.",
        "Does SERA-001 have EBITDA of $300k?",
        "SERA-001 does not have EBITDA of $300k [SERA-001-S4].",
        "SERA-001 EBITDA is not $300k [SERA-001-S4].",
        "SERA-001 EBITDA of $300k is not recorded [SERA-001-S4].",
        "SERA-001 does not have audited statements. Its asking price is $650k [SERA-001-S1].",
    ],
)
def test_preserves_correct_or_nonfactual_amounts(records, answer):
    assert not record_claim_issues(answer, records)


def test_table_ownership_and_header_values(records):
    header = "| Practice | Asking price | EBITDA |\n|---|---|---|\n"
    assert not record_claim_issues(
        header + "| Riverbend Dermatology | $650k [SERA-001-S1] | $187k [SERA-001-S4] |", records
    )
    issues = record_claim_issues(
        header + "| Riverbend Dermatology | $1.15m [SERA-025-S1] | $386k [SERA-025-S4] |", records
    )
    assert any("own evidence" in issue for issue in issues)
    assert any("price" in issue for issue in issues)
    assert any("ebitda" in issue for issue in issues)
    assert record_claim_issues(
        header + "| Riverbend Dermatology | $650k [SERA-001-S1] | $386k [SERA-001-S4] |", records
    )


def test_own_citation_does_not_excuse_foreign_citation_on_separate_row(records):
    answer = "| Practice | Price |\n|---|---|\n| Riverbend Dermatology | $650k [SERA-025-S1] |\n| Elmbrook Skin Center | $1.15m [SERA-001-S1] |"
    issues = record_claim_issues(answer, records)
    assert len([issue for issue in issues if "own evidence" in issue]) == 2


@pytest.mark.parametrize(
    "answer",
    [
        "SERA-001 is a guaranteed profitable acquisition. Buy it now [SERA-001-S1].",
        "SERA-001 is legally cleared [SERA-001-S6].",
        "SERA-001 has a clean legal history [SERA-001-S1].",
        "SERA-001 has no legal issues [SERA-001-S1].",
        "SERA-001 landlord consent has already been obtained [SERA-001-S5].",
        "SERA-001 property is included in the practice price [SERA-001-S5].",
        "SERA-025 includes the office condominium in its $1,150,000 practice price [SERA-025-S5].",
    ],
)
def test_rejects_unfounded_assurances(records, answer):
    assert record_claim_issues(answer, records)


@pytest.mark.parametrize(
    "answer",
    [
        "SERA-001 is not guaranteed profitable [SERA-001-S1].",
        "Do not buy it now; verify the transaction first.",
        "SERA-001 is not legally cleared [SERA-001-S6].",
        "SERA-001 isn’t legally cleared [SERA-001-S6].",
        "SERA-001 being legally cleared is not established [SERA-001-S6].",
        "SERA-001 has no independently verified clean legal history [SERA-001-S1].",
        "SERA-001 landlord consent has not been obtained [SERA-001-S5].",
        "Confirm landlord consent has been obtained before closing.",
        "Has SERA-001 landlord consent been obtained?",
        "If landlord consent is obtained, reassess the conditions before proceeding.",
        "SERA-001 property is not included in the practice price [SERA-001-S5].",
        "SERA-001's practice and separately priced property have a combined total price of $2m.",
    ],
)
def test_preserves_negation_questions_and_process_guidance(records, answer):
    assert not record_claim_issues(answer, records)


def test_unrelated_disclaimer_does_not_exempt_later_assurance(records):
    assert record_claim_issues(
        "Do not assume returns; however SERA-001 is guaranteed profitable [SERA-001-S1].", records
    )


@pytest.mark.parametrize(
    "claim",
    [
        "Riverbend Dermatology has higher EBITDA than Elmbrook Skin Center [SERA-001-S4] [SERA-025-S4].",
        "SERA-001 EBITDA is greater than SERA-025 EBITDA [SERA-001-S4] [SERA-025-S4].",
        "SERA-025 has a lower asking price than SERA-001 [SERA-001-S1] [SERA-025-S1].",
    ],
)
def test_rejects_reversed_direction_even_without_amounts(records, claim):
    assert any("comparison" in issue for issue in record_claim_issues(claim, records))


@pytest.mark.parametrize(
    "claim",
    [
        "Riverbend Dermatology has lower EBITDA than Elmbrook Skin Center [SERA-001-S4] [SERA-025-S4].",
        "SERA-025 EBITDA is greater than SERA-001 EBITDA [SERA-001-S4] [SERA-025-S4].",
        "SERA-001 has a lower asking price than SERA-025 [SERA-001-S1] [SERA-025-S1].",
        "SERA-001 does not have higher EBITDA than SERA-025 [SERA-001-S4] [SERA-025-S4].",
        "If SERA-001 EBITDA were higher than SERA-025, reassess the ranking.",
        "Does SERA-001 have higher EBITDA than SERA-025?",
    ],
)
def test_preserves_correct_and_hypothetical_direction(records, claim):
    assert not record_claim_issues(claim, records)


def test_requires_financial_or_premises_source_for_its_metric(records):
    assert any(
        "Cite" in issue
        for issue in record_claim_issues("SERA-001 EBITDA is $187k [SERA-001-S1].", records)
    )
    assert any(
        "Cite" in issue
        for issue in record_claim_issues("SERA-001 annual rent is $43,200 [SERA-001-S1].", records)
    )
    assert not record_claim_issues("SERA-001 annual revenue is $850k [SERA-001-S4].", records)


@pytest.mark.parametrize(
    "label",
    [
        "combined asking-price subtotal",
        "combined asking price",
        "combined purchase price",
        "combined practice and property asking-price subtotal",
    ],
)
def test_combined_price_checks_recorded_sum_and_both_sources(records, label):
    prefix = f"Elmbrook Skin Center {label} is "
    citations = " [SERA-025-S1] [SERA-025-S5]."
    assert not record_claim_issues(prefix + "$1,542,000" + citations, records)
    assert any(
        "combined_price" in issue and "1,542,000" in issue
        for issue in record_claim_issues(prefix + "$1,500,000" + citations, records)
    )
    for source in ("SERA-025-S1", "SERA-025-S5"):
        assert any(
            "Cite" in issue
            for issue in record_claim_issues(prefix + f"$1,542,000 [{source}].", records)
        )


def test_combined_price_table_header_and_missing_property_price(records):
    header = "| Practice | Combined asking-price subtotal |\n|---|---|\n"
    citations = "[SERA-025-S1] [SERA-025-S5]"
    assert not record_claim_issues(
        header + f"| Elmbrook Skin Center | $1.542m {citations} |", records
    )
    assert record_claim_issues(header + f"| Elmbrook Skin Center | $1.5m {citations} |", records)
    assert record_claim_issues(
        "SERA-001 combined asking price is $650,000 [SERA-001-S1] [SERA-001-S5].", records
    )


def test_unqualified_asking_price_subtotal_is_not_assumed_combined(records):
    assert record_claim_issues(
        "SERA-025 asking-price subtotal is $1,542,000 [SERA-025-S1] [SERA-025-S5].", records
    )
    assert not record_claim_issues(
        "SERA-025 asking-price subtotal is $1,150,000 [SERA-025-S1].", records
    )


@pytest.mark.parametrize(
    "answer",
    [
        "**Legally cleared:** No. Neither transaction has independent clearance [SERA-001-S6] [SERA-002-S6].",
        "**Property included in the business price?** No. Elmbrook Skin Center property is separately priced [SERA-025-S5].",
        'You cannot describe Elmbrook Skin Center as "legally cleared" [SERA-025-S6].',
        "You cannot describe Elmbrook Skin Center as “legally cleared” [SERA-025-S6].",
        "Neither transaction is legally cleared [SERA-001-S6] [SERA-002-S6].",
        "**Landlord consent obtained:** No [SERA-001-S5].",
        "**Property included in the business price:** No [SERA-025-S5].",
        "Riverbend Dermatology is **not legally cleared** [SERA-001-S6].",
    ],
)
def test_denied_assurances_survive_quotes_and_markdown(records, answer):
    assert not record_claim_issues(answer, records)


@pytest.mark.parametrize(
    "answer",
    [
        "**Legally cleared:** Yes [SERA-001-S6].",
        "**Landlord consent obtained:** Yes [SERA-001-S5].",
        "**Property included in the business price:** Yes [SERA-025-S5].",
        'Do not assume clearance. Riverbend Dermatology is "legally cleared" [SERA-001-S6].',
        "**Legally cleared?** Yes. Riverbend Dermatology is legally cleared [SERA-001-S6].",
    ],
)
def test_formatted_positive_assurances_remain_rejected(records, answer):
    assert record_claim_issues(answer, records)
