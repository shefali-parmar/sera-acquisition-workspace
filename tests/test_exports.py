"""Exports preserve list membership, unknowns, context and plain spreadsheet text."""

import csv
import io
import json

from sera.catalog import load_practices
from sera.exports import build_list_export, export_csv, export_filename, export_json
from sera.models import Filters, SavedList


def test_export_retains_unavailable_ids_without_inventing_records():
    records = load_practices()
    known = records[0]
    item = SavedList(id="test", name="My list", practice_ids=[known.id, "SERA-999"])
    filters = Filters(states=["CA"], max_price=1000000)
    payload = build_list_export(item, {known.id: known}, filters=filters, buyer_goals="Stable team")
    restored = json.loads(export_json(payload))
    assert restored["list"]["practice_ids"] == [known.id, "SERA-999"]
    assert restored["unavailable_practice_ids"] == ["SERA-999"]
    assert [record["id"] for record in restored["practices"]] == [known.id]
    assert restored["context"]["applied_filters"] == filters.model_dump()
    assert restored["context"]["buyer_goals"] == "Stable team"
    assert restored["fictional"] is True
    item.practice_ids.clear()
    assert len(payload["list"]["practice_ids"]) == 2
    rows = list(csv.DictReader(io.StringIO(export_csv(payload))))
    assert len(rows) == 2
    assert rows[1]["record_status"] == "Record unavailable"
    assert rows[1]["asking_price_usd"] == ""


def test_csv_preserves_unknown_price_and_blocks_formula_labels():
    record = load_practices()[0].model_copy(update={"asking_price": None})
    record.name = '=HYPERLINK("https://example.com","Open")'
    item = SavedList(id="test", name=" +1+1", practice_ids=[record.id])
    payload = build_list_export(item, {record.id: record}, filters=Filters(), buyer_goals="")
    row = next(csv.DictReader(io.StringIO(export_csv(payload))))
    assert row["name"].startswith("'=")
    assert row["list_name"].lstrip().startswith("'")
    assert row["asking_price_usd"] == ""
    assert "Budget unverified" in row["asking_price_budget_fit"]
    assert record.sources[0].id in row["source_references"]


def test_export_filename_cannot_escape_download_folder():
    assert (
        export_filename("../../My favorite practices", "json") == "sera-my-favorite-practices.json"
    )
    assert export_filename("♥", "csv") == "sera-list.csv"


def test_exports_append_complete_financial_operations_and_property_profiles():
    records = load_practices()
    selected = [
        next(p for p in records if p.premises.occupancy == status) for status in ("Leased", "Owned")
    ]
    item = SavedList(id="complete", name="Premises review", practice_ids=[p.id for p in selected])
    payload = build_list_export(
        item, {p.id: p for p in selected}, filters=Filters(), buyer_goals="Own the premises"
    )
    restored = json.loads(export_json(payload))
    rows = list(csv.DictReader(io.StringIO(export_csv(payload))))
    for practice, record, row in zip(selected, restored["practices"], rows):
        assert record["financials"] == practice.financials.model_dump()
        assert record["operations"] == practice.operations.model_dump()
        assert record["premises"] == practice.premises.model_dump()
        assert row["normalized_ebitda_usd_fictional_not_audited"] == str(
            practice.financials.normalized_ebitda
        )
        assert json.loads(row["financial_profile_json"]) == practice.financials.model_dump()
        assert json.loads(row["operations_profile_json"]) == practice.operations.model_dump()
        assert json.loads(row["premises_profile_json"]) == practice.premises.model_dump()
        assert row["property_included_in_practice_price"] == "False"
        if practice.premises.occupancy == "Leased":
            assert row["annual_base_rent_usd"] == str(practice.premises.annual_base_rent)
            assert row["separate_property_asking_price_usd"] == ""
        else:
            assert row["annual_base_rent_usd"] == ""
            assert row["separate_property_asking_price_usd"] == str(
                practice.premises.property_asking_price
            )
    assert "fictional unaudited model" in restored["evidence_notice"]
