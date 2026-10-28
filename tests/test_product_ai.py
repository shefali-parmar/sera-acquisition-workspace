"""Product AI failure and conversation paths; no network or paid model calls."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from sera import ai
from sera.catalog import load_practices


def practice_name(pid):
    return next(p.name for p in load_practices() if p.id == pid)


def detail(pid="SERA-001"):
    return ToolMessage(
        content=ai.get_practice_details.invoke({"practice_id": pid}),
        name="get_practice_details",
        tool_call_id=pid,
    )


def scripted_agent(monkeypatch, outputs):
    invocations = []

    def invoke(request, config):
        invocations.append(request)
        output = outputs[min(len(invocations) - 1, len(outputs) - 1)]
        return {"messages": request["messages"] + output}

    monkeypatch.setattr(ai, "model", lambda: None)
    monkeypatch.setattr(ai, "create_agent", lambda **kwargs: SimpleNamespace(invoke=invoke))
    return invocations


def test_names_case_and_ordinal_references_resolve_before_inference():
    history = [
        HumanMessage(content="Compare"),
        AIMessage(content="SERA-001, SERA-025 and SERA-007"),
    ]
    assert ai.investigation_ids("Investigate sera-007", history, None) == ["SERA-007"]
    assert ai.investigation_ids(f"Tell me about {practice_name('SERA-007')}", [], None) == [
        "SERA-007"
    ]
    assert ai.investigation_ids("What about the second one?", history, None) == ["SERA-025"]
    assert ai.investigation_ids("And the last option?", history, None) == ["SERA-007"]
    assert ai.investigation_ids("Show dentists in Texas", history, ["SERA-001"]) == []
    assert ai.investigation_ids("Show me its price", history, ["SERA-001"]) == ["SERA-001"]


def test_ambiguous_and_missing_ordinal_references_need_clarification(monkeypatch):
    monkeypatch.setattr(ai, "model", lambda: pytest.fail("No model needed for ambiguous reference"))
    records = load_practices()
    for record in records:
        if record.id in {"SERA-001", "SERA-025"}:
            record.name = "Willow Sacramento Dermatology " + record.id[-3:]
    monkeypatch.setattr(ai, "load_practices", lambda: records)
    result = ai.investigate("Investigate Willow Sacramento Dermatology", "")
    assert result["status"] == "needs_clarification"
    assert "SERA-001" in result["answer"] and "SERA-025" in result["answer"]
    assert result["calls"] == []
    result = ai.investigate("Compare the second one", "")
    assert result["status"] == "needs_clarification"


def test_new_search_resets_old_conversation(monkeypatch):
    calls = scripted_agent(
        monkeypatch, [[AIMessage(content="No matching records in this fictional catalog.")]]
    )
    history = [HumanMessage(content="Old question"), AIMessage(content="SERA-001")]
    result = ai.investigate("Show dentistry practices in Texas", "", history, ["SERA-001"])
    assert len(calls[0]["messages"]) == 1
    assert (
        "Required practice IDs to retrieve with get_practice_details: []"
        in calls[0]["messages"][0].content
    )
    assert len(result["history"]) == 2


def test_oversized_inputs_reject_instead_of_dropping_last_constraint(monkeypatch):
    monkeypatch.setattr(ai, "model", lambda: pytest.fail("No inference for rejected input"))
    description = "a" * ai.MAX_INPUT_CHARS + " under $1 million"
    with pytest.raises(ValueError, match="too long"):
        ai.extract_filters(description)
    with pytest.raises(ValueError, match="too long"):
        ai.investigate(description, "")
    with pytest.raises(ValueError, match="too long"):
        ai.investigate("Question", description)
    with pytest.raises(ValueError, match="cannot be empty"):
        ai.investigate("  ", "")


def test_empty_or_truncated_answer_gets_one_repair_then_preserves_facts(monkeypatch):
    for answer in [
        AIMessage(content=""),
        *[
            AIMessage(content="SERA-001 [SERA-001-S1]", response_metadata={key: reason})
            for key, reason in [
                ("finish_reason", "length"),
                ("finish_reason", "MAX_TOKENS"),
                ("stop_reason", "max_output_tokens"),
            ]
        ],
    ]:
        calls = scripted_agent(monkeypatch, [[detail(), answer]])
        result = ai.investigate("Investigate SERA-001", "")
        assert len(calls) == 2
        assert result["status"] == "facts_only"
        assert "$650,000" in result["answer"]
        assert "No recommendation or ranking" in result["answer"]
        assert result["sources"]
        assert result["warnings"]


def test_missing_selected_candidate_is_explicit_in_fallback(monkeypatch):
    scripted_agent(monkeypatch, [[detail(), AIMessage(content="SERA-001 [SERA-001-S1]")]])
    result = ai.investigate("Compare", "", required_ids=["SERA-001", "SERA-025"])
    assert result["status"] == "facts_only"
    assert f"SERA-025 — {practice_name('SERA-025')}" in result["answer"]
    assert "$1,150,000" in result["answer"]
    assert "Recorded facts" in result["answer"]
    assert "SERA-001-S1" in result["answer"]


def test_discovery_summary_cannot_support_unretrieved_recommendation(monkeypatch):
    calls = scripted_agent(
        monkeypatch,
        [[AIMessage(content=f"I recommend {practice_name('SERA-007')} as the best fit.")]],
    )
    result = ai.investigate("Find practices", "")
    assert len(calls) == 2
    assert result["status"] == "facts_only"
    assert "best fit" not in result["answer"]
    assert any("Retrieve every" in warning for warning in result["warnings"])


def test_zero_match_claim_requires_current_search_but_clarification_can_skip_it(monkeypatch):
    scripted_agent(
        monkeypatch, [[AIMessage(content="No records match in this fictional catalog.")]]
    )
    result = ai.investigate("Find practices", "")
    assert result["status"] == "facts_only"
    assert any("Run search_practices" in warning for warning in result["warnings"])
    scripted_agent(monkeypatch, [[AIMessage(content="Which specialty and state should I search?")]])
    result = ai.investigate("Find practices", "")
    assert result["status"] == "complete"


def test_each_current_turn_retrieves_again_and_uses_own_source(monkeypatch):
    calls = scripted_agent(
        monkeypatch, [[AIMessage(content="SERA-001 has a recorded price [SERA-001-S1].")]]
    )
    prior = [HumanMessage(content="Old question"), AIMessage(content="SERA-001 [SERA-001-S1]")]
    result = ai.investigate("What changes if budget drops?", "Budget $500000", prior)
    assert len(calls) == 1
    assert result["status"] == "complete"
    assert result["sources"][0]["id"] == "SERA-001-S1"
    assert result["calls"] == [
        {
            "tool": "get_practice_details",
            "arguments": {"practice_id": "SERA-001"},
            "executor": "application",
        }
    ]
    assert ai.answer_issues(
        "SERA-001 [SERA-025-S1]",
        ["SERA-001"],
        {"SERA-001", "SERA-025"},
        [{"id": "SERA-001-S1"}, {"id": "SERA-025-S1"}],
    )


def test_timeout_after_completed_read_preserves_evidence(monkeypatch):
    async def ainvoke(request, config):
        callback = config["callbacks"][0]
        callback.on_tool_start(
            {"name": "get_practice_details"}, '{"practice_id":"SERA-001"}', run_id="read"
        )
        callback.on_tool_end(detail(), run_id="read")
        await asyncio.sleep(1)

    monkeypatch.setattr(ai, "REQUEST_TIMEOUT_SECONDS", 0.02)
    monkeypatch.setattr(ai, "model", lambda: None)
    monkeypatch.setattr(ai, "create_agent", lambda **kwargs: SimpleNamespace(ainvoke=ainvoke))
    result = ai.investigate("Investigate SERA-001", "")
    assert result["status"] == "facts_only"
    assert "$650,000" in result["answer"]
    assert result["sources"][0]["id"] == "SERA-001-S1"
    assert result["calls"][0]["tool"] == "get_practice_details"
    assert result["calls"][0]["arguments"] == {"practice_id": "SERA-001"}


def test_provider_failure_without_evidence_is_clear_and_private(monkeypatch):
    def invoke(request, config):
        raise RuntimeError("secret endpoint and private credentials")

    monkeypatch.setattr(ai, "model", lambda: None)
    monkeypatch.setattr(ai, "create_agent", lambda **kwargs: SimpleNamespace(invoke=invoke))
    with pytest.raises(ValueError, match="Check the selected provider") as error:
        ai.investigate("Find practices", "")
    assert "secret" not in str(error.value)


def test_history_bounds_keep_pairs_and_never_replay_old_tools():
    history = []
    for _ in range(20):
        history += [HumanMessage(content="buyer goals " * 200), AIMessage(content="answer " * 200)]
    trimmed = ai._prior_messages(history)
    assert len(trimmed) <= ai.MAX_HISTORY_MESSAGES
    assert sum(len(message.content) for message in trimmed) <= ai.MAX_HISTORY_CHARS
    assert isinstance(trimmed[0], HumanMessage)
    assert isinstance(trimmed[-1], AIMessage)


def test_invalid_provider_is_unavailable_without_startup_crash(monkeypatch):
    monkeypatch.setenv("SERA_AI_PROVIDER", "unsupported")
    assert not ai.configured()
    with pytest.raises(ValueError, match="must be openai or ollama"):
        ai.model()


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        (
            "Find dermatology in California under $1.5 million. Include succession opportunities.",
            ["Listed for sale", "Open to succession"],
        ),
        ("Find only succession opportunities", ["Open to succession"]),
        ("Find succession opportunities only", ["Open to succession"]),
        ("Find practices, exclude succession opportunities", ["Listed for sale"]),
        ("Find practices, do not include succession opportunities", ["Listed for sale"]),
        ("Include succession opportunities but exclude sale listings", ["Open to succession"]),
        ("Find only listed-for-sale practices", ["Listed for sale"]),
        (
            "Find only listed for sale or succession opportunities",
            ["Listed for sale", "Open to succession"],
        ),
        (
            "Find practices, not only succession opportunities",
            ["Listed for sale", "Open to succession"],
        ),
        (
            "Find dermatology practices with established owners",
            ["Listed for sale", "Open to succession"],
        ),
    ],
)
def test_filter_extraction_preserves_explicit_availability_scope(
    monkeypatch, description, expected
):
    from sera.models import Filters, SearchSuggestion

    raw = SearchSuggestion(filters=Filters(statuses=["Open to succession"]))
    structured = SimpleNamespace(invoke=lambda messages: raw)
    monkeypatch.setattr(
        ai,
        "model",
        lambda: SimpleNamespace(with_structured_output=lambda *args, **kwargs: structured),
    )
    result = ai.extract_filters(description)
    assert result.filters.statuses == expected


def test_conflicting_availability_scope_requires_a_choice(monkeypatch):
    from sera.models import Filters, SearchSuggestion

    raw = SearchSuggestion(filters=Filters(statuses=["Open to succession"]))
    structured = SimpleNamespace(invoke=lambda messages: raw)
    monkeypatch.setattr(
        ai,
        "model",
        lambda: SimpleNamespace(with_structured_output=lambda *args, **kwargs: structured),
    )
    result = ai.extract_filters("Only listed for sale. Include succession opportunities.")
    assert result.filters.statuses == []
    assert "Which availability statuses" in result.clarification


def test_resolved_comparison_prefetches_all_records_before_one_synthesis(monkeypatch):
    reads, model_requests = [], []
    original_read = ai.get_practice_details.invoke

    def read(arguments):
        reads.append(arguments["practice_id"])
        return original_read(arguments)

    def invoke(payload, config):
        model_requests.append(payload)
        assert reads == ["SERA-001", "SERA-025"]
        evidence = payload["messages"][-1].content
        assert "Current-turn retrieved evidence" in evidence
        assert '"id": "SERA-001"' in evidence and '"id": "SERA-025"' in evidence
        return {
            "messages": payload["messages"]
            + [
                AIMessage(
                    content="SERA-001 [SERA-001-S1] and SERA-025 [SERA-025-S1]. Revenue is not profit."
                )
            ]
        }

    def create(**kwargs):
        assert kwargs["tools"] == []
        assert kwargs["system_prompt"] == ai.SYNTHESIS_SYSTEM
        return SimpleNamespace(invoke=invoke)

    monkeypatch.setattr(ai, "get_practice_details", SimpleNamespace(invoke=read))
    monkeypatch.setattr(ai, "model", lambda: None)
    monkeypatch.setattr(ai, "create_agent", create)
    result = ai.investigate(
        f"Compare {practice_name('SERA-001')} and {practice_name('SERA-025')}",
        "Budget $1500000",
    )
    assert result["status"] == "complete"
    assert len(model_requests) == 1
    assert len(result["calls"]) == 2
    assert all(call["executor"] == "application" for call in result["calls"])
    assert [call["arguments"]["practice_id"] for call in result["calls"]] == reads


@pytest.mark.parametrize(
    ("question", "guidance"),
    [
        (
            "Prepare due diligence for SERA-001 and SERA-025",
            "### Process guidance\nRequest financial statements and tax returns; reconcile "
            "the reporting periods and expenses to assess earnings.\n### Next step\n"
            "Ask the seller which records are available.",
        ),
        (
            "Prepare seller questions for SERA-001 and SERA-025",
            "### Seller questions (process guidance)\n**Finances:** Which financial "
            "statements and expense records can you provide?\n**Transition:** What "
            "transition support would you be willing to discuss?",
        ),
    ],
)
def test_ma_guidance_formats_preserve_candidate_evidence_requirements(
    monkeypatch, question, guidance
):
    answer = (
        "### Recorded basis\nRecords retrieved for SERA-001 [SERA-001-S1] "
        "and SERA-025 [SERA-025-S1]. Profit is unknown.\n" + guidance
    )
    requests = scripted_agent(monkeypatch, [[AIMessage(content=answer)]])
    result = ai.investigate(question, "")
    assert result["status"] == "complete"
    assert result["answer"] == answer
    assert len(requests) == 1
    assert [call["arguments"]["practice_id"] for call in result["calls"]] == [
        "SERA-001",
        "SERA-025",
    ]
    # Alternate presentation must not bypass ownership or complete-detail checks.
    issues = ai.answer_issues(
        answer.replace("[SERA-025-S1]", ""),
        ["SERA-001", "SERA-025"],
        {"SERA-001", "SERA-025"},
        result["sources"],
    )
    assert "Cite a recorded source for SERA-025" in issues


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        (
            "Should I lease or buy medical office space?",
            "### Process guidance\nCompare the expected holding period, upfront cash, "
            "flexibility and total occupancy costs. What rent, lease term, purchase price "
            "and fit-out assumptions should we use?",
        ),
        (
            "Find a medical office building for lease in Austin",
            "### Process guidance\nI cannot search live properties or provide an inventory "
            "of available buildings. What size, permitted use, budget and timing should "
            "your broker search brief include?",
        ),
    ],
)
def test_general_property_guidance_needs_no_practice_or_catalog_search(
    monkeypatch, question, answer
):
    creations, requests = [], []

    def invoke(payload, config):
        requests.append(payload)
        return {"messages": payload["messages"] + [AIMessage(content=answer)]}

    def create(**kwargs):
        creations.append(kwargs)
        return SimpleNamespace(invoke=invoke)

    monkeypatch.setattr(ai, "model", lambda: None)
    monkeypatch.setattr(ai, "create_agent", create)
    monkeypatch.setattr(
        ai,
        "get_practice_details",
        SimpleNamespace(invoke=lambda *args: pytest.fail("No fictional property lookup")),
    )
    result = ai.investigate(question, "Keep upfront costs manageable")
    assert result["status"] == "complete"
    assert result["answer"] == answer
    assert result["calls"] == result["sources"] == []
    assert len(requests) == 1
    assert creations[0]["tools"] == []
    assert creations[0]["system_prompt"] == ai.GENERAL_PROPERTY_SYSTEM
    assert "Keep upfront costs manageable" in requests[0]["messages"][0].content


def test_target_property_question_prefetches_own_record_and_retains_evidence_checks(monkeypatch):
    records = [practice.model_copy(update={"premises": None}) for practice in load_practices()]
    monkeypatch.setattr(ai, "load_practices", lambda: records)
    answer = (
        f"### Recorded basis\nSERA-001 — {practice_name('SERA-001')} has a recorded "
        "practice asking price [SERA-001-S1]. This does not establish a property "
        "purchase price; building ownership, rent and lease terms are unknown.\n"
        "### Process guidance\nRequest the executed lease and ask the landlord about "
        "assignment, renewal, permitted use and responsibility for repairs."
    )
    requests = scripted_agent(monkeypatch, [[AIMessage(content=answer)]])
    result = ai.investigate("What real-estate diligence is needed?", "", required_ids=["SERA-001"])
    assert result["status"] == "complete"
    assert len(requests) == 1
    assert result["calls"] == [
        {
            "tool": "get_practice_details",
            "arguments": {"practice_id": "SERA-001"},
            "executor": "application",
        }
    ]
    assert result["sources"]
    assert "Cite a recorded source for SERA-001" in ai.answer_issues(
        answer.replace("[SERA-001-S1]", ""), ["SERA-001"], {"SERA-001"}, result["sources"]
    )


def test_property_guidance_does_not_accept_invented_catalog_evidence(monkeypatch):
    requests = scripted_agent(
        monkeypatch, [[AIMessage(content="The building for SERA-001 is available [SERA-001-S1].")]]
    )
    result = ai.investigate("What should I check before leasing a medical building?", "")
    assert len(requests) == 2
    assert result["status"] == "facts_only"
    assert result["sources"] == []
    assert "building for SERA-001 is available" not in result["answer"]
    assert any("Retrieve every" in warning for warning in result["warnings"])


def test_property_topic_does_not_replace_a_practice_discovery_request():
    assert not ai._general_property_request("Find dermatology practices with leased premises")
    assert ai._general_property_request("What lease questions should I ask a landlord?")
    for prompt in [ai.SYSTEM, ai.SYNTHESIS_SYSTEM, ai.GENERAL_PROPERTY_SYSTEM]:
        assert "practice asking price is not a real-estate price" in prompt
        assert "building ownership" in prompt
        assert "no standalone property inventory" in prompt


def test_focused_property_answer_uses_premises_synthesis_instead_of_an_investment_brief(
    monkeypatch,
):
    targets = load_practices()[:2]
    answer = "\n".join(
        f"{practice.id} — {practice.name}: see the recorded lease terms "
        f"[{practice.premises.source}]. Confirm assignment and landlord consent in writing."
        for practice in targets
    )
    creations, requests = [], []

    def invoke(payload, config):
        requests.append(payload)
        return {"messages": payload["messages"] + [AIMessage(content=answer)]}

    def create(**kwargs):
        creations.append(kwargs)
        return SimpleNamespace(invoke=invoke)

    monkeypatch.setattr(ai, "model", lambda: None)
    monkeypatch.setattr(ai, "create_agent", create)
    result = ai.investigate(
        "What are the annual base rent and CAM, and which lease permissions still need confirming?",
        "",
        required_ids=[practice.id for practice in targets],
    )
    assert result["status"] == "complete"
    assert result["answer"] == answer
    assert len(requests) == 1  # No irrelevant unknown-profit correction for a premises-only answer.
    assert creations[0]["system_prompt"] == ai.PROPERTY_SYNTHESIS_SYSTEM
    assert creations[0]["tools"] == []
    assert "Target review or investment brief" not in creations[0]["system_prompt"]
    assert [call["arguments"]["practice_id"] for call in result["calls"]] == [
        practice.id for practice in targets
    ]
    assert "Discuss every selected practice" in ai.answer_issues(
        "SERA-001 [SERA-001-S5]",
        [practice.id for practice in targets],
        {practice.id for practice in targets},
        result["sources"],
        require_profit_distinction=False,
    )
    # The legacy assessment check remains the default outside the narrow property route.
    assert any(
        "unknown net profit" in issue
        for issue in ai.answer_issues(
            answer,
            [practice.id for practice in targets],
            {practice.id for practice in targets},
            result["sources"],
        )
    )


def test_property_route_still_requires_profit_distinction_when_earnings_are_discussed(monkeypatch):
    requests = scripted_agent(
        monkeypatch,
        [[AIMessage(content="SERA-001 [SERA-001-S5] and SERA-002 [SERA-002-S5] have EBITDA.")]],
    )
    result = ai.investigate(
        "Compare lease costs and EBITDA", "", required_ids=["SERA-001", "SERA-002"]
    )
    assert len(requests) == 2
    assert result["status"] == "facts_only"
    assert any("unknown net profit" in warning for warning in result["warnings"])


def test_acquisition_checklist_with_incidental_property_item_retains_ma_task_routing(monkeypatch):
    from sera.ma_workspace import deal_tasks

    generic_tasks = {task.label: task for task in deal_tasks([])}
    target_tasks = {task.label: task for task in deal_tasks(load_practices()[:2])}
    for tasks in [generic_tasks, target_tasks]:
        assert not ai._general_property_request(tasks["Evaluate a practice"].request)
        assert ai._general_property_request(tasks["Lease or buy?"].request)
        assert ai._general_property_request(tasks["Assess a property"].request)
    creations = []

    def create(**kwargs):
        creations.append(kwargs)
        return SimpleNamespace(
            invoke=lambda payload, config: {
                "messages": payload["messages"]
                + [
                    AIMessage(
                        content="### Process guidance\nRequest financial, operations and lease records."
                    )
                ]
            }
        )

    monkeypatch.setattr(ai, "model", lambda: None)
    monkeypatch.setattr(ai, "create_agent", create)
    result = ai.investigate(generic_tasks["Evaluate a practice"].request, "")
    assert result["status"] == "complete"
    assert creations[0]["system_prompt"] == ai.SYSTEM
    assert {tool.name for tool in creations[0]["tools"]} == {
        "search_practices",
        "get_practice_details",
    }


def test_recorded_ebitda_is_preserved_in_evidence_limits_and_failure_fallback(monkeypatch):
    from sera.models import Financials

    practice = load_practices()[0]
    financials = Financials(
        source=practice.id + "-S4",
        reporting_period="Calendar year 2025",
        accounting_basis="Illustrative accrual basis; seller reported, not audited",
        normalized_ebitda=200000,
        normalization_notes="After market clinical owner compensation; before debt and tax",
        payroll_expense=300000,
        supplies_expense=100000,
        occupancy_expense=100000,
        other_operating_expense=150000,
    )
    practice = practice.model_copy(update={"financials": financials})
    monkeypatch.setattr(ai, "load_practices", lambda: [practice])
    record = json.loads(ai.get_practice_details.invoke({"practice_id": practice.id}))
    assert (
        "Use the supplied financials reporting period"
        in record["interpretation_limits"]["financial"]
    )
    record["premises"] = {
        "occupancy": "Leased",
        "annual_base_rent": 85000,
        "annual_cam": 15000,
        "lease_expires": "2030-12-31",
        "source": practice.id + "-S5",
    }
    answer = ai._facts_fallback({practice.id: record}, [practice.id])
    assert "normalized EBITDA: $200,000" in answer
    assert "Calendar year 2025" in answer and "accrual basis" in answer
    assert "[" + financials.source + "]" in answer
    assert "net profit unknown" in answer
    assert "annual base rent $85,000 plus annual CAM $15,000" in answer
    assert f"[{practice.id}-S5]" in answer


def test_legacy_missing_financials_remain_unknown_and_owned_property_price_stays_separate(
    monkeypatch,
):
    practice = load_practices()[0].model_copy(update={"financials": None, "premises": None})
    monkeypatch.setattr(ai, "load_practices", lambda: [practice])
    record = json.loads(ai.get_practice_details.invoke({"practice_id": practice.id}))
    assert "Profit is unknown" in record["interpretation_limits"]["financial"]
    assert "Building ownership" in record["interpretation_limits"]["premises"]
    record["premises"] = {
        "occupancy": "Owned",
        "property_asking_price": 1200000,
        "source": practice.id + "-S5",
    }
    answer = ai._facts_fallback({practice.id: record}, [practice.id])
    assert "Operating earnings unknown" in answer
    assert "separate property asking price $1,200,000, excluded from the practice price" in answer
    assert "annual base rent" not in answer


def test_normalized_ebitda_must_not_be_treated_as_net_profit_or_take_home_income():
    for suffix in ["net profit", "take-home income", "SDE"]:
        assert any(
            "Normalized EBITDA is not net profit" in issue
            for issue in ai.answer_issues(f"Normalized EBITDA is {suffix}.", [], set(), [])
        )
    assert not ai.answer_issues(
        "Normalized EBITDA is not net profit, take-home income or SDE.", [], set(), []
    )


def test_capture_keeps_structured_inputs_when_tool_input_string_is_absent():
    capture = ai._EvidenceCapture()
    capture.on_tool_start(
        {"name": "get_practice_details"},
        None,
        run_id="read",
        inputs={"practice_id": "SERA-025"},
    )
    assert capture.calls == [
        {"tool": "get_practice_details", "arguments": {"practice_id": "SERA-025"}}
    ]


def test_discovery_still_runs_model_selected_tools(monkeypatch):
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.outputs import ChatGeneration, ChatResult

    class DiscoveryModel(BaseChatModel):
        @property
        def _llm_type(self):
            return "offline-discovery-test"

        def bind_tools(self, tools, **kwargs):
            assert {tool.name for tool in tools} == {"search_practices", "get_practice_details"}
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            count = sum(isinstance(message, ToolMessage) for message in messages)
            if count == 0:
                answer = AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "search_practices",
                            "args": {"filters": {"states": ["CA"]}},
                            "id": "search",
                        }
                    ],
                )
            elif count == 1:
                answer = AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "get_practice_details",
                            "args": {"practice_id": "SERA-001"},
                            "id": "details",
                        }
                    ],
                )
            else:
                answer = AIMessage(
                    content="One fictional candidate is SERA-001 [SERA-001-S1]; further evidence is needed."
                )
            return ChatResult(generations=[ChatGeneration(message=answer)])

    monkeypatch.setattr(ai, "model", lambda: DiscoveryModel())
    result = ai.investigate("Find dermatology practices in California", "")
    assert result["status"] == "complete"
    assert [call["tool"] for call in result["calls"]] == [
        "search_practices",
        "get_practice_details",
    ]
    assert result["calls"][1]["arguments"] == {"practice_id": "SERA-001"}


def test_corrective_revision_reuses_provider_event_loop(monkeypatch):
    loops = []

    async def ainvoke(payload, config):
        loops.append(asyncio.get_running_loop())
        if len(loops) == 1:
            answer = AIMessage(content="SERA-001 has seller-reported revenue.")
        else:
            assert loops[0] is loops[1], (
                "Async provider connection cannot move to another event loop"
            )
            answer = AIMessage(
                content="SERA-001 has seller-reported, unverified revenue; profit unknown [SERA-001-S1]."
            )
        return {"messages": payload["messages"] + [answer]}

    monkeypatch.setattr(ai, "model", lambda: None)
    monkeypatch.setattr(ai, "create_agent", lambda **kwargs: SimpleNamespace(ainvoke=ainvoke))
    result = ai.investigate("Investigate SERA-001", "")
    assert result["status"] == "complete"
    assert len(loops) == 2
    assert loops[0].is_closed()


@pytest.mark.parametrize(
    "claim",
    [
        "SERA-001 has verified revenue",
        "SERA-001 revenue is verified",
        "SERA-001 revenue has been verified",
        "SERA-001 has no verified revenue. However, SERA-001 has verified revenue",
    ],
)
def test_seller_reported_revenue_must_not_be_called_verified(claim):
    issues = ai.answer_issues(
        claim + " [SERA-001-S1]", ["SERA-001"], {"SERA-001"}, [{"id": "SERA-001-S1"}]
    )
    assert any("remove claims of verified revenue" in issue for issue in issues)
    assert not ai.answer_issues(
        "SERA-001 has unverified revenue [SERA-001-S1]",
        ["SERA-001"],
        {"SERA-001"},
        [{"id": "SERA-001-S1"}],
    )


@pytest.mark.parametrize(
    "claim",
    [
        "SERA-001: no verified revenue has been supplied",
        "SERA-001 remains without verified revenue",
        "SERA-001 has a lack of verified revenue",
        "SERA-001 revenue has not been verified",
        "SERA-001 revenue is not independently verified",
    ],
)
def test_explicit_absence_of_verified_revenue_is_not_a_positive_claim(claim):
    assert not ai.answer_issues(
        claim + " [SERA-001-S1]", ["SERA-001"], {"SERA-001"}, [{"id": "SERA-001-S1"}]
    )


@pytest.mark.parametrize(
    "question",
    [
        "Find the annual rent for this practice.",
        "Search for its lease renewal terms.",
        "Find annual rent and other costs.",
        "Search the lease documents for these practices.",
        "Find the dermatology details for this practice.",
        "Show the selected practices and their prices.",
        "Find this orthodontist's lease terms.",
        "List practice details.",
        "Show these practices' annual revenue.",
    ],
)
def test_fact_lookups_retain_selected_and_historical_candidates(question):
    history = [AIMessage(content="SERA-001 [SERA-001-S5]")]
    assert not ai.new_discovery(question)
    assert ai.investigation_ids(question, [], ["SERA-001"]) == ["SERA-001"]
    assert ai.investigation_ids(question, history, None) == ["SERA-001"]


@pytest.mark.parametrize(
    "question",
    [
        "Find a practice in Texas",
        "Search for dermatology practices",
        "Find other practices like this practice",
        "Find practices in Texas and compare their asking prices.",
        "Find practices like this practice.",
        "Find orthodontists in Texas.",
        "Find dental offices in Texas.",
        "Find a $1.5 million dental practice in Texas.",
        "Show listed for sale practices in California.",
        "Find dermatology in Texas and compare their practices.",
        "New search",
    ],
)
def test_explicit_catalog_discovery_clears_old_candidates(question):
    assert ai.new_discovery(question)
    assert ai.investigation_ids(question, [], ["SERA-001"]) == []
    assert ai.investigation_ids(question, [AIMessage(content="SERA-001 [SERA-001-S5]")], None) == []


def test_discovery_with_later_possessive_enables_catalog_tools(monkeypatch):
    creations = []

    def create(**kwargs):
        creations.append(kwargs)
        return SimpleNamespace(
            invoke=lambda request, config: {
                "messages": request["messages"]
                + [AIMessage(content="Which specialties should I search?")]
            }
        )

    monkeypatch.setattr(ai, "model", lambda: None)
    monkeypatch.setattr(ai, "create_agent", create)
    result = ai.investigate(
        "Find practices in Texas and compare their asking prices.",
        "",
        [HumanMessage(content="Old question"), AIMessage(content="SERA-001")],
        ["SERA-001"],
    )
    assert {tool.name for tool in creations[0]["tools"]} == {
        "search_practices",
        "get_practice_details",
    }
    assert result["calls"] == []  # The old selected practice was not prefetched.
    assert len(result["history"]) == 2


def test_rent_lookup_retrieves_selected_practice_evidence(monkeypatch):
    scripted_agent(
        monkeypatch, [[AIMessage(content="The recorded lease has rent information [SERA-001-S5].")]]
    )
    result = ai.investigate(
        "Find the annual rent for this practice.", "", required_ids=["SERA-001"]
    )
    assert result["status"] == "complete"
    assert any(source["id"] == "SERA-001-S5" for source in result["sources"])
    assert any(call["tool"] == "get_practice_details" for call in result["calls"])
