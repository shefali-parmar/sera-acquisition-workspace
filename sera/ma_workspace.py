"""Buyer-controlled M&A work requests and portable conversation notes."""

from dataclasses import dataclass

from sera.models import Practice


@dataclass(frozen=True)
class DealTask:
    label: str
    icon: str
    description: str
    request: str
    minimum_targets: int = 0


def deal_tasks(practices: list[Practice]) -> tuple[DealTask, ...]:
    """Named targets prevent task drafts from accidentally starting new discovery."""
    names = "; ".join(practice.name for practice in practices)
    subject = names or "a prospective medical or dental practice acquisition"
    property_subject = (
        f"the premises for {names}" if practices else "a prospective commercial or medical property"
    )
    basis = (
        "Use current recorded evidence and separate facts, interpretation and missing information. "
        if practices
        else "Give general process guidance; do not assume facts about a particular practice. "
    )
    return (
        DealTask(
            "Review a target",
            ":material/description:",
            "Review the selected practice as a business: finances, patients, staffing, operations and owner transition.",
            f"Prepare an acquisition review for {subject}. "
            "What fits my priorities, what needs more investigation, and what should I verify next?",
            1,
        ),
        DealTask(
            "Compare practices",
            ":material/compare_arrows:",
            "Compare two or three targets using the same criteria, with unknowns kept visible.",
            f"Compare acquisition targets: {subject}. {basis}"
            "Compare each against the same buyer requirements. Explain asking-price fit, "
            "supported tradeoffs and what I must verify before deciding. Keep missing information visible; "
            "asking price is not total acquisition cost and revenue is not profit.",
            2,
        ),
        DealTask(
            "Evaluate a practice",
            ":material/fact_check:",
            "Assess the business: finances, patients, staffing, operations and owner transition before making an offer.",
            f"Help me prepare an acquisition review for {subject}. "
            "How should I assess financial performance, operations, and owner transition before making an offer?",
        ),
        DealTask(
            "Prepare seller questions",
            ":material/forum:",
            "Draft a focused seller agenda grounded in recorded facts and unanswered questions.",
            f"Prepare seller questions for {subject}. {basis}"
            "Draft a short meeting agenda grouped by financials, operations and transition, and outstanding diligence. "
            "Connect questions to known gaps without assuming seller intent or treating an unanswered question as a confirmed concern.",
        ),
        DealTask(
            "Lease or buy?",
            ":material/real_estate_agent:",
            "Compare renting versus owning a space: occupancy costs, upfront capital, flexibility and holding period.",
            f"Should I lease or buy {property_subject}? "
            "Help me compare costs, upfront capital, flexibility, and the information I need before deciding.",
        ),
        DealTask(
            "Assess a property",
            ":material/domain:",
            "Assess the physical space: permitted use, layout, accessibility, parking and renovation needs.",
            f"How should I assess whether {property_subject} fits my intended use? "
            "Help me check permitted use, layout, accessibility, parking, and fit-out needs. "
            "What should I confirm with the landlord or broker?",
        ),
    )


def deal_notes(
    chat: list[dict],
    practices: list[Practice],
    criteria: str,
    priorities: str,
    render_answer,
    *,
    missing_targets: list[str] | None = None,
) -> str:
    """Export the visible conversation and its captured scope, not internal messages."""
    targets = (
        "; ".join(
            [practice.name for practice in practices]
            + [f"Unavailable practice ({pid})" for pid in (missing_targets or [])]
        )
        or "Catalog research"
    )
    sections = [
        "# SERA acquisition and property working notes",
        "Fictional demo evidence. AI interpretations and process guidance require review.",
        f"**Current targets:** {targets}\n\n**Captured search criteria:** {criteria}"
        f"\n\n**Captured acquisition priorities:** {priorities}",
        "Target scope can change during the conversation; each exchange retains its wording.",
    ]
    for entry in chat:
        label = "Buyer" if entry["role"] == "user" else "SERA"
        sections.append(f"## {label}\n\n{render_answer(entry['content'])}")
    sections.append(
        "Session working notes only. This is not a valuation or completed due diligence."
    )
    return "\n\n".join(sections) + "\n"
