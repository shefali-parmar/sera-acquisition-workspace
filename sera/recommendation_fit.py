"""Deterministic checks for supported buyer criteria, separate from AI interpretation.

Only the structured Applied filters snapshot and narrow explicit price/patient
bounds are understood. Other prose, preferences and diligence judgments are not
silently converted into filters. These checks do not establish overall deal fit.
"""

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from pydantic import ValidationError

from sera.geography import distance_miles
from sera.models import Filters
from sera.search_location import validate_distance_filters

_AMOUNT = r"\$?\s*(\d[\d,]*(?:\.\d+)?)\s*(million|thousand|m|k)?\b"
_CAP_PATTERNS = (
    (r"(?:\bunder\b|\bbelow\b|\bless than\b|<)\s*" + _AMOUNT, False),
    (r"\b(?:up to|at most|no more than)\s*" + _AMOUNT, True),
    (
        r"\b(?:max(?:imum)?(?:\s+asking[- ]price)?(?:\s+budget|\s+price|\s+cap)?|"
        r"(?:asking[- ]price\s+|practice[- ]price\s+)?budget(?:\s+cap)?|price cap|cap)"
        r"\s*(?:(?:is now|now|is|of|to|at|drops? to|falls? to|changes? to|increases? to|decreases? to)\s*)?"
        r"[:=]?\s*" + _AMOUNT,
        True,
    ),
    (_AMOUNT + r"\s+(?:asking[- ]price\s+|practice[- ]price\s+)?(?:budget|cap)\b", True),
)
_PATIENT_PATTERNS = (
    r"\b(?:at least|minimum(?: of)?|min(?:imum)?(?: active)? patients?\s*[:=])\s*"
    r"(\d[\d,]*)\s*(?:active\s+)?patients?\b",
    r"\b(\d[\d,]*)\s*\+\s*(?:active\s+)?patients?\b",
    r"\bminimum (?:active )?patients?\s*[:=]?\s*(\d[\d,]*)\b",
)


def _question_text(value: str) -> str:
    """Extract the actual user request from the backend's stored request wrapper."""
    match = re.search(r"(?:^|\n)Request:\s*(.*)", value, re.S)
    if match:
        value = match.group(1).split("\nRequired practice IDs to retrieve", 1)[0]
    return value.strip()


def _soft_at(text: str, start: int) -> bool:
    prefix = re.split(r"[.;!?\n]|\b(?:but|however|instead)\b", text[:start], flags=re.I)[-1]
    preference = re.search(
        r"\b(?:prefer|preference|ideally|nice to have|would like)\b", prefix, re.I
    )
    return bool(
        preference
        and not re.search(
            r"\b(?:must|require|required|mandatory)\b", prefix[preference.end() :], re.I
        )
    )


def _amount(number: str, unit: str | None) -> int | None:
    try:
        value = (
            Decimal(number.replace(",", ""))
            * {
                "million": 1_000_000,
                "m": 1_000_000,
                "thousand": 1000,
                "k": 1000,
                "": 1,
            }[(unit or "").lower()]
        )
        return int(value) if value == value.to_integral_value() else None
    except (InvalidOperation, KeyError):
        return None


