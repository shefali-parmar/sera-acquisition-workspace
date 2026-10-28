# Recommendation reliability review — October 27, 2026

This review covers the fictional product demo's AI recommendation path, not a professional acquisition assessment or a claim of error-free AI.

## Findings and changes

The earlier evidence checks established retrieval and source existence. Scripted probes showed that incorrect budget fit, swapped EBITDA values, exchanged comparison-row citations and guaranteed-profit language could nevertheless return `complete`. These were controlled validator failures, not four observed Gemini failures.

The application now:

- Calculates supported criteria from validated captured filters and narrow explicit budget/patient-count updates, with latest questions taking precedence. It preserves exclusive versus inclusive caps and treats missing prices as unverified.
- Supplies those calculations alongside fresh records and displays a separate **Recorded criteria check**. Priorities remain distinct from hard search criteria.
- Checks locally attributable numeric facts, candidate/source ownership, metric-specific sources and narrow higher/lower comparisons against the retrieved records. It checks explicit unsupported profit, legal-clearance, landlord-consent and property-inclusion assurances.
- Requests clarification for conflicting numeric bounds or ambiguous property-budget scope. An explicitly combined budget is kept separate from the practice asking-price check.
- Allows one corrective revision. Repeated detected failures preserve recorded facts and withhold the recommendation. Failed drafts are excluded from retained conversation history.
- Keeps an attached candidate for “Recommend the practice” and retains the acquisition comparison format when a later sentence asks to separate property prices.

## Controlled regressions

The tests include strict/equal/inclusive price boundaries, zero budgets, price omission, patient floors, changed caps, chronological follow-ups, subjective preferences, supported geographic and operating criteria, copied/swap errors, wrong-source rows and financial/property sources. Positive contrasts cover correct values, valid comparisons, questions, negation, hypothetical scenarios and conditional diligence. Integration tests verify the actual repair/fallback boundary, visible criteria checks and preserved evidence/history. No test makes a provider request.

## Live review method

Use the public app's configured Gemini provider with fictional prompts only. Review the visible answer against current catalog records; count response completion separately from factual/decision correctness. Record each case and any fallback or interpretation failure. A bounded sample is not an accuracy estimate, and the review is not expert ground truth.

The initial hosted baseline correctly rejected both Riverbend ($650,000; 850 patients) and Elmbrook ($1,150,000; 1,525 patients) for the combined requirements **strictly under $1,150,000** and **at least 1,000 patients**. It also kept Elmbrook's $392,000 property price separate. This is one observed pass before the new guards.

## Remaining limits

These rules cover explicit, locally attributable statements. They do not prove arbitrary prose, cross-sentence associations, derived totals/ratios, valuation reasoning, subjective priority weighting or every possible recommendation. The deterministic check evaluates supported captured criteria and narrow recognized updates; other conversational requirements still require interpretation and buyer review. Open-ended discovery still relies on the model to translate the request into supported tool filters, and a returned subset is not proof of exhaustive search.

All evidence is fictional and seller/simulated reporting is not independent verification. A matching price/patient threshold does not establish financial health, legal clearance, valuation or suitability. Public-session request limits are not a billing ceiling. Preserve and review recorded facts when an AI assessment is incomplete.
