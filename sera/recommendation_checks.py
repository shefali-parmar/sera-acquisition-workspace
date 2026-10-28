"""Conservative checks for explicit record claims, not a semantic fact checker.

Only locally attributable claims are checked. Ambiguous multi-practice prose,
most derived totals/ratios, subjective rankings, and buyer requirements need separate
checks. Passing these rules does not establish that an answer is grounded.
"""

import math
import re

_CITATION = re.compile(r"\bSERA-\d{3}-S\d+\b", re.I)
_AMOUNT = re.compile(
    r"(?<![\w.-])(?P<dollar>\$)?(?P<number>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)"
    r"\s*(?P<scale>million|thousand|[km])?(?!\w)",
    re.I,
)
_METRICS = (
    (
        "combined_price",
        r"combined\s+(?:(?:practice|business)\s*(?:and|\+)\s*(?:property|building)\s+)?"
        r"(?:asking[- ]price(?:\s+subtotal)?|purchase[- ]price)",
    ),
    ("property_price", r"(?:property|real[- ]estate|building)\s+(?:(?:asking|purchase)\s+)?price"),
    ("rent_cam", r"(?:combined|total)\s+(?:annual\s+)?(?:rent\s*(?:and|\+)\s*CAM|occupancy cost)"),
    ("rent", r"(?:(?:annual|monthly)\s+)?(?:base\s+)?rent"),
    ("cam", r"(?:(?:annual|monthly)\s+)?CAM"),
    ("ebitda", r"(?:normalized\s+)?EBITDA"),
    ("revenue", r"(?:annual\s+)?revenue"),
    ("patients", r"active patients|patient count|patients"),
    ("price", r"(?:(?:practice|business|asking|purchase|acquisition)\s+)?(?:asking\s+)?price"),
)
_THRESHOLD = re.compile(
    r"\b(?:budget|cap|threshold|at least|at most|under|below|up to|less than|more than|"
    r"minimum|maximum|target|assume|assuming|hypothetical)\b",
    re.I,
)


def _owners(text: str, records: dict[str, dict]) -> set[str]:
    text = _CITATION.sub("", text)
    return {
        pid
        for pid, record in records.items()
        if any(
            re.search(r"\b" + re.escape(alias) + r"\b", text, re.I)
            for alias in (pid, record.get("name", ""))
            if alias
        )
    }


def _guidance(text: str) -> bool:
    """Questions and explicitly hypothetical/document-request clauses are not facts."""
    text = re.sub(r"^[\s*#>\-]+", "", text)
    return text.rstrip().endswith("?") or bool(
        re.match(
            r"(?:if\b|assum(?:e|ing)\b|hypothetical\b|scenario\b|"
            r"(?:please\s+)?(?:ask|verify|confirm|request|check|obtain)\b|"
            r"(?:the )?buyer (?:must|should|needs? to) (?:verify|confirm|obtain|check)\b)",
            text,
            re.I,
        )
    )


def _negated(text: str, start: int) -> bool:
    prefix = text[max(0, start - 80) : start].replace("’", "'")
    prefix = re.sub(r'["“”‘*`]+', "", prefix)
    # Keep negation local; unrelated earlier disclaimers cannot exempt a later claim.
    return bool(
        re.search(
            r"\b(?:no|not|never|neither|cannot|can't|without|isn't|aren't|wasn't|hasn't|haven't)"
            r"(?:\s+[\w'-]+){0,6}\s*$",
            prefix,
            re.I,
        )
    )


def _denied_after(text: str) -> bool:
    text = re.sub(r'["“”‘*`]+', "", text.replace("’", "'"))
    # A denied answer label ("Legally cleared: No") is not an assurance.
    if re.match(r"\s*:\s*(?:no|not|unknown|unverified)\b", text, re.I):
        return True
    return bool(
        re.match(
            r"\s+(?:(?:is|are|was|were)\s+)?(?:not\s+(?:supported|established|verified|recorded)|"
            r"cannot\s+be|can't\s+be|does\s+not\s+exist|doesn't\s+exist)\b",
            text,
            re.I,
        )
    )