def _bounds(text: str) -> tuple[dict, str]:
    text = _question_text(text)
    caps, spans = set(), []
    for pattern, inclusive in _CAP_PATTERNS:
        for match in re.finditer(pattern, text, re.I):
            if any(match.start() < end and match.end() > start for start, end in spans):
                continue
            if _soft_at(text, match.start()):
                continue
            # Currency can qualify an operating metric without being a price cap.
            # Only adjacent named metrics are excluded; no new constraint is inferred.
            if re.search(
                r"\b(?:(?:annual|reported|seller[- ]reported)\s+)?"
                r"(?:revenue|(?:normalized\s+)?EBITDA|(?:annual\s+)?(?:base\s+)?rent|"
                r"CAM|occupancy(?:\s+costs?)?|(?:net\s+)?profit|cash\s+flow|earnings)"
                r"\s*(?:(?:is|must be|should be|strictly|budget|cap)\s*)?$",
                text[max(0, match.start() - 100) : match.start()],
                re.I,
            ):
                continue
            # Generic comparisons can describe years/patients/counts, not dollars.
            price_designation = re.search(r"\b(?:price|budget|cap)\b", match.group(), re.I)
            adjacent_price = re.search(
                r"\b(?:price|budget|cap)\s*(?:(?:is|must be|should be|strictly)\s*)?$",
                text[max(0, match.start() - 60) : match.start()],
                re.I,
            )
            if not ("$" in match.group() or match.group(2) or price_designation or adjacent_price):
                continue
            # An explicitly negated bound is not a replacement cap.
            if re.search(
                r"\b(?:not|never|no longer)\s*$",
                text[max(0, match.start() - 24) : match.start()],
                re.I,
            ):
                continue
            value = _amount(match.group(1), match.group(2))
            if value is None:
                return {}, "Use a whole-dollar practice asking-price cap."
            caps.add((value, inclusive))
            spans.append(match.span())
    patients = set()
    for pattern in _PATIENT_PATTERNS:
        for match in re.finditer(pattern, text, re.I):
            if not _soft_at(text, match.start()):
                patients.add(int(match.group(1).replace(",", "")))
    if len(caps) > 1 or len(patients) > 1:
        return (
            {},
            "Confirm one practice asking-price cap and one minimum active-patient count; this request contains conflicting bounds.",
        )
    if caps:
        property_topic = bool(
            re.search(r"\b(?:property|building|real[- ]estate|premises)\b", text, re.I)
        )
        combined = bool(
            re.search(
                r"\b(?:combined|total|all[- ]in)\s+(?:acquisition\s+)?(?:budget|cap|cost)\b|"
                r"\b(?:budget|cap)\b[^.;!?\n]{0,60}\b(?:combined|total|all[- ]in|including (?:the )?(?:property|building))\b|"
                r"\b(?:practice|business)\s+and\s+(?:the\s+)?(?:property|building)\b[^.;!?\n]{0,60}\b(?:together|combined|total|all[- ]in)\b",
                text,
                re.I,
            )
        )
        explicit_business = bool(
            re.search(r"\b(?:practice|business|asking)[- ](?:asking[- ])?price\b", text, re.I)
        )
        if property_topic and combined:
            # Clearly combined budgets need separately sourced property arithmetic,
            # never an inferred cap on the business asking price alone.
            return {"max_price": None, "_combined_budget": True}, ""
        if property_topic and not explicit_business:
            return (
                {},
                "Is this cap for the practice asking price only, the property only, or both? The practice and property prices are separate.",
            )
    result = {}
    if caps:
        result["max_price"], result["max_price_inclusive"] = next(iter(caps))
    if patients:
        result["min_patients"] = next(iter(patients))
    return result, ""


def _money(value: int) -> str:
    return f"${value:,.0f}"


