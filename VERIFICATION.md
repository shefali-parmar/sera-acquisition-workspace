# Verification record

October 27, 2026. This record applies only to this restored full-product working copy. The original archive, latest advisor and v2 are separate applications.

## Relevance and distance — October 27, 2026

- Removed Catalog order. Relevance is the default; eligible ties use Name A–Z then stable ID. Price sorts keep undisclosed prices last. Relevance equally weights active keyword placement, price headroom, surplus above selected minimums and proximity; it never changes eligibility or uses acquisition priorities.
- Added offline Census ZIP/city/state lookup and approximate straight-line miles to each practice's city center. ZIP takes precedence; otherwise a supplied city or single state supplies the area center. All 50 practice cities resolve. Unknown or ambiguous explicit origins prevent application; unknown practice locations cannot meet a radius. See [data provenance and limitations](docs/GEOGRAPHY.md).
- A 1–10,000 mile radius replaces only exact city/state restrictions. Other hard filters remain required. Distance sorting becomes available when an origin resolves, missing distances sort last, and cards disclose rounded approximate miles. Apply/discard/reset preserve the existing review flow. Changing criteria, sort or membership resets pagination.
- The isolated local suite passed **299 tests in 11.35 seconds** before adding one additional fractional-radius boundary regression. Lint, formatting, dependency consistency and offline evaluation passed (5 passed, 6 skipped; no model requests). A separate integration review caught and fixed a model/UI radius-bound mismatch: both now require at least one mile.
- Real local browser: ZIP 95814 with a 100-mile radius returned three Sacramento practices, each displaying approximately two miles. Distance appeared among the five sort choices; Catalog order was absent. Changing to Distance preserved the three candidates. Hosted verification follows after publication.

## Controlled checks

- Python 3.14.8, using the existing SERA virtual environment.
- **183 tests passed** in 10.63 seconds after the assistant ordering refinement (previous baselines: 160 M&A assistant, 149 buyer workspace, 113 presentation). Coverage includes the 50-profile catalog, accounting reconciliation, source ownership, focused property versus broad acquisition routing, optional legacy profiles, financial/property exports, deterministic filters, drafts, navigation, list concurrency and model-response handling.
- Ruff lint passed; all 29 product, script and test Python files passed formatting. Ignored diagnostic scripts in `local_data` are outside the product formatting check.
- Offline evaluation: **5 passed, 6 skipped**. The skipped cases require a live model; they were not counted as successes.
- The shared environment emitted 13 upstream LangSmith deprecation warnings. Tests disabled third-party pytest plugin autoload because that shared environment still contains an old Phoenix plugin. Phoenix is not required by this product.
- Fresh macOS and GitHub-hosted Ubuntu 24.04 Python 3.14 installations from the pinned requirements are now verified in the GitHub preparation checks below. Windows file locking remains unverified.

These checks verify controlled behavior. They are not a model accuracy score, a security audit or a production deployment check.

## Public hosting preparation — October 27, 2026

