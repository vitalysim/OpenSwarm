import asyncio

import pytest

import model_failover
import subscription_models
from agents import ModelSettings
from agents.items import ModelResponse
from agents.models.interface import Model
from agents.usage import Usage


class FakeModel(Model):
    def __init__(
        self,
        *,
        response: ModelResponse | None = None,
        error: BaseException | None = None,
        stream_events: list[object] | None = None,
        stream_error: BaseException | None = None,
    ):
        self.model = "fake"
        self.response = response or ModelResponse(output=[], usage=Usage(requests=1), response_id=None)
        self.error = error
        self.stream_events = stream_events or []
        self.stream_error = stream_error
        self.calls = 0

    async def get_response(
        self,
        system_instructions,
        input,
        model_settings,
        tools,
        output_schema,
        handoffs,
        tracing,
        *,
        previous_response_id,
        conversation_id,
        prompt,
    ):
        self.calls += 1
        if self.error:
            raise self.error
        return self.response

    def stream_response(
        self,
        system_instructions,
        input,
        model_settings,
        tools,
        output_schema,
        handoffs,
        tracing,
        *,
        previous_response_id,
        conversation_id,
        prompt,
    ):
        async def gen():
            self.calls += 1
            for event in self.stream_events:
                yield event
            if self.stream_error:
                raise self.stream_error

        return gen()


def _settings():
    return ModelSettings()


def _model_response():
    return ModelResponse(output=[], usage=Usage(requests=1, input_tokens=1, output_tokens=1, total_tokens=2), response_id=None)


def test_classifier_detects_claude_usage_limit_payload():
    error = subscription_models.SubscriptionCliError(
        "claude",
        "You're out of extra usage - resets 4am",
        status=429,
        payload={"api_error_status": 429, "result": "You're out of extra usage - resets 4am"},
    )

    signal = model_failover.classify_model_limit_error(error)

    assert signal is not None
    assert signal.reason == "usage_limit"


def test_classifier_does_not_retry_auth_errors():
    error = RuntimeError("401 invalid API key")

    assert model_failover.classify_model_limit_error(error) is None


def test_classifier_does_not_retry_invalid_api_key_code():
    error = RuntimeError("AuthenticationError: invalid_api_key")

    assert model_failover.classify_model_limit_error(error) is None


def test_fallback_candidates_skip_current_and_unavailable(monkeypatch):
    monkeypatch.setenv(
        model_failover.FAILOVER_ORDER_ENV_VAR,
        "subscription/codex,subscription/claude,gpt-5.2",
    )
    monkeypatch.setenv(model_failover.FAILOVER_MAX_ATTEMPTS_ENV_VAR, "2")
    monkeypatch.setattr(model_failover, "_model_available", lambda model_id: model_id != "subscription/claude")

    assert model_failover.fallback_candidates("subscription/codex") == ["gpt-5.2"]


def test_get_response_falls_back_on_limit_error(monkeypatch):
    primary = FakeModel(error=RuntimeError("429 rate limit"))
    fallback = FakeModel(response=_model_response())
    monkeypatch.setenv(model_failover.FAILOVER_ENV_VAR, "auto")
    monkeypatch.setenv(model_failover.FAILOVER_ORDER_ENV_VAR, "subscription/claude")
    monkeypatch.setattr(model_failover, "_model_available", lambda model_id: True)
    monkeypatch.setattr(model_failover, "_resolve_backend_model", lambda model_id: fallback)

    wrapped = model_failover.FailoverModel("subscription/codex", primary)
    response = asyncio.run(
        wrapped.get_response(
            None,
            [],
            _settings(),
            [],
            None,
            [],
            None,
            previous_response_id=None,
            conversation_id=None,
            prompt=None,
        )
    )

    assert response is fallback.response
    assert primary.calls == 1
    assert fallback.calls == 1
    assert wrapped._agency_swarm_usage_model_name == "subscription/claude"
    assert [event["phase"] for event in wrapped.consume_failover_events()] == ["retrying", "succeeded"]


def test_get_response_does_not_fallback_when_disabled(monkeypatch):
    primary = FakeModel(error=RuntimeError("429 rate limit"))
    fallback = FakeModel(response=_model_response())
    monkeypatch.setenv(model_failover.FAILOVER_ENV_VAR, "off")
    monkeypatch.setenv(model_failover.FAILOVER_ORDER_ENV_VAR, "subscription/claude")
    monkeypatch.setattr(model_failover, "_resolve_backend_model", lambda model_id: fallback)

    wrapped = model_failover.FailoverModel("subscription/codex", primary)

    with pytest.raises(RuntimeError, match="429"):
        asyncio.run(
            wrapped.get_response(
                None,
                [],
                _settings(),
                [],
                None,
                [],
                None,
                previous_response_id=None,
                conversation_id=None,
                prompt=None,
            )
        )
    assert fallback.calls == 0


def test_stream_response_emits_failover_events_before_fallback(monkeypatch):
    primary = FakeModel(stream_error=RuntimeError("429 rate limit"))
    fallback = FakeModel(stream_events=[{"type": "response.created"}, {"type": "response.completed"}])
    monkeypatch.setenv(model_failover.FAILOVER_ENV_VAR, "auto")
    monkeypatch.setenv(model_failover.FAILOVER_ORDER_ENV_VAR, "subscription/claude")
    monkeypatch.setattr(model_failover, "_model_available", lambda model_id: True)
    monkeypatch.setattr(model_failover, "_resolve_backend_model", lambda model_id: fallback)

    wrapped = model_failover.FailoverModel("subscription/codex", primary)

    async def collect():
        return [
            event
            async for event in wrapped.stream_response(
                None,
                [],
                _settings(),
                [],
                None,
                [],
                None,
                previous_response_id=None,
                conversation_id=None,
                prompt=None,
            )
        ]

    events = asyncio.run(collect())

    assert events[0]["type"] == "openswarm_model_failover"
    assert events[0]["phase"] == "retrying"
    assert events[1]["type"] == "response.created"
    assert events[2]["type"] == "response.completed"
    assert events[3]["type"] == "openswarm_model_failover"
    assert events[3]["phase"] == "succeeded"


def test_subscription_stream_does_not_emit_created_before_cli_success(monkeypatch):
    model = subscription_models.SubscriptionModel("claude")

    async def fail(*args, **kwargs):
        raise subscription_models.SubscriptionCliError("claude", "429 usage limit", status=429)

    monkeypatch.setattr(model, "get_response", fail)
    stream = model.stream_response(
        None,
        [],
        _settings(),
        [],
        None,
        [],
        None,
        previous_response_id=None,
        conversation_id=None,
        prompt=None,
    )

    async def first():
        return await stream.__anext__()

    with pytest.raises(subscription_models.SubscriptionCliError):
        asyncio.run(first())