def build_fit_context(
    records: dict[str, dict], goals: str, question: str, prior_questions: list[str]
) -> dict:
    """Evaluate retrieved records against captured filters plus explicit later bounds.

    A supported current question overrides earlier questions, which override the
    original snapshot. Conflicting bounds or property-budget ambiguity require
    clarification. Unsupported prose is not parsed into additional requirements.
    """
    filters, clarification, notes = None, "", []
    markers = list(re.finditer(r"(?:^|\n)Applied filters:[ \t]*", goals))
    marker = markers[-1] if markers else None
    if marker:
        try:
            filters = Filters.model_validate_json(goals[marker.end() :].strip())
        except (ValidationError, ValueError):
            clarification = (
                "The captured search criteria are invalid; review and apply your filters again."
            )
    else:
        changes, clarification = _bounds(goals)
        if changes.pop("_combined_budget", False):
            notes.append(
                "The explicitly combined practice-and-property budget is not assessed as a practice asking-price cap; compare the separately recorded prices and additional costs."
            )
        if changes:
            filters = Filters(**changes)
    snapshot_issue = clarification if marker and filters is None else ""
    for index, text in enumerate([*prior_questions, question]):
        # A previous explicit scenario is not a lasting change to the buyer's cap.
        # The current question may still assess that scenario on its own turn.
        previous_scenario = index < len(prior_questions) and re.search(
            r"^(?:(?:what\s+)?if\b[^.!?;\n]{0,160}\b(?:were|would|could)\b|"
            r"(?:suppose|hypothetically|in a hypothetical scenario)\b)",
            _question_text(text),
            re.I,
        )
        if previous_scenario:
            continue
        changes, issue = _bounds(text)
        if issue:
            clarification = issue
        elif changes:
            if changes.pop("_combined_budget", False):
                notes.append(
                    "The explicitly combined practice-and-property budget is not assessed as a practice asking-price cap; compare the separately recorded prices and additional costs."
                )
            filters = Filters.model_validate({**(filters or Filters()).model_dump(), **changes})
            # A later explicit replacement resolves an earlier numeric ambiguity.
            clarification = snapshot_issue
    rows = []
    origin = None
    if filters is not None:
        try:
            origin = validate_distance_filters(filters)
        except ValueError as error:
            clarification = str(error)
    for pid, record in records.items():
        matched, failed, unverified = [], [], []

        def check(label: str, value, passes: bool) -> None:
            (unverified if value is None else matched if passes else failed).append(label)

        if filters is not None:
            if filters.specialties:
                check(
                    "Specialty: " + ", ".join(filters.specialties),
                    record.get("specialty"),
                    record.get("specialty") in filters.specialties,
                )
            if filters.max_distance_miles is not None:
                miles = (
                    distance_miles(origin, record.get("city", ""), record.get("state", ""))
                    if origin
                    else None
                )
                check(
                    f"Within {filters.max_distance_miles:g} miles of search origin",
                    miles,
                    miles is not None and miles <= filters.max_distance_miles,
                )
            else:
                if filters.states:
                    check(
                        "State: " + ", ".join(filters.states),
                        record.get("state"),
                        record.get("state") in filters.states,
                    )
                if filters.city.strip():
                    city = record.get("city")
                    check(
                        "City: " + filters.city.strip(),
                        city,
                        city is not None and city.casefold() == filters.city.strip().casefold(),
                    )
            check(
                "Availability: " + (", ".join(filters.statuses) or "none selected"),
                record.get("status"),
                record.get("status") in filters.statuses,
            )
            price = record.get("asking_price")
            if price is None:
                unverified.append("Budget unverified — asking price undisclosed")
            elif filters.max_price is not None:
                operator = "up to" if filters.max_price_inclusive else "under"
                check(
                    f"Asking price {operator} {_money(filters.max_price)} (recorded {_money(price)})",
                    price,
                    price <= filters.max_price
                    if filters.max_price_inclusive
                    else price < filters.max_price,
                )
            for field, value, label in (
                ("min_patients", record.get("active_patients"), "active patients"),
                (
                    "min_years",
                    None
                    if record.get("founding_year") is None
                    else date.today().year - record["founding_year"],
                    "years operating",
                ),
                ("min_sqft", record.get("sqft"), "square feet"),
                ("min_operatories", record.get("operatories"), "operatories"),
            ):
                minimum = getattr(filters, field)
                if minimum:
                    check(
                        f"At least {minimum:,} {label} (recorded {value if value is not None else 'unknown'})",
                        value,
                        value is not None and value >= minimum,
                    )
            if filters.keyword.strip():
                values = [record.get(field) for field in ("name", "specialty", "description")]
                haystack = " ".join(value for value in values if isinstance(value, str)).casefold()
                passes = filters.keyword.strip().casefold() in haystack
                check(
                    "Keyword: " + filters.keyword.strip(),
                    True if passes or all(value is not None for value in values) else None,
                    passes,
                )
        elif record.get("asking_price") is None:
            unverified.append("Budget unverified — asking price undisclosed")
        rows.append(
            {
                "practice_id": pid,
                "name": record.get("name", pid),
                "matched": matched,
                "failed": failed,
                "unverified": unverified,
            }
        )
    return {
        "filters": filters.model_dump() if filters is not None else None,
        "rows": rows,
        "clarification": clarification,
        "notes": list(dict.fromkeys(notes)),
    }


