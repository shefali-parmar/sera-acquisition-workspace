# Recommendation reliability review — October 27, 2026

This review covers the fictional product demo's AI recommendation path, not a professional acquisition assessment or a claim of error-free AI.

## Findings and changes

The earlier evidence checks established retrieval and source existence. Scripted probes showed that incorrect budget fit, swapped EBITDA values, exchanged comparison-row citations and guaranteed-profit language could nevertheless return `complete`. These were controlled validator failures, not four observed Gemini failures.

The application now:

- Calculates supported criteria from validated captured filters and narrow explicit budget/patient-count updates, with latest questions taking precedence. It preserves exclusive versus inclusive caps and treats missing prices as unverified.
- Supplies those calculations alongside fresh records and displays a separate **Recorded criteria check**. Priorities remain distinct from hard search criteria.
- Checks locally attributable numeric facts, candidate/source ownership, metric-specific sources and narrow higher/lower comparisons against the retrieved records. It checks explicit unsupported profit, legal-clearance, landlord-consent and property-inclusion assurances.
- Requests clarification for conflicting numeric bounds or ambiguous property-budget scope. An explicitly combined budget is kept separate from the practice asking-price check.
- Supplies the arithmetic sum of known, separately recorded business/property asking prices. A locally reproduced checker bug that compared a correct combined subtotal against the business price alone is fixed; explicit combined asking-price statements are checked against both amounts and their sources. Other transaction costs remain excluded.
- Allows one corrective revision. Repeated detected failures preserve recorded facts and withhold the recommendation. Failed drafts are excluded from retained conversation history.
- Keeps an attached candidate for “Recommend the practice” and retains the acquisition comparison format when a later sentence asks to separate property prices.

## Controlled regressions

The tests include strict/equal/inclusive price boundaries, zero budgets, price omission, patient floors, changed caps, chronological follow-ups, subjective preferences, supported geographic and operating criteria, copied/swap errors, wrong-source rows and financial/property sources. Positive contrasts cover correct values, valid comparisons, questions, negation, hypothetical scenarios and conditional diligence. Integration tests verify the actual repair/fallback boundary, visible criteria checks and preserved evidence/history. No test makes a provider request.

## Live review method

Use the public app's configured Gemini provider with fictional prompts only. Review the visible answer against current catalog records; count response completion separately from factual/decision correctness. Record each case and any fallback or interpretation failure. A bounded sample is not an accuracy estimate, and the review is not expert ground truth.

The initial hosted baseline correctly rejected both Riverbend ($650,000; 850 patients) and Elmbrook ($1,150,000; 1,525 patients) for the combined requirements **strictly under $1,150,000** and **at least 1,000 patients**. It also kept Elmbrook's $392,000 property price separate. This is one observed pass before the new guards.

## Observed public Gemini results

After a host restart on `d109b91`, the following nine requests were reviewed against the catalog. These are individual observations, not a statistical accuracy score. Export working notes was downloaded and reopened for the three-candidate case, preserving the names, facts, eligibility distinctions and calculated criteria.

| Case | Observed result |
| --- | --- |
| Strictly under $1,150,000 and at least 1,000 active patients | Correctly rejected Riverbend for 850 patients and Elmbrook for equality with the exclusive cap. Calculated criteria appeared. |
| Follow-up changes only the cap to up to $1,150,000 | Correctly made Elmbrook eligible, while Riverbend still failed the patient minimum. Calculated criteria appeared. This also verified the property-cost-reminder routing fix. |
| Three candidates, up to $1,200,000 and at least 1,000 patients | Correctly distinguished Riverbend's failed patient minimum, Torrey Pines' undisclosed/unverified budget and Elmbrook's matched criteria. Conditionally prioritized Elmbrook for diligence. |
| Combined $1,500,000 business/property budget, subtotal and legal-assurance question | Facts-only fallback; no complete answer or recommendation. The hidden draft was not inspected, so the specific live failure cause is unconfirmed. |
| Narrower follow-up asks only for separately recorded prices and subtotal | Correct $1,150,000 business price, $392,000 property price and $1,542,000 arithmetic subtotal; property was separate and legal clearance was not asserted. |
| Broad lower-entry-price priority comparison, no patient minimum | Facts-only fallback. Both candidates' matched price checks remained visible; no ranking was presented. |
| Follow-up prioritizes reported normalized EBITDA | Correct $187,000 Riverbend and $386,000 Elmbrook, with their own financial sources; conditionally prioritized Elmbrook. Both budget checks stayed matched and net profit remained unknown. |
| Follow-up switches priority to lower business asking price | Correctly switched to Riverbend ($650,000 versus $1,150,000), while both budget checks stayed matched. |
| Legal-clearance/landlord-consent question for Riverbend and Torrey Pines | Facts-only fallback; no legal assurance, but the requested legal/consent explanation was not completed. |

[Hosted three-candidate comparison screenshot](images/recommendation-three-practices.png).

The inclusive-boundary answer before `d109b91` was factually correct but omitted the application-calculated criteria because a property-separation reminder misrouted it. The post-fix repeat above showed the criteria. A local probe also established that an explicitly combined asking-price subtotal could be wrongly checked against the business price alone; `7fc9ef1` corrects that distinct reproducible checker bug and supplies the arithmetic subtotal to the model. This does not establish that this bug caused the earlier hosted fallback.

After publishing `7fc9ef1`, the clean [GitHub Linux release workflow](https://github.com/shefali-parmar/sera-acquisition-workspace/actions/runs/40616701766) succeeded. The public host was rebooted and loaded with AI configured. The exact combined-budget/subtotal/legal-assurance question was then repeated once: it still returned facts only, with both correct asking prices preserved. The arithmetic checker regression is fixed, but this live completion failure remains unresolved; no causal claim is made about the discarded draft. [Observed incomplete answer](images/recommendation-incomplete.png).

The final isolated local suite passed **476 tests in 12.15 seconds**, including **144 added recommendation regressions**. Lint, formatting of all 45 Python files, dependency consistency and offline evaluation passed (5 passed, 6 live-only skipped). Fourteen upstream deprecation warnings remain. Controlled tests make no provider calls; skipped evaluations are not successes.

## Remaining limits

These rules cover explicit, locally attributable statements. They do not prove arbitrary prose, cross-sentence associations, most derived totals/ratios, valuation reasoning, subjective priority weighting or every possible recommendation. The deterministic check evaluates supported captured criteria and narrow recognized updates; other conversational requirements still require interpretation and buyer review. Open-ended discovery still relies on the model to translate the request into supported tool filters, and a returned subset is not proof of exhaustive search.

Observed completion limits remain: some broader and legal questions returned facts only, and generated headings/citation placement can vary. The fallback preserves core financial/premises facts but does not fully answer every requested legal or operating question. Passing a source check does not prove that each prose claim has the most precise source.

All evidence is fictional and seller/simulated reporting is not independent verification. A matching price/patient threshold does not establish financial health, legal clearance, valuation or suitability. Public-session request limits are not a billing ceiling. Preserve and review recorded facts when an AI assessment is incomplete.