def _assurance_issues(text: str, record: dict | None) -> list[str]:
    if _guidance(text):
        return []
    patterns = (
        (
            r"\bguarantee(?:d|s)?\s+(?:to be\s+)?(?:profitable|profits?|returns?|ROI)\b|"
            r"\b(?:profitability|profits?|returns?|ROI)\s+(?:is|are)\s+guaranteed\b",
            "Do not guarantee profitability or investment returns.",
        ),
        (
            r"\b(?:buy|purchase|acquire)\s+[^.!?;]{0,50}?\b(?:now|immediately)\b",
            "Replace immediate purchase instructions with conditional diligence guidance.",
        ),
        (
            r"\blegally\s+(?:cleared|safe|approved)\b|\bclean legal (?:history|record)\b|"
            r"\bno legal (?:issues|risks)\b",
            "Recorded disclosures do not establish independent legal clearance.",
        ),
        (
            r"\b(?:landlord\s+)?consent\s+(?:(?:has|have)\s+(?:already\s+)?been\s+|"
            r"(?:is|was)\s+(?:already\s+)?|already\s+)?(?:obtained|secured|approved|granted)\b",
            "Landlord consent is not recorded as obtained; describe the confirmation needed.",
        ),
    )
    issues = []
    for pattern, message in patterns:
        if any(
            not _negated(text, match.start()) and not _denied_after(text[match.end() :])
            for match in re.finditer(pattern, text, re.I)
        ):
            issues.append(message)
    premises = (record or {}).get("premises") or {}
    if premises.get("property_included_in_practice_price") is not True:
        for match in re.finditer(
            r"\b(?:property|real[- ]estate|building|premises)\s+(?:(?:is|are)\s+)?"
            r"included\s+in\s+(?:the\s+)?(?:practice|business|asking|purchase)\s+price\b|"
            r"\bincludes?\s+(?:the\s+)?(?:office\s+)?(?:condominium|property|real[- ]estate|building|premises)"
            r"\s+in\s+(?:its|the)\s+(?:\$[\d,.]+\s*)?(?:practice|business|asking|purchase)\s+price\b",
            text,
            re.I,
        ):
            if not _negated(text, match.start()) and not _denied_after(text[match.end() :]):
                issues.append("Property is separately priced, not included in the practice price.")
    return issues


def _field_sources(field: str, record: dict) -> set[str]:
    primary = record.get("availability_source")
    financial = (record.get("financials") or {}).get("source")
    operations = (record.get("operations") or {}).get("source")
    premises = (record.get("premises") or {}).get("source")
    return {
        source
        for source in {
            "price": {primary},
            "revenue": {primary, financial},
            "patients": {primary, operations},
            "ebitda": {financial},
            "rent": {premises},
            "cam": {premises},
            "rent_cam": {premises},
            "property_price": {premises},
            "combined_price": {primary, premises},
        }[field]
        if source
    }


def _directional_issues(text: str, records: dict[str, dict]) -> list[str]:
    """Only compare two explicitly named subjects and one recorded metric."""
    if _guidance(text):
        return []
    fields = {field for _, _, field in _metric_matches(text)}
    if len(fields) != 1:
        return []
    field = next(iter(fields))
    issues = []
    for comparison in re.finditer(
        r"\b(higher|lower|greater|less|more|larger|smaller)\b([^;!?]*?)\bthan\b", text, re.I
    ):
        if _negated(text, comparison.start()):
            continue
        left = _owners(text[: comparison.start()], records)
        right = _owners(text[comparison.end() :], records)
        if len(left) != 1 or len(right) != 1 or left == right:
            continue
        left_id, right_id = next(iter(left)), next(iter(right))
        first, second = (
            _expected(field, records[left_id], text),
            _expected(field, records[right_id], text),
        )
        if first is None or second is None:
            continue
        higher = comparison.group(1).casefold() in {"higher", "greater", "more", "larger"}
        if not (first > second if higher else first < second):
            issues.append(
                f"Correct {field} comparison: {left_id} is {first:g} and {right_id} is {second:g}; the stated direction is unsupported."
            )
        citations = {source.upper() for source in _CITATION.findall(text)}
        for pid in (left_id, right_id):
            allowed = _field_sources(field, records[pid])
            if (
                citations
                and allowed
                and (
                    not allowed.issubset(citations)
                    if field == "combined_price"
                    else not citations.intersection(allowed)
                )
            ):
                issues.append(f"Cite {pid} {field} evidence from {', '.join(sorted(allowed))}.")
    return issues