def _sentences(answer: str) -> list[str]:
    # Currency decimals are rare in fit claims; retain table rows as independent clauses.
    return [
        part.strip()
        for part in re.split(
            r"(?<=[.!?])\s+|\n|;|,?\s+\b(?:but|whereas|however|while)\b\s+", answer, flags=re.I
        )
        if part.strip()
    ]


def _negative_budget_issues(answer: str, context: dict) -> list[str]:
    """Check only explicit price failures, not general disqualification language."""
    fitting = [
        row
        for row in context.get("rows", [])
        if any(label.startswith("Asking price ") for label in row.get("matched", []))
    ]
    if not fitting or context.get("clarification"):
        return []
    target = r"(?:(?:the|your|my)\s+)?(?:(?:practice\s+)?asking[- ]price\s+|price\s+)?(?:cap|budget)(?:\s+cap)?"
    negative = re.compile(
        r"\b(?:fails?\s+|(?:is\s+)?(?:above|over|outside)\s+|(?:does not|doesn't)\s+(?:meet|fit)\s+|not within\s+)"
        + target,
        re.I,
    )
    global_claim = re.compile(
        r"\b(neither|none|no candidate|no practice)\s+(?:of (?:them|these|the candidates)\s+)?(?:meets?|fits?|satisf(?:y|ies)|is within|are within)\s+"
        + target,
        re.I,
    )
    issues = []
    for sentence in _sentences(answer):
        global_match = global_claim.search(sentence)
        if global_match and not re.search(
            r"\b(?:not|false|incorrect)\b", sentence[: global_match.start()], re.I
        ):
            if global_match.group(1).casefold() != "neither" or len(context.get("rows", [])) == 2:
                issues.append(
                    "Do not say all assessed candidates fail the asking-price cap: at least one recorded asking price meets it."
                )
        for row in fitting:
            if not re.search(
                r"\b(?:" + re.escape(row["name"]) + "|" + re.escape(row["practice_id"]) + r")\b",
                sentence,
                re.I,
            ):
                continue
            for claim in negative.finditer(sentence):
                if re.search(
                    r"\b(?:not|doesn't|does not|cannot|can't)\b[^.!?;]*$",
                    sentence[max(0, claim.start() - 30) : claim.start()],
                    re.I,
                ):
                    continue
                issues.append(
                    f"Do not say {row['name']} fails the asking-price cap; its recorded asking price meets the assessed cap."
                )
    return list(dict.fromkeys(issues))


