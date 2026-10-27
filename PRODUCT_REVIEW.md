# SERA full product review

Reviewed October 27, 2026. Scope: the earlier full application with natural language search, editable filters, practice evidence, named lists, comparisons, exports and contextual follow-ups. The preserved archive is the baseline; changes are made in this separate working copy.

The restored baseline passed 22 existing tests. This review identified state, persistence, evidence and first-use problems, then corrected them in the existing application. The changes below are implemented. Controlled regression tests and real browser observations are recorded separately in [VERIFICATION.md](VERIFICATION.md); neither establishes general AI accuracy.

## Findings, fixes and benefits

| Priority | Finding | Correction | Benefit |
| --- | --- | --- | --- |
| P1 | A saved-file validation failure stops the whole application in `app.py:main`. | Preserve the file, disable list mutations and let browsing and chat continue. | One damaged local file does not make the entire product unusable. |
| P1 | Storage mutations are unguarded in detail and saved-list screens. | Handle validation, write and stale-edit failures without losing visible input. | Users can understand failures and retry safely. |
| P1 | Filter widgets disappear between screens, and old suggestions become the defaults again. | Keep applied filters, draft edits and pending suggestions separate across navigation. | Search criteria remain predictable. |
| P1 | Unapplied suggestion preferences enter `effective_goals`. | Use only applied search context for the advisor. | An unapproved suggestion cannot silently change advice. |
| P1 | Old list forms can overwrite memberships added through another view. | Detect stale edits and reload current data before replacing it. | Saving in one screen does not erase newer work. |
| P1 | Atomic replacement prevents partial JSON but does not prevent lost concurrent edits. | Serialize read-modify-write operations and reject stale replacements. | Two tabs cannot silently replace each other's changes. |
| P1 | Practice names and ordinal follow-ups are not reliably bound to candidates; some new searches inherit old candidates. | Resolve explicit names and references, distinguish fresh discovery and retrieve evidence again for follow-ups. | Contextual questions use the intended practices. |
| P1 | AI output checks allow empty, incomplete or unsupported discovery assessments; failed repair discards retrieved evidence. | Validate completion and evidence access, bound requests, retain facts when interpretation fails. | Failures produce useful, honestly labeled outcomes. |
| P1 | Saved-data and source contracts permit ambiguous identities and invalid provenance. | Validate names, IDs, memberships and practice-owned sources. | Lists and citations point to stable, valid records. |
| P2 | Maximum price is always inclusive, including requests saying “under.” | Preserve strict versus inclusive price limits throughout extraction, editing and search. | Search honors the buyer's boundary. |
| P2 | Unlimited comparison selection and repeated names reduce readability. | Limit a comparison to three practices and show distinct name and location labels. | The comparison remains readable and unambiguous. |
| P2 | Snapshot follow-ups silently adopt changed buyer context; draft/reset states are unclear. | Carry assessment context into chat and show context changes explicitly. | Users can understand what each answer is based on. |
| P1 | A real model repair failed because its HTTP connection moved to a closed event loop. | Reuse one event loop for the initial request and its bounded repair. | The recovery path can complete rather than raising a second infrastructure error. |
| P1 | Real extraction interpreted “include succession opportunities” as succession only. | Normalize explicit additive, exclusive and contradictory availability instructions. | Listed opportunities are not silently dropped. |
| P1 | A suggested zero-dollar cap became uncapped in the filter form. | Use a separate cap toggle and retain zero as a numeric value. | Every supported budget retains its meaning. |
| P2 | Saving the first practice required leaving its detail view to create a list. | Create the list and initial membership in one atomic operation from the detail view. | The first save has a direct path. |
| P2 | A dense comparison clipped long records and showed internal identifiers. | Show seven factual rows with full wrapped practice names and location; organize full evidence in detail tabs. | Buyers can identify candidates and inspect supporting detail. |
| P2 | Internal instructions appeared in continued chat, and failed checks exposed correction messages. | Seed visible chat with only the saved answer; show buyer-readable fallback notices. | Ask SERA remains a product experience. |
| P2 | Multiple dollar amounts in a paragraph were parsed as equations. | Escape monetary dollar signs only when rendering answers. | Currency remains readable while original answers and history stay intact. |
| P2 | A narrow revenue guard treated explicit absence of verified revenue as a positive claim. | Recognize explicit local negation while continuing to reject positive claims. | Valid uncertainty statements do not trigger that false rejection. |

## Buyer-workspace upgrade

The approved upgrade is implemented in this working copy. Native Explore / Shortlists / Ask SERA navigation gives each screen one heading. Acquisition priorities explicitly guide assessments without changing deterministic matches. Criteria chips open review; catalog scope, unknown-price exclusions and sorting stay visible. Sorting and selected lists survive navigation through persistent state separate from temporary widget keys.

Cards separate View practice from Save / Saved. Saved opens multi-list membership controls. Meaningful metadata is approximately 14px with stronger contrast. Evidence gaps, including explicitly unknown legal information, appear near the top of profiles. Profiles have responsive metrics, constrained desktop reading width and mobile full-screen details. Comparisons use sticky candidate headings and row labels, distinct values and reporting notes, plus a narrow-screen scrolling cue.

