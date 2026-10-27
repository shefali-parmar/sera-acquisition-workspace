"""Portable buyer-list snapshots built from recorded evidence, without model calls."""

import csv
import io
import json
import re
from datetime import datetime, timezone

from sera.catalog import budget_fit, fact_sheet
from sera.models import Filters, Practice, SavedList


def build_list_export(
    item: SavedList,
    by_id: dict[str, Practice],
    *,
    filters: Filters,
    buyer_goals: str,
) -> dict:
    """Keep missing candidates visible and bind an export to the current criteria."""
    return {
        "schema_version": 1,
        "fictional": True,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "evidence_notice": (
            "All practices and source references are fictional and unverified. "
            "Saved-list membership does not mean a practice meets current criteria. "
            "Asking price is not total acquisition cost; reported revenue is not profit. "
            "Any normalized EBITDA is a fictional unaudited model. Real estate, when offered, "
            "is separately priced and excluded from the practice asking price."
        ),
        "list": item.model_dump(mode="json"),
        "context": {
            "buyer_goals": buyer_goals,
            "applied_filters": filters.model_dump(mode="json"),
        },
        "unavailable_practice_ids": [pid for pid in item.practice_ids if pid not in by_id],
        "practices": [
            {
                **by_id[pid].model_dump(mode="json"),
                "asking_price_budget_fit": budget_fit(
                    by_id[pid], filters.max_price, inclusive=filters.max_price_inclusive
                ),
                "fact_sheet": fact_sheet(by_id[pid]),
            }
            for pid in item.practice_ids
            if pid in by_id
        ],
    }


def export_json(payload: dict) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False)


def export_filename(list_name: str, suffix: str) -> str:
    if suffix not in {"json", "csv"}:
        raise ValueError("Export format must be json or csv.")
    stem = re.sub(r"[^a-z0-9]+", "-", list_name.casefold()).strip("-")[:60]
    return f"sera-{stem or 'list'}.{suffix}"


def _spreadsheet_text(value: object) -> object:
    """Treat untrusted labels as text when a CSV is opened in a spreadsheet."""
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return "" if value is None else value


def export_csv(payload: dict) -> str:
    """Export recorded fields; unavailable records get explicit rows, not invented facts."""
    fields = [
        "list_name",
        "practice_id",
        "record_status",
        "name",
        "specialty",
        "city",
        "state",
        "availability",
        "asking_price_usd",
        "asking_price_budget_fit",
        "annual_revenue_usd_not_profit",
        "revenue_period",
        "active_patients",
        "patient_period",
        "founding_year",
        "square_feet",
        "operatories",
        "seller_legal_disclosures",
        "independent_legal_research",
        "source_references",
        "exported_at",
        "fictional",
        "normalized_ebitda_usd_fictional_not_audited",
        "financial_reporting_period",
        "providers",
        "staff_fte",
        "exam_rooms",
        "annual_visits",
        "premises_occupancy",
        "premises_address_fictional",
        "annual_base_rent_usd",
        "annual_cam_usd",
        "lease_expires",
        "separate_property_asking_price_usd",
        "property_included_in_practice_price",
        "financial_profile_json",
        "operations_profile_json",
        "premises_profile_json",
    ]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    records = {record["id"]: record for record in payload["practices"]}
    for pid in payload["list"]["practice_ids"]:
        record = records.get(pid)
        row = {
            "list_name": payload["list"]["name"],
            "practice_id": pid,
            "record_status": "Available in fictional catalog" if record else "Record unavailable",
            "exported_at": payload["exported_at"],
            "fictional": True,
        }
        if record:
            row.update(
                {
                    "name": record["name"],
                    "specialty": record["specialty"],
                    "city": record["city"],
                    "state": record["state"],
                    "availability": record["status"],
                    "asking_price_usd": record["asking_price"],
                    "asking_price_budget_fit": record["asking_price_budget_fit"],
                    "annual_revenue_usd_not_profit": record["annual_revenue"],
                    "revenue_period": record["revenue_period"],
                    "active_patients": record["active_patients"],
                    "patient_period": record["patient_period"],
                    "founding_year": record["founding_year"],
                    "square_feet": record["sqft"],
                    "operatories": record["operatories"],
                    "seller_legal_disclosures": record["legal_disclosures"],
                    "independent_legal_research": record["legal_research_status"],
                    "source_references": "; ".join(
                        f"{source['id']}: {source['label']} ({source['date']})"
                        for source in record["sources"]
                    ),
                }
            )
            financials = record.get("financials") or {}
            operations = record.get("operations") or {}
            premises = record.get("premises") or {}
            row.update(
                {
                    "normalized_ebitda_usd_fictional_not_audited": financials.get(
                        "normalized_ebitda"
                    ),
                    "financial_reporting_period": financials.get("reporting_period"),
                    "providers": operations.get("providers"),
                    "staff_fte": operations.get("staff_fte"),
                    "exam_rooms": operations.get("exam_rooms"),
                    "annual_visits": operations.get("annual_visits"),
                    "premises_occupancy": premises.get("occupancy"),
                    "premises_address_fictional": premises.get("address"),
                    "annual_base_rent_usd": premises.get("annual_base_rent"),
                    "annual_cam_usd": premises.get("annual_cam"),
                    "lease_expires": premises.get("lease_expires"),
                    "separate_property_asking_price_usd": premises.get("property_asking_price"),
                    "property_included_in_practice_price": premises.get(
                        "property_included_in_practice_price"
                    ),
                    "financial_profile_json": json.dumps(financials, ensure_ascii=False)
                    if financials
                    else "",
                    "operations_profile_json": json.dumps(operations, ensure_ascii=False)
                    if operations
                    else "",
                    "premises_profile_json": json.dumps(premises, ensure_ascii=False)
                    if premises
                    else "",
                }
            )
        writer.writerow({key: _spreadsheet_text(value) for key, value in row.items()})
    return output.getvalue()