def _metric_matches(text: str) -> list[tuple[int, int, str]]:
    found = sorted(
        (match.start(), match.end(), field)
        for field, pattern in _METRICS
        for match in re.finditer(r"\b(?:" + pattern + r")\b", text, re.I)
    )
    # Prefer the longest containing label: 'property asking price' is not business price.
    return [
        item
        for item in found
        if not any(
            other[0] <= item[0] and other[1] >= item[1] and other[:2] != item[:2] for other in found
        )
    ]


def _expected(field: str, record: dict, context: str) -> float | None:
    financials, premises = record.get("financials") or {}, record.get("premises") or {}
    value = {
        "price": record.get("asking_price"),
        "revenue": record.get("annual_revenue"),
        "patients": record.get("active_patients"),
        "ebitda": financials.get("normalized_ebitda"),
        "rent": premises.get("annual_base_rent"),
        "cam": premises.get("annual_cam"),
        "property_price": premises.get("property_asking_price"),
        "combined_price": (
            record["asking_price"] + premises["property_asking_price"]
            if record.get("asking_price") is not None
            and premises.get("property_asking_price") is not None
            else None
        ),
        "rent_cam": (
            premises["annual_base_rent"] + premises["annual_cam"]
            if premises.get("annual_base_rent") is not None
            and premises.get("annual_cam") is not None
            else None
        ),
    }[field]
    if (
        value is not None
        and field in {"rent", "cam", "rent_cam"}
        and re.search(r"\bmonthly\b|\bper month\b|/mo(?:nth)?\b", context, re.I)
    ):
        value /= 12
    return value