- Added an explicit Gemini Developer API provider using `langchain-google-genai` 4.4.2. Its default model is `gemini-3.5-flash-lite`; the model and private key remain operator settings. Actual adapter tests mock the network boundary and verify native structured extraction, tool arguments, 45,000 ms timeout, one total attempt and a 900-token output limit. No live Gemini accuracy claim follows from those tests.
- Added public session storage, selected by `SERA_PUBLIC_DEMO=true`. It preserves list validation, atomic membership operations and stale-edit checks without reading or writing shared saved-list files. Local disk persistence is unchanged.
- Added public AI limits at all three model entry paths: filter suggestions, practice/list assessments and Ask SERA. Defaults are 10 requests per visit, a 10-second cooldown and 100 requests per process per UTC day. New conversations do not reset the allowance. Failed requests count. These counters reset with their session/process and are not a provider billing ceiling.
- The isolated Python 3.14 environment passed **230 tests in 10.10 seconds**, dependency consistency, Ruff lint and formatting for all 34 Python files. Offline evaluation: **5 passed, 6 skipped** with no model calls. Fourteen upstream deprecation warnings remain (LangSmith and Google SDK).
- Four integration regressions exercise public-mode UI isolation, rejection before filter extraction, starter drafts without calls, preservation of rejected chat drafts, and assessment rejection before model invocation. Session-storage regressions additionally cover snapshots, memberships, IDs, stale edits and filesystem avoidance.
- A real local public-mode server on port 8506 created “Private visit check” with Riverbend Dermatology through the Save control. Its Shortlists screen retained that candidate. A second browser tab opened a separate visit with no lists. The sidebar disclosed per-visit storage and export-before-reload behavior. Screenshot: `local_data/public-isolated-visit.jpg`.
- Deployed to **https://sera-acquisition-workspace.streamlit.app/** from this standalone repository's `main` branch and `app.py`, using Python 3.14. Streamlit's Sharing settings explicitly reported “This app is public and searchable.” The private hosting key was entered directly into Streamlit settings and is excluded from the repository.
- On the hosted app, Gemini extracted Dermatology, California, a strict $1.5M cap and both sale/succession statuses from the example description. Review preceded application; applying returned Riverbend and Elmbrook. Opened Riverbend's profile, saved both candidates to “California dermatology,” selected both, and viewed the recorded comparison. Downloaded the actual JSON export and reopened it: the file contained SERA-001 / Riverbend and SERA-025 / Elmbrook.
- A live hosted Gemini answer for attached Riverbend gave the correct $43,200 annual base rent and $9,600 CAM, cited its S5 source, and correctly excluded real estate from the practice asking price. The composer cleared and working-note export became available. Its introductory ID label repeated the display name; this remains a cosmetic wording limitation. This single observed answer does not establish general AI accuracy. Screenshot: `local_data/hosted-gemini-answer.jpg`.
- [Linux checks for `bc50fea`](https://github.com/shefali-parmar/sera-acquisition-workspace/actions/runs/40605908321) succeeded, including clean installation, tests, dependency consistency, lint, formatting and offline evaluation. Streamlit's build logs showed that the host replaces PyArrow 25 with 24.0.0 and updates Certifi; the requirements now pin PyArrow 24.0.0 and Certifi 2026.10.23 to align local and hosted installs. Dependency consistency and the complete test suite were rerun after this adjustment.
- The public URL was set to `sera-acquisition-workspace.streamlit.app`, then reopened successfully with configured AI and 49 default catalog matches. A new visit correctly started with empty session data. Current homepage proof: `docs/images/hosted.jpg`. The separate interview deployment was not changed.

## GitHub preparation — October 27, 2026

- Installed `requirements-dev.txt` from PyPI into a new isolated Python 3.14 environment without system site packages or the existing SERA environment. Installation succeeded; `pip check` found no broken requirements.
- In that environment, **183 tests passed in 10.45 seconds**, Ruff lint passed, and all 29 Python files passed formatting. The offline evaluation returned **5 passed, 6 skipped**; it made no model calls. Thirteen upstream LangSmith deprecation warnings remain.
- Added a product-first README, a five-minute manual walkthrough plus optional AI journey, and five current screenshots under `docs/images/`. Fresh Explore and Shortlists captures show the current catalog and named candidates. Documentation keeps fictional-data disclosures and observed AI interpretation limitations explicit.
- Added the MIT license and a GitHub Actions workflow for Python 3.14 on Ubuntu 24.04: isolated installation, dependency consistency, tests, lint, formatting and offline evaluation. Actions are pinned to verified release commits, repository permissions are read-only, and checks need no model or API key. The first [GitHub run](https://github.com/shefali-parmar/sera-acquisition-workspace/actions/runs/40603221842), for commit `180adb5`, completed successfully.
- Initialized a local repository on `main`. Reviewed all 50 staged files: a pattern scan found no embedded credential tokens, private keys, authenticated URLs or personal absolute paths. Ignore checks excluded `.env`, environment variants, Streamlit secrets, saved lists, caches and virtual environments. This is a targeted release scan, not a comprehensive security audit.
- Exported only staged files to a separate directory and launched that export using the fresh environment, with provider settings and API keys removed. The real browser showed 50 fictional practices, 49 default matches, disabled AI actions and functioning browsing. Opened Riverbend's complete profile, created a first named list and saved it atomically, then confirmed Riverbend in Shortlists. The test used only the export's own local storage. Proof is retained locally at `local_data/release-check/first-run-save.jpg`.
- Published this standalone product demo to the new public repository [shefali-parmar/sera-acquisition-workspace](https://github.com/shefali-parmar/sera-acquisition-workspace), on `main`, with its own Git history. Verified the remote repository identity and public visibility independently through GitHub. No public application hosting was created. This preparation does not establish AI accuracy.

## Real browser journey

The app ran at `http://127.0.0.1:8504`, using isolated ignored demo storage and local Ollama.

| Step | Observation |
| --- | --- |
| Describe a practice | “Find dermatology practices in California under $1.5 million. Include succession opportunities.” produced California, Dermatology, a strict $1.5M cap and both sale and succession statuses. |
| Review and apply | Suggestions remained unapplied until chosen. Applying returned the two matching fictional records, SERA-001 and SERA-025. |
| First save | Created “California dermatology” and saved SERA-001 directly from its evidence dialog. |
| Add another practice | Saved SERA-025 through the detail membership selector; both appeared in the list. |
| Compare recorded facts | Inspected the compact comparison and distinct column headings, with expanded evidence available separately. |
| Exports | Downloaded JSON and CSV through the actual controls. Reopened both files: JSON held both record IDs, and CSV contained two corresponding rows. |
| Persisted lists | Opened a fresh browser session. The named list and both memberships remained. Session buyer goals correctly started empty. |
| Continue into Ask SERA | The assessment follow-up opened the assistant with only the answer visible. Internal prompts, tool JSON, developer/interview panels and Phoenix controls were absent. |
| Currency and errors | Confirmed multiple currency amounts remain literal dollars, and failed evidence checks show a buyer-readable notice rather than internal revision instructions. |
| Live follow-up | A $1M budget follow-up read the same two candidates and explained that $650K is within the new cap and $1.15M exceeds it. The generated table called the latter “Marginal” despite the hard cap, demonstrating a remaining interpretation limitation. |

Manual zero-cap handling and some injected error states are covered by controlled AppTests, rather than separately repeated in the browser.

## Presentation update browser checks

After the initial journey above, the refined UI was checked again in the local browser without new model calls:

- The initial screen showed description and manual entry actions, without open filter widgets. Manual review showed criteria without result cards. Applying Dermatology, California and a $1.5M inclusive cap opened exactly the two expected practices with an applied-search summary and no filter editor.
- Both actual catalog names appeared on the cards, saved-list selectors and comparison headers. The comparison retained financial and patient reporting periods, unknown values and evidence limits.
- The detail dialog showed summary metrics and working Overview, Due diligence, Area & patients, and Sources tabs. Seller and independent legal uncertainty, survey limits and source metadata remained accessible. Its save popover showed the existing list membership.
- At a 1440-pixel viewport, the card grid used three columns; at the default 994-pixel app panel, it used two. Neither grid overflowed horizontally. The narrowest one-column breakpoint is implemented but was not separately browser-verified. Temporary viewport settings were reset.
- Screenshots are retained locally in `local_data/acceptance/refined-results.jpg`, `refined-practice-details.jpg` and `refined-comparison.jpg`.

Pagination, criteria revision/discard/reset, navigation persistence, and preserving internal history/source IDs while displaying names were also checked with controlled AppTests.

## Buyer-workspace acceptance

The final buyer-workspace build was checked in the same local browser on October 27. Three agents implemented separate view modules; the lead integrated native routing and verified the combined product.

- Real local extraction of the example description again produced Dermatology, California, a strict $1.5M cap and sale plus succession. Suggestions stayed in review until Apply. Results showed Riverbend Dermatology and Elmbrook Skin Center, with compact criteria chips and separate View practice / Saved actions.
- Both saved memberships were explicitly updated through actual detail/card controls. Shortlists initially showed zero selected; selecting one kept Compare disabled, selecting two enabled the factual comparison. Reporting periods appeared beneath values, with actual practice names in headers.
- List actions exposed rename, membership editing, whole-list exports, creation and Delete. JSON and CSV were downloaded and reopened: both contained SERA-001 / Riverbend Dermatology and SERA-025 / Elmbrook Skin Center. Deletion confirmation, cancellation and stale-edit rejection were exercised through controlled tests rather than deleting the demo list in the browser.
- A full server restart retained “California dermatology” and both memberships. All 36 catalog names changed without changing IDs or any other catalog field; the lead compared every non-name field against the pre-upgrade backup.
- A locally generated Riverbend brief continued directly from its detail dialog into Ask SERA. The assistant named Riverbend and showed its frozen criteria and priorities. New conversation exposed three starters; Review due diligence populated the composer without a request, spinner or assistant response. A keyboard Tab reached Ask assistant with a visible teal focus ring.
- Automated regressions additionally verify that acquisition priorities never change deterministic matches, criteria-chip review does not apply changes, list and sort selection survive native page changes, candidate changes carry through subsequent follow-ups, and failed requests retain the previous conversation snapshot.

- Responsive checks used 1440×900 desktop, 768×1024 tablet and 390×844 mobile. Tablet used two card columns; mobile used one, without document overflow. The corrected mobile profile measured exactly left 0, top 0, width 390 and height 844, with an opaque off-white background and a 2×2 metric grid. Sources remained reachable and Escape dismissed the dialog, returning focus to View practice.
- At 390px the comparison panel measured 356px with 530px scrollable content. Arrow keys moved horizontal scroll while the first row label stayed fixed at the panel edge. Candidate headers and row labels used sticky positioning; the panel had a visible keyboard focus outline and scrolling cue. These are targeted keyboard/layout checks, not a complete assistive-technology or WCAG audit.
- Representative text/background contrast calculations were 6.16:1 for muted body text, 6.20:1 for teal text on pale green, and 5.01:1 for white primary-action text on teal. The final mobile style adjustment also passed all eight focused design tests; lint and formatting passed again.
- Current screenshots are retained in `local_data/acceptance/workspace-desktop-shortlist.jpg`, `workspace-tablet-shortlist.jpg`, `workspace-mobile-details.jpg` and `workspace-mobile-comparison.jpg`. Temporary viewport overrides were reset.

The live brief completed the response protocol. It still called a candidate “Matched” with unspecified preferences and described unknown legal history as “not clean.” These are unmeasured and potentially misleading interpretations. The UX pass does not change or validate the underlying model quality. Earlier live findings below remain applicable.

## Assistant page order — current iteration

- Starter buttons use native Streamlit help pop-ups with distinct definitions for the business, lease-versus-own decision, and physical premises. Browser keyboard focus on Assess a property displayed its definition without populating the composer or making a request. Screenshot: `local_data/acceptance/assistant-definition-tooltip.jpg`. Ruff passed after the definition copy update.
- Replaced the overlapping diligence starters with **Evaluate a practice**, **Lease or buy?**, and **Assess a property**. Their drafts now focus respectively on acquisition performance/operations/transition, occupancy strategy, and intended use/layout/access/fit-out. With practices attached, the first starter remains **Review a target**. The 101 affected workspace, task, AI-routing and application UI tests passed in 8.17 seconds; Ruff passed. No model request was made.
- Replaced the category subtitle with a short description: “Evaluate practices, compare leasing or buying a property, and plan your due diligence. Ask a general question or add practices for a tailored review.”
- Reordered the initial page to introduction, three starting questions, composer, then Add practices and Send. Prepared drafts now read as short buyer questions; policy safeguards remain in the backend. Applying practice selection uses a callback before composer instantiation so untouched generated drafts can clear safely.
- Browser-checked desktop and a measured **390×844 CSS viewport**. The mobile document width was 390; all three starters and both action controls fitted without horizontal overflow. Clicking Lease or buy? prepared the shortened editable question without a model response. No new live model request was made for this layout change. The temporary viewport override was reset.
- Screenshots: `local_data/acceptance/assistant-order-desktop.jpg` and `assistant-order-mobile.jpg`.

## Complete catalog and real estate assistant — preceding iteration

- Removed Deal context completely. Captured preferences, criteria and priorities still reach the assistant and working-note export. The question composer now precedes three compact draft starters. Add practices is optional; lease-versus-buy and property diligence work with no practice selected. Send remains the only model trigger.
- Expanded the catalog from 36 to **50 distinct fictional practices**. Each record has financial, operations, premises, patient/statistical and legal/disclosure information. Forty premises scenarios are leased and ten owned. All source references remain within their own practice. The original names, IDs and known numeric facts are retained; added profiles use new IDs 037–050.
- An independent rendering audit of all 50 `missing_information` outputs returned only **SERA-002: Asking price**. No other core information gaps remain. Null medical operatories/dental exam rooms and lease fields for owned premises are inapplicable; they are not presented as unknown. The single undisclosed price intentionally preserves a realistic demo edge case.
- Typed validation checks all payer mixes total 100%, revenue equals operating expenses plus normalized EBITDA, leased occupancy costs equal base rent plus CAM, and lease/property fields agree with occupancy type. EBITDA remains separate from net income, valuation and take-home pay. New profile objects are optional for legacy records.
- The real browser showed 49 default matches with one undisclosed price excluded, and the sidebar confirmed the 50-record catalog. Alpine Family Medicine displayed eight exam rooms, complete staffing, $1.57M revenue and $314K modeled EBITDA. Its property tab showed an owned scenario priced separately at $1.037M alongside the $1.15M practice price. Riverbend's lease tab showed $43,200 base rent, $9,600 CAM, $52,800 total, expiry, escalation, renewal options and consent requirements. No real-world property or legal review is claimed.
- The general Lease or buy? starter populated a draft without a practice. One live qwen3:8b request completed, discussing costs, flexibility, holding period, capital and required inputs; no unrelated practice was introduced and no made-up market rate or property value was displayed. It answered in prose rather than the requested Process guidance heading, so format compliance remains imperfect. This is one workflow observation, not an accuracy rate.
- The first targeted rent/CAM answer gave the correct $43,200/$9,600 figures with Riverbend's S5 source, but added an unsolicited acquisition opinion and unsupported “strong” earnings judgment. A separate focused property-response prompt was then added, with regression coverage for premises-only versus broad acquisition requests. It keeps property questions out of the investment-brief template while preserving evidence checks and request limits.
- After restarting with that prompt, the same live Riverbend question returned only its $43,200 annual base rent, $9,600 annual CAM and landlord assignment consent to confirm, citing SERA-001-S5. The unsolicited investment opinion and earnings metric were absent. The model said consent was “not yet obtained” where the record only says it is not represented as obtained; that wording remains stronger than the supplied evidence and requires review. The passing response protocol is not a full semantic-quality pass. Screenshot: `local_data/acceptance/property-assistant-focused-lease.jpg`.
- After a full restart, the saved California dermatology list still contained Riverbend and Elmbrook. The actual CSV download included both records and their full financial, operations and premises profiles. Reopened profile JSON confirmed Riverbend's leased costs, Elmbrook's separate owned-property price, within-record sources and 100% payer totals.
- The assistant was checked at a measured **390×844 CSS viewport**, with document width 390 and all three starting questions visible without truncation. The browser's pre-existing zoom was accounted for; the viewport override was reset. Desktop and mobile screenshots are `local_data/acceptance/property-assistant-desktop.jpg` and `property-assistant-mobile.jpg`. Additional proof: `complete-profile-financials.jpg`, `complete-profile-owned-property.jpg`, `complete-profile-lease.jpg`, and `property-assistant-live-guidance.jpg`.
- The offline evaluation was rerun against the expanded catalog: **5 passed, 6 skipped**. The undisclosed-price evaluation case now uses SERA-002. No skipped case is counted as live verification.

## M&A assistant refinement — preceding iteration

The oversized conversation context was replaced with a compact target strip and a collapsed Deal context panel. It retains captured criteria, applied preferences, unverifiable requirements and acquisition priorities. Four task controls prepare editable requests: target review, comparison, diligence planning and seller questions. They do not call the model until Ask assistant is chosen.

- Buyers can select up to three named targets from the catalog or a saved list without changing filters or memberships. Controlled tests verify explicit application, unavailable IDs, per-source selection and target persistence across native navigation.
- Untouched generated drafts clear when targets change; edited drafts remain with a scope-review notice. Drafts survive navigation. Failed requests retain them, while successful requests clear the composer. Existing conversation snapshots remain frozen.
- Working-note exports include visible exchanges, named targets, captured criteria and priorities, including an explicit placeholder for unavailable targets. Internal model messages are excluded.
- The response instructions distinguish acquisition reviews, comparisons, document-request plans and seller agendas. Recorded facts, interpretations, unknowns and general process guidance remain distinct. These instructions do not establish model accuracy or replace professional diligence.
- The real browser confirmed selecting Riverbend Dermatology, preparing a diligence draft without a call, and opening/closing target controls. At a measured 390×844 CSS viewport, the document width remained 390px, target controls fit, and all four task labels wrapped without truncation. The browser's existing 80% zoom was accounted for in the viewport override. Temporary overrides were reset.
- One explicit live local qwen3:8b diligence request completed with Recorded basis, Process guidance and Next step. It identified Riverbend, its $650,000 asking price, seller-reported unverified $850,000 revenue, 850 active patients (2025), and unknown legal information. It proposed financial, legal, lease, licensing and payer-mix requests; it did not claim these checks were completed. The composer cleared and New conversation and Export working notes became available.
- The actual Export working notes control downloaded `~/Downloads/sera-acquisition-notes.md`. Reopening the file confirmed the named target, captured criteria/priorities, buyer request and displayed answer, without internal tool messages.
- Remaining live quality issues: the response attached seller-evidence citations to generic process requests, selected a 2020–2025 financial-record span without explaining that choice, and repeated the practice name in its opening. This single completed response is a workflow observation, not an accuracy score or proof of professional M&A quality. Previous AI limitations below remain applicable.
- Screenshots: `local_data/acceptance/ma-assistant-mobile.jpg` and `ma-assistant-desktop.jpg`.

## Bounded live model observations

Both tested models were already installed locally. No paid fallback or external model API was used. The request limit is 60 seconds, with one possible corrective revision inside that total.

| Model and final direct case | Seconds | Result |
| --- | ---: | --- |
| qwen3:8b, two-practice comparison | 48.57 | Facts only: the revised answer still omitted a candidate's source. |
| qwen3:8b, changed-budget follow-up | 27.07 | Complete protocol response. Manual review confirmed the correct price ordering and new-cap exclusion. “Strong patient base” remained an interpretation rather than a measured conclusion. |
| qwen2.5:7b, same comparison | 60.00 | Facts only: deadline reached during repair. |
| qwen2.5:7b, same follow-up | 57.09 | Facts only: the answer failed the revenue/profit distinction check. |

The qwen3 default is retained. This tiny development set does not demonstrate a quality rate or a stable latency guarantee. Earlier real checks also found invented disqualification language, unsupported “safer”/growth interpretations, incorrect evidence attribution and incomplete citations. Some were corrected by a prompt or a bounded repair; some caused a facts-only fallback. They must not be reported as a clean acceptance pass.

Detailed development attempts, drafts and diagnostic outputs are retained locally in ignored `local_data/acceptance/`. They are not public product telemetry. There is no ongoing observability service.

## Release boundary

The non-AI product journey is working in the verified local browser. AI synthesis remains optional and inconsistent on the tested local models. Recorded facts, lists and exports remain usable when it fails. Evidence checks cover specific errors; correct references do not establish that every claim or recommendation is supported.

Before presenting AI recommendations as dependable, a separate bounded semantic-quality pass should address hard-cap labels, source-to-claim support and unsupported comparative judgments. Public hosting also needs authentication and separate user storage. Conversations and assessments currently remain session-only.

The product repository is published as recorded above; no public application deployment was created and no event application was submitted. No private `.env` was copied into this product directory.