def fit_claim_issues(answer: str, context: dict) -> list[str]:
    """Catch narrow positive fit/recommendation claims contradicted by assessed facts.

    This is conservative phrase checking, not a general semantic validator.
    Negated claims and explicit hypothetical changes to the constraints are left
    alone. A diligence caveat cannot excuse a known numerical failure.
    """
    issues = _negative_budget_issues(answer, context)
    for row in context.get("rows", []):
        failures, unknowns = row.get("failed", []), row.get("unverified", [])
        if not failures and not unknowns and not context.get("clarification"):
            continue
        names = [re.escape(row["practice_id"]), re.escape(row["name"])]
        for sentence in _sentences(answer):
            if not re.search(r"\b(?:" + "|".join(names) + r")\b", sentence, re.I):
                continue
            # A genuine future change in requirements is not a current-fit claim.
            condition = re.search(r"\b(?:if|assuming|provided)\b([^,.;!?]*)", sentence, re.I)
            if (
                condition
                and re.search(
                    r"\b(?:budget|cap|minimum|requirements?|constraints?|patient count)\b",
                    condition.group(1),
                    re.I,
                )
                and re.search(
                    r"\b(?:raise[ds]?|increase[ds]?|lower(?:ed)?|remove[ds]?|relax(?:ed)?|change[ds]?|reduce[ds]?|waiv(?:e[ds]?|ing))\b",
                    condition.group(1),
                    re.I,
                )
            ):
                continue
            positives = re.finditer(
                r"\b(?:meets? (?:all|every|the) (?:buyer )?(?:hard )?(?:requirements?|criteria|constraints?)|qualif(?:y|ies)|(?:within|fits?) (?:the |your |my )?(?:asking[- ]price )?(?:\$[\d,.]+\s*(?:million|thousand|m|k)?\s*)?(?:budget|cap)|recommend(?:ed|s)?|best fit|top pick)\b",
                sentence,
                re.I,
            )
            for positive in positives:
                before = sentence[max(0, positive.start() - 55) : positive.start()]
                if re.search(
                    r"\b(?:not|never|cannot|can't|doesn't|does not|do not|don't|no candidate|no practice|no recommendation)\b[^.!?;]*$",
                    before,
                    re.I,
                ):
                    continue
                recommendation = positive.group().casefold().startswith("recommend")
                if recommendation and re.search(
                    r"\brecommend(?:ed|s)?\s+(?:reviewing|verifying|checking|requesting|asking|further diligence|due diligence)\b|"
                    r"\bfor (?:further )?(?:due diligence|review|investigation)\b",
                    sentence,
                    re.I,
                ):
                    continue
                if (
                    recommendation
                    and not failures
                    and not context.get("clarification")
                    and re.search(r"\b(?:subject to|conditional on|pending)\b", sentence, re.I)
                ):
                    continue
                budget_claim = bool(re.search(r"\b(?:budget|cap)\b", positive.group(), re.I))
                budget_block = any(
                    "asking price" in label.casefold() for label in failures + unknowns
                )
                if budget_claim and not budget_block and not context.get("clarification"):
                    continue
                issue = (
                    f"Do not present {row['name']} as meeting the assessed requirements or recommend it unconditionally: "
                    + "; ".join(failures + unknowns)
                )
                if context.get("clarification"):
                    issue += "; clarify the buyer constraints first"
                if issue not in issues:
                    issues.append(issue)
    return issues


def format_fit_context(context: dict) -> str:
    """Buyer-visible deterministic criteria check; not an overall verification badge."""
    has_assessment = any(
        any(row.get(key) for key in ("matched", "failed", "unverified"))
        for row in context.get("rows", [])
    )
    if not has_assessment and not context.get("clarification"):
        return ""
    lines = [
        "### Recorded criteria check",
        "Asking-price checks exclude property price and total acquisition costs. Only assessed criteria are shown, not overall fit or independent verification.",
    ]
    if context.get("clarification"):
        lines.append("**Clarification needed:** " + context["clarification"])
    lines.extend(context.get("notes", []))
    if context.get("filters") is None:
        lines.append("No supported hard criteria were supplied for assessment.")
    for row in context.get("rows", []):
        parts = []
        for label, key in (
            ("Matched", "matched"),
            ("Failed", "failed"),
            ("Unverified", "unverified"),
        ):
            if row.get(key):
                parts.append(f"{label}: " + "; ".join(row[key]))
        if parts:
            lines.append("- **" + row["name"].replace("\n", " ") + "** — " + " · ".join(parts))
    return re.sub(r"(?<!\\)\$(?=\d)", r"\\$", "\n\n".join(lines))