All 36 fictional practice names were curated for distinct identities. An independent field comparison confirmed IDs, numerical facts, source ownership and every non-name field unchanged. Shortlists start comparison selection empty, preserve it per list and allow two or three candidates. List management and full-list exports are grouped under List actions; deletion confirmation appears only after Delete is chosen. Card and detail membership widgets use distinct keys.

Ask SERA shows readable candidate, criteria and priority context. Three contextual starters populate the composer without calling the model. Successful candidate changes update the active conversational scope; failed requests preserve the previous snapshot. Native routing also opens follow-ups directly from a detail dialog. These refinements preserve the existing AI limits and evidence checks; they do not establish semantic accuracy.

## Product decisions

The subsequent presentation review addressed four buyer-facing problems: internal IDs in practice labels, text-heavy profiles, oversized result cards, and competing search controls. Display labels and comparison headers now use catalog practice names; source reference IDs remain available for evidence tracing. Profiles use summary metrics and four evidence tabs. Results use compact cards, six per page, in a responsive one-, two-, or three-column grid. Search has distinct Describe, Review criteria, and Explore matches stages, with advanced criteria collapsed and only a short applied-search summary above results. These changes preserve the existing search, saved-list and evidence contracts.

Preserve the original teal, off-white and pale-green design, deterministic Python filters, fictional evidence, named lists and exports. Refine the existing application incrementally.

Phoenix integration, tracing dependencies, verification scripts, tracing artifacts and setup instructions have been removed from this working product. Interview/developer views, raw tool arguments and internal model messages are absent from the buyer screens. The preserved original repository and its shared Python environment were not modified.

Use one local-user storage boundary for this demo. A public multi-user deployment requires authentication, per-user storage and concurrency appropriate to that environment. A local demo is not that deployment.

MCP is deferred for this slice. The application already has direct read-only Python tools; another transport would not fix its current state, evidence or persistence failures. A reusable external-assistant interface can be evaluated after the complete journey works.

## Practice and real estate assistant — current iteration

The latest feedback supersedes the context-heavy M&A layout below. Deal context is removed. A short introduction describes the tool, followed by three compact starting questions, the question composer, and an action row with optional Add practices on the left and Send on the right. Starter drafts use brief buyer-facing questions; evidence instructions remain in the assistant policy. General lease-versus-buy and property-diligence guidance does not require a practice or trigger a search of unrelated practice records. Selected practices still require their own current evidence. The assistant covers acquisition reviews, comparisons, seller questions, lease terms, occupancy costs, property diligence and landlord/broker questions. It has no standalone property inventory or live listing search.

All 50 fictional profiles now have financial, operational, patient, legal and premises schedules, each linked to its own invented source. The existing 36 IDs/names and known numeric facts were preserved, and 14 distinct profiles were added. Forty leased scenarios supply rent, CAM, renewals, escalation and assignment terms; ten owned-property scenarios supply a separate property price. Practice prices exclude real estate. One intentionally undisclosed practice price remains; inapplicable lease and clinical-room fields are displayed as such. Legal and property reviews are explicitly simulated, not real-world checks.

Financials and Property & lease tabs surface the added records, while comparisons and exports include earnings and premises information. Operating expenses plus normalized EBITDA reconcile to revenue; leased occupancy equals base rent plus CAM, and payer percentages total 100. Normalized EBITDA remains distinct from net income, take-home income or value. New typed profiles remain optional for older imported records; real missing evidence is still handled safely.

## Ask SERA M&A refinement — preceding iteration

User feedback identified that the large context box and repeated explanatory text dominated the assistant. Ask SERA now opens as a practice M&A workspace: a compact target summary, a Select targets popover, collapsed Deal context, four acquisition tasks and a question composer. Targets can come from the catalog or a named shortlist, with explicit application and a maximum of three. Task buttons prepare editable requests without model calls. Review needs a target; comparison needs two or three. Diligence and seller-question tasks also support general process planning.

The assistant now receives task-appropriate format guidance for acquisition reviews, comparisons, document/verification plans and seller agendas. Process guidance is separated from recorded practice evidence. These are buyer preparation tools, not completed checks, seller outreach, valuations or financial transactions. The existing record retrieval, evidence checks and request bounds remain in place.

Draft requests survive navigation. Changing targets clears an untouched generated request; edited text is retained with a warning to check practice names. Once a conversation starts, the picker directs the buyer to New conversation to select a new scope. Existing explicit-reference follow-ups still resolve current targets. Working notes export only visible exchanges, captured criteria/preferences/priorities and named targets, including unavailable-target placeholders; internal model messages remain excluded.

## Remaining boundaries

The product is a local, single-user demo using invented records. A production service still needs user accounts, isolated user data, operational deployment controls and authorized current listing sources. Session conversations and generated assessments are not durable account history.

The local model is probabilistic. Live checks exposed unsupported interpretation and missing citations despite passing controlled tests. The application preserves evidence and withholds recommendations after detected failures. Its guards catch specific patterns, not every semantic mistake; human evidence review remains necessary. Mixed known and entirely unknown practice names can also require a clarification rather than reliable automatic resolution.

No GitHub upload or event application has been submitted. The separate v2 interview release is outside this work.