def _numeric_issues(text: str, pid: str, record: dict, *, header: str = "") -> list[str]:
    if _guidance(text):
        return []
    clean = _CITATION.sub("", text).replace("**", "")
    metrics = _metric_matches(clean)
    if header and len(_metric_matches(header)) == 1:
        metrics = [(-len(header), 0, _metric_matches(header)[0][2])]
    issues = []
    for amount in _AMOUNT.finditer(clean):
        if not metrics:
            continue
        # Match one nearby metric without crossing another stated amount or metric.
        metric = min(
            metrics,
            key=lambda item: min(abs(amount.start() - item[1]), abs(item[0] - amount.end())),
        )
        left, right = min(metric[1], amount.end()), max(metric[0], amount.start())
        between = clean[max(0, left) : max(0, right)]
        if len(between) > 60 or _AMOUNT.search(between) or _THRESHOLD.search(between):
            continue
        if re.search(
            r"\b(?:per patient|per visit|per square foot|margin|ratio|multiple|yield)\b",
            between,
            re.I,
        ) or re.match(r"\s+(?:higher|lower|more|less)\b", clean[amount.end() :], re.I):
            continue  # Derived ratios and comparative deltas aren't the recorded metric.
        if re.search(
            r"\b(?:not|never|isn't|aren't|wasn't|cannot|can't)\b", between.replace("’", "'"), re.I
        ) or _denied_after(clean[amount.end() :]):
            continue
        if _negated(clean, min(metric[0], amount.start())):
            continue
        before = clean[max(0, amount.start() - 35) : amount.start()]
        # Buyer thresholds and general transaction totals aren't record values.
        if _THRESHOLD.search(before) and not re.search(r"\b(?:is|was|of|at)\s*$", before, re.I):
            continue
        field = metric[2]
        if (
            field != "combined_price"
            and re.search(r"\b(combined|total|together|sum)\b", clean, re.I)
            and re.search(r"\b(practice|business)\b", clean, re.I)
            and re.search(r"\b(property|real[- ]estate|building)\b", clean, re.I)
        ):
            continue
        raw, scale = amount["number"].replace(",", ""), (amount["scale"] or "").casefold()
        value = float(raw) * (
            1_000_000 if scale in {"m", "million"} else 1_000 if scale in {"k", "thousand"} else 1
        )
        if not amount["dollar"] and not scale and field != "patients":
            if not re.fullmatch(r"[\s:()=]*(?:(?:is|was|of|at|reported)\s*)?", between, re.I):
                continue
            if 1800 <= value <= 2100 and re.search(r"\b(?:year|period|calendar|FY)\b", clean, re.I):
                continue
        context = (
            header
            or clean[
                max(0, min(metric[0], amount.start()) - 10) : max(metric[1], amount.end()) + 15
            ]
        )
        expected = _expected(field, record, context)
        citations = {source.upper() for source in _CITATION.findall(text)}
        allowed = _field_sources(field, record)
        if (
            citations
            and allowed
            and (
                not allowed.issubset(citations)
                if field == "combined_price"
                else not citations.intersection(allowed)
            )
        ):
            issues.append(f"Cite {pid} {field} evidence from {', '.join(sorted(allowed))}.")
        if expected is None or not math.isclose(value, expected, rel_tol=0.000001, abs_tol=0.01):
            recorded = (
                "not recorded/applicable"
                if expected is None
                else f"{expected:,.2f}".removesuffix(".00")
            )
            issues.append(
                f"Correct {pid} {field}: recorded value is {recorded}; do not report {value:g} as a recorded fact."
            )
    return issues


def record_claim_issues(answer: str, records: dict[str, dict]) -> list[str]:
    """Check explicit local factual claims against request-local complete records.

    Tables use their headers; prose needs an exact practice name/ID or one source
    owner in its clause. Multi-owner clauses are skipped rather than assigned by
    guesswork. Questions, hypothetical values, thresholds and most derived totals
    are not checked; explicitly combined asking/purchase prices are checked against
    the practice plus property asking prices. This does not validate rankings or arbitrary prose.
    """
    issues, headers = [], []
    for line in answer.splitlines():
        # Markdown emphasis must not change sentence boundaries or negation.
        line = re.sub(r"\*\*|__|`", "", line)
        is_table = line.strip().startswith("|") and line.strip().endswith("|")
        if is_table:
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if not _owners(line, records) and not _CITATION.search(line):
                if any(_metric_matches(cell) for cell in cells):
                    headers = cells
                continue
            units = [line]
        else:
            units = re.split(
                r"(?<=[.!?;])\s+|,?\s+(?:compared (?:with|to)|versus|whereas|while|however|but)\s+",
                line,
                flags=re.I,
            )
        for unit in units:
            issues.extend(_directional_issues(unit, records))
            explicit = _owners(unit, records)
            citations = {match.upper() for match in _CITATION.findall(unit)}
            cited_owners = {source.split("-S", 1)[0] for source in citations}
            owners = explicit or cited_owners
            record = records.get(next(iter(owners))) if len(owners) == 1 else None
            issues.extend(_assurance_issues(unit, record))
            if len(owners) != 1 or record is None:
                continue
            pid = next(iter(owners))
            if citations and pid not in cited_owners and not _guidance(unit):
                issues.append(
                    f"Cite {pid}'s own evidence in its clause or comparison row; another practice's sources do not support it."
                )
            if is_table and headers and len(headers) == len(cells):
                for header, cell in zip(headers, cells):
                    if _metric_matches(header):
                        issues.extend(_numeric_issues(cell, pid, record, header=header))
            else:
                issues.extend(_numeric_issues(unit, pid, record))
    return list(dict.fromkeys(issues))
