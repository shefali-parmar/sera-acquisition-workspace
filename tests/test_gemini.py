"""Gemini configuration and adapter compatibility; no external requests or real keys."""

import json

import pytest
from google.genai import types
from google.genai.models import Models
from langchain_google_genai import ChatGoogleGenerativeAI

from sera import ai
from sera.models import SearchSuggestion


@pytest.fixture(autouse=True)
def gemini_environment(monkeypatch):
    monkeypatch.setenv("SERA_AI_PROVIDER", "gemini")
    for name in ("GEMINI_API_KEY", "GEMINI_MODEL", "GOOGLE_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def test_gemini_requires_its_own_explicit_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-unrelated-google-key")
    assert ai.provider_name() == "gemini"
    assert not ai.configured()
    with pytest.raises(ValueError, match="operator API configuration required"):
        ai.model()


@pytest.mark.parametrize("key", ["", "   ", "replace_with_private_key"])
def test_gemini_rejects_missing_or_placeholder_key(monkeypatch, key):
    monkeypatch.setenv("GEMINI_API_KEY", key)
    assert not ai.configured()
    with pytest.raises(ValueError, match="operator API configuration required"):
        ai.model()


def test_gemini_uses_developer_api_and_bounded_client(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    # Ambient credentials must not switch the provider or backend.
    monkeypatch.setenv("GOOGLE_API_KEY", "test-unrelated-google-key")
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "unrelated-project")
    assert ai.configured()
    client = ai.model()
    assert isinstance(client, ChatGoogleGenerativeAI)
    assert client.model == "gemini-3.5-flash-lite"
    assert client.google_api_key.get_secret_value() == "test-gemini-key"
    assert client.vertexai is False
    assert client.timeout == ai.MODEL_TIMEOUT_SECONDS
    assert client.max_retries == 1  # Google SDK: one total attempt, no retries.
    assert client.max_output_tokens == 900


def test_gemini_model_can_be_configured_without_changing_other_providers(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("GEMINI_MODEL", " gemini-3.8-flash ")
    monkeypatch.setenv("OPENAI_MODEL", "openai-model")
    monkeypatch.setenv("OLLAMA_MODEL", "local-model")
    assert ai.model_name() == "gemini-3.8-flash"
    assert ai.model().model == "gemini-3.8-flash"
    monkeypatch.setenv("SERA_AI_PROVIDER", "openai")
    assert ai.model_name() == "openai-model"
    monkeypatch.setenv("SERA_AI_PROVIDER", "ollama")
    assert ai.model_name() == "local-model"


def test_gemini_empty_model_is_unavailable(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("GEMINI_MODEL", " ")
    assert not ai.configured()
    with pytest.raises(ValueError, match="operator API configuration required"):
        ai.model()


def test_gemini_adapter_accepts_existing_extraction_schema_and_tools(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    client = ai.model()
    structured = client.with_structured_output(SearchSuggestion, method="json_schema")
    assert structured is not None
    bound = client.bind_tools([ai.search_practices, ai.get_practice_details])
    assert bound is not None


def test_gemini_extraction_round_trip_uses_native_schema_and_request_limits(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    requests = []

    def respond(_self, **request):
        requests.append(request)
        return types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part(
                                text=json.dumps(
                                    {
                                        "filters": {
                                            "states": ["CA"],
                                            "max_price": 1500000,
                                            "max_price_inclusive": False,
                                        },
                                    }
                                )
                            )
                        ],
                    ),
                    finish_reason="STOP",
                )
            ]
        )

    monkeypatch.setattr(Models, "generate_content", respond)
    suggestion = ai.extract_filters("California practices under $1.5 million")
    assert suggestion.filters.states == ["CA"]
    assert suggestion.filters.max_price == 1500000
    assert not suggestion.filters.max_price_inclusive
    assert len(requests) == 1
    config = requests[0]["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema
    assert config.http_options.timeout == ai.MODEL_TIMEOUT_SECONDS * 1000
    assert config.http_options.retry_options.attempts == 1
    assert config.max_output_tokens == 900


def test_gemini_function_call_round_trip_preserves_tool_arguments(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")

    def respond(_self, **request):
        return types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part(
                                function_call=types.FunctionCall(
                                    name="get_practice_details", args={"practice_id": "SERA-001"}
                                )
                            )
                        ],
                    ),
                    finish_reason="STOP",
                )
            ]
        )

    monkeypatch.setattr(Models, "generate_content", respond)
    response = ai.model().bind_tools([ai.get_practice_details]).invoke("Inspect SERA-001")
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0]["name"] == "get_practice_details"
    assert response.tool_calls[0]["args"] == {"practice_id": "SERA-001"}


def test_gemini_text_blocks_exclude_thoughts_and_preserve_citations():
    message = ai.AIMessage(
        content=[
            {"type": "thinking", "thinking": "internal reasoning"},
            {"type": "text", "text": "Recorded evidence [SERA-001-S1]."},
        ]
    )
    assert ai._answer_text(message) == "Recorded evidence [SERA-001-S1]."
