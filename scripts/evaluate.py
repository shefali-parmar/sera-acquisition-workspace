"""Run deterministic checks or explicitly authorized live AI cases; never fake a live result."""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sera import ai
from sera.catalog import ROOT, load_practices, search
from sera.models import Filters


def check_fields(actual: dict, expected: dict) -> list[str]:
    failures = []
    for field, wanted in expected.items():
        value = actual[field]
        equal = set(value) == set(wanted) if isinstance(wanted, list) else value == wanted
        if not equal:
            failures.append(f"{field}: expected {wanted!r}, got {value!r}")
    return failures


def run_case(case: dict, live: bool, histories: dict) -> dict:
    start = time.perf_counter()
    failures = []
    result = {"id": case["id"], "kind": case["kind"], "mode": "live" if live else "offline"}
    try:
        if case["kind"] == "filters":
            if live:
                suggestion = ai.extract_filters(case["request"])
                filters = suggestion.filters
                failures.extend(check_fields(filters.model_dump(), case["expected"]))
                if case.get("expect_unverifiable") and not suggestion.unverifiable:
                    failures.append("Unsupported requirements were not surfaced")
                if case.get("expect_clarification") and not suggestion.clarification:
                    failures.append("Expected a clarifying question")
                result["suggestion"] = suggestion.model_dump()
            else:
                if case.get("expect_unverifiable") or case.get("expect_clarification"):
                    result.update(
                        status="skipped",
                        reason="Clarification and unsupported-language handling require live extraction.",
                    )
                    return result
                # Expected filters exercise Python only; this does NOT evaluate language extraction.
                filters = Filters.model_validate(case["expected"])
            matches = search(load_practices(), filters)
            result["matched_ids"] = [record.id for record in matches]
            if case.get("expect_no_results") and matches:
                failures.append("No-match location returned candidates")
        elif live:
            parent = histories.get(case.get("follow_up_to"))
            if case.get("follow_up_to") and parent is None:
                result["status"] = "skipped"
                result["reason"] = "Prerequisite conversation failed"
                return result
            response = ai.investigate(
                case["request"],
                case.get(
                    "goals",
                    "California dermatology; $1.5 million asking-price budget; at least 1000 patients.",
                ),
                parent,
                None if case.get("infer_candidates") else case["required_ids"],
            )
            if response.get("status") != "complete":
                failures.append(
                    "AI interpretation was not completed; preserved facts are not a completed assessment"
                )
            histories[case["id"]] = response["history"]
            tools = {call["tool"] for call in response["calls"]}
            details = {
                call["arguments"].get("practice_id")
                for call in response["calls"]
                if call["tool"] == "get_practice_details"
            }
            failures.extend(
                f"Missing fresh details: {pid}"
                for pid in case["required_ids"]
                if pid not in details
            )
            failures.extend(
                f"Missing tool: {tool}" for tool in case["required_tools"] if tool not in tools
            )
            failures.extend(
                f"Missing expected phrase: {term}"
                for term in case.get("expected_terms", [])
                if term.casefold() not in response["answer"].casefold()
            )
            result.update(
                {
                    key: response.get(key)
                    for key in ("answer", "calls", "sources", "status", "warnings")
                }
            )
            result["human_review"] = (
                "Required: factual grounding, usefulness, complete comparison, and uncertainty."
            )
        else:
            result.update(
                status="skipped",
                reason="Agent quality requires a live model; offline graph wiring is tested by pytest.",
            )
            return result
        result.update(status="passed" if not failures else "failed", failures=failures)
    except Exception as error:
        # Avoid copying raw provider errors, headers, or credentials into a shareable report.
        result.update(status="error", error_type=type(error).__name__)
    finally:
        result["elapsed_seconds"] = round(time.perf_counter() - start, 2)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run actual model calls (local Ollama or paid OpenAI).",
    )
    parser.add_argument("--case", action="append", help="Run only these case IDs; may be repeated.")
    args = parser.parse_args()
    if args.live and not ai.configured():
        parser.error("No AI provider configured. Configure the private .env file.")
    cases = json.loads((ROOT / "evaluation/cases.json").read_text())
    selected = [case for case in cases if not args.case or case["id"] in args.case]
    if not selected:
        parser.error("No matching cases")
    histories = {}
    results = []
    for case in selected:
        result = run_case(case, args.live, histories)
        results.append(result)
        print(f"{case['id']}: {result['status']} ({result['elapsed_seconds']}s)", flush=True)
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "live" if args.live else "offline",
        "model": None if not args.live else ai.model_name(),
        "cases": results,
        "note": "Automated checks are narrow proxies, not proof of answer correctness. Offline mode makes no model calls.",
    }
    directory = ROOT / ("local_data/evaluations" if args.live else "evaluation")
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / ("latest_live.json" if args.live else "offline_results.json")
    encoded = json.dumps(report, indent=2)
    destination.write_text(encoded)
    if args.live:
        # Keep a dated copy so new experiments do not erase earlier evidence.
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        (directory / f"run_{stamp}.json").write_text(encoded)
    print(f"Report: {destination}")
    if any(result["status"] in {"failed", "error"} for result in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
