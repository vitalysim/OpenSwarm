"""Request-local model failover for OpenSwarm agents."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
import copy
import json
import os
import re
from typing import Any

from agents import ModelSettings
from agents.items import ModelResponse
from agents.models._openai_shared import get_default_openai_client
from agents.models.interface import Model, ModelTracing
from agents.models.openai_provider import shared_http_client
from agents.models.openai_responses import OpenAIResponsesModel
from openai import AsyncOpenAI


FAILOVER_ENV_VAR = "OPENSWARM_MODEL_FAILOVER"
FAILOVER_ORDER_ENV_VAR = "OPENSWARM_MODEL_FAILOVER_ORDER"
FAILOVER_MAX_ATTEMPTS_ENV_VAR = "OPENSWARM_MODEL_FAILOVER_MAX_ATTEMPTS"

DEFAULT_FAILOVER_ORDER = (
    "subscription/codex",
    "subscription/claude",
    "gpt-5.2",
    "litellm/anthropic/claude-sonnet-4-6",
    "litellm/gemini/gemini-3-flash",
)

_DISABLED_VALUES = {"0", "false", "off", "disabled", "no"}

_AUTH_ERROR_RE = re.compile(
    r"\b(401|403|unauthori[sz]ed|forbidden|invalid[_ -]?api[_ -]?key|incorrect[_ -]?api[_ -]?key|"
    r"api key rejected|missing api key|authentication failed|permission denied)\b",
    re.IGNORECASE,
)
_LIMIT_ERROR_RE = re.compile(
    r"\b(429|too many requests|rate limit|rate_limit|quota|usage limit|extra usage|out of .*usage|credits?|"
    r"capacity|overloaded|overload|temporarily unavailable|resource exhausted|service unavailable)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ModelLimitSignal:
    reason: str
    detail: str


@dataclass(frozen=True)
class FailoverEvent:
    phase: str
    original_model: str
    fallback_model: str
    reason: str
    detail: str
    agent: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "type": "openswarm_model_failover",
            "phase": self.phase,
            "status": self.phase,
            "agent": self.agent,
            "original_model": self.original_model,
            "fallback_model": self.fallback_model,
            "from": self.original_model,
            "to": self.fallback_model,
            "reason": self.reason,
            "detail": self.detail,
            "temporary": True,
        }


class ModelFailoverExhausted(RuntimeError):
    """Raised when every configured fallback model also fails."""


class FailoverModel(Model):
    """Model wrapper that retries rate/quota failures on configured fallbacks."""

    def __init__(self, primary_model_id: str, primary_model: str | Model, *, agent_name: str | None = None):
        self.model = primary_model_id
        self.primary_model_id = primary_model_id
        self.primary_model: str | Model = primary_model
        self.agent_name = agent_name
        self._agency_swarm_usage_model_name = _usage_model_id(primary_model_id)
        self._pending_events: list[dict[str, Any]] = []

    def __repr__(self) -> str:
        return self.primary_model_id

    def __str__(self) -> str:
        return self.primary_model_id

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.primary_model_id == other
        return super().__eq__(other)

    __hash__ = object.__hash__

    async def get_response(
        self,
        system_instructions: str | None,
        input,
        model_settings: ModelSettings,
        tools,
        output_schema,
        handoffs,
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt,
    ) -> ModelResponse:
        async def call(model: Model, settings: ModelSettings) -> ModelResponse:
            return await model.get_response(
                system_instructions,
                input,
                settings,
                tools,
                output_schema,
                handoffs,
                tracing,
                previous_response_id=previous_response_id,
                conversation_id=conversation_id,
                prompt=prompt,
            )

        return await self._call_with_failover(call, model_settings)

    def stream_response(
        self,
        system_instructions: str | None,
        input,
        model_settings: ModelSettings,
        tools,
        output_schema,
        handoffs,
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt,
    ) -> AsyncIterator[Any]:
        async def generator() -> AsyncIterator[Any]:
            async for event in self._stream_with_failover(
                system_instructions,
                input,
                model_settings,
                tools,
                output_schema,
                handoffs,
                tracing,
                previous_response_id=previous_response_id,
                conversation_id=conversation_id,
                prompt=prompt,
            ):
                yield event

        return generator()

    def consume_failover_events(self) -> list[dict[str, Any]]:
        """Return and clear events recorded during non-streaming calls."""
        events = list(self._pending_events)
        self._pending_events.clear()
        return events

    async def _call_with_failover(
        self,
        call: Callable[[Model, ModelSettings], Awaitable[ModelResponse]],
        primary_settings: ModelSettings,
    ) -> ModelResponse:
        self._agency_swarm_usage_model_name = _usage_model_id(self.primary_model_id)
        try:
            return await call(self._primary_backend_model(), primary_settings)
        except Exception as exc:
            signal = classify_model_limit_error(exc)
            if not signal or not failover_enabled():
                raise
            last_exc: BaseException = exc

        for fallback_id in fallback_candidates(self.primary_model_id):
            self._record_event(fallback_id, signal, "retrying")
            try:
                fallback_model = _resolve_backend_model(fallback_id)
                result = await call(fallback_model, _settings_for_model(fallback_id, primary_settings))
            except Exception as fallback_exc:  # noqa: BLE001
                last_exc = fallback_exc
                fallback_signal = classify_model_limit_error(fallback_exc)
                if not fallback_signal:
                    self._record_event(fallback_id, signal, "failed")
                    raise
                self._record_event(fallback_id, fallback_signal, "failed")
                signal = fallback_signal
                continue

            self._agency_swarm_usage_model_name = _usage_model_id(fallback_id)
            self._record_event(fallback_id, signal, "succeeded")
            return result

        raise ModelFailoverExhausted(
            f"All configured OpenSwarm model fallbacks failed after {self.primary_model_id}: {last_exc}"
        ) from last_exc

    async def _stream_with_failover(
        self,
        system_instructions: str | None,
        input,
        model_settings: ModelSettings,
        tools,
        output_schema,
        handoffs,
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt,
    ) -> AsyncIterator[Any]:
        self._agency_swarm_usage_model_name = _usage_model_id(self.primary_model_id)
        emitted_primary_event = False
        try:
            async for event in self._primary_backend_model().stream_response(
                system_instructions,
                input,
                model_settings,
                tools,
                output_schema,
                handoffs,
                tracing,
                previous_response_id=previous_response_id,
                conversation_id=conversation_id,
                prompt=prompt,
            ):
                emitted_primary_event = True
                yield event
            return
        except Exception as exc:
            signal = classify_model_limit_error(exc)
            if emitted_primary_event or not signal or not failover_enabled():
                raise
            last_exc: BaseException = exc

        for fallback_id in fallback_candidates(self.primary_model_id):
            yield self._event_payload(fallback_id, signal, "retrying")
            emitted_fallback_event = False
            try:
                fallback_model = _resolve_backend_model(fallback_id)
                async for event in fallback_model.stream_response(
                    system_instructions,
                    input,
                    _settings_for_model(fallback_id, model_settings),
                    tools,
                    output_schema,
                    handoffs,
                    tracing,
                    previous_response_id=previous_response_id,
                    conversation_id=conversation_id,
                    prompt=prompt,
                ):
                    emitted_fallback_event = True
                    yield event
            except Exception as fallback_exc:  # noqa: BLE001
                last_exc = fallback_exc
                fallback_signal = classify_model_limit_error(fallback_exc)
                if emitted_fallback_event or not fallback_signal:
                    yield self._event_payload(fallback_id, signal, "failed")
                    raise
                yield self._event_payload(fallback_id, fallback_signal, "failed")
                signal = fallback_signal
                continue

            self._agency_swarm_usage_model_name = _usage_model_id(fallback_id)
            yield self._event_payload(fallback_id, signal, "succeeded")
            return

        raise ModelFailoverExhausted(
            f"All configured OpenSwarm model fallbacks failed after {self.primary_model_id}: {last_exc}"
        ) from last_exc

    def _record_event(self, fallback_id: str, signal: ModelLimitSignal, phase: str) -> None:
        self._pending_events.append(self._event_payload(fallback_id, signal, phase))

    def _event_payload(self, fallback_id: str, signal: ModelLimitSignal, phase: str) -> dict[str, Any]:
        return FailoverEvent(
            phase=phase,
            agent=self.agent_name,
            original_model=self.primary_model_id,
            fallback_model=fallback_id,
            reason=signal.reason,
            detail=signal.detail,
        ).to_payload()

    def _primary_backend_model(self) -> Model:
        model = _coerce_model(self.primary_model_id, self.primary_model)
        self.primary_model = model
        return model


def maybe_wrap_model(model_id: str, model: str | Model, *, agent_name: str | None = None) -> str | Model:
    if isinstance(model, FailoverModel) or not failover_enabled():
        return model
    return FailoverModel(model_id, model, agent_name=agent_name)


def apply_model_failover_endpoint_patch() -> None:
    """Preserve failover wrapping when FastAPI request client_config rebuilds models."""
    try:
        from agency_swarm.integrations.fastapi_utils import endpoint_handlers as eh  # noqa: PLC0415
    except Exception:
        return
    if getattr(eh, "_openswarm_model_failover_patched", False):
        return

    original_apply_client_to_agent = eh._apply_client_to_agent
    original_apply_model_override_to_agent = eh._apply_model_override_to_agent

    def patched_apply_client_to_agent(agent, client, config):
        before = getattr(agent, "model", None)
        before_id = getattr(before, "primary_model_id", None) if isinstance(before, FailoverModel) else None
        before_agent = getattr(before, "agent_name", None) if isinstance(before, FailoverModel) else None
        original_apply_client_to_agent(agent, client, config)
        after = getattr(agent, "model", None)
        if before_id and not isinstance(after, FailoverModel):
            agent.model = FailoverModel(before_id, after, agent_name=before_agent or getattr(agent, "name", None))

    def patched_apply_model_override_to_agent(agent, model_name, config):
        applied_client = original_apply_model_override_to_agent(agent, model_name, config)
        if failover_enabled() and not isinstance(getattr(agent, "model", None), FailoverModel):
            agent.model = FailoverModel(str(model_name), agent.model, agent_name=getattr(agent, "name", None))
        return applied_client

    eh._apply_client_to_agent = patched_apply_client_to_agent
    eh._apply_model_override_to_agent = patched_apply_model_override_to_agent
    eh._openswarm_model_failover_patched = True


def failover_enabled() -> bool:
    return os.getenv(FAILOVER_ENV_VAR, "auto").strip().lower() not in _DISABLED_VALUES


def fallback_candidates(current_model_id: str) -> list[str]:
    max_attempts = _max_attempts()
    if max_attempts <= 0:
        return []
    candidates: list[str] = []
    for model_id in _configured_order():
        if _same_model_id(model_id, current_model_id):
            continue
        if any(_same_model_id(model_id, existing) for existing in candidates):
            continue
        if not _model_available(model_id):
            continue
        candidates.append(model_id)
        if len(candidates) >= max_attempts:
            break
    return candidates


def classify_model_limit_error(error: BaseException | str | Any) -> ModelLimitSignal | None:
    text = _error_text(error)
    status = _status_code(error)
    if not text and status is None:
        return None
    if _is_auth_error(text, status):
        return None
    if status == 429 or _LIMIT_ERROR_RE.search(text or ""):
        reason = "rate_or_usage_limit"
        lowered = (text or "").lower()
        if "extra usage" in lowered or re.search(r"\bout of .*usage\b", lowered):
            reason = "usage_limit"
        elif status == 429 or "429" in lowered or "rate" in lowered or "too many requests" in lowered:
            reason = "rate_limit"
        elif "overload" in lowered or "capacity" in lowered or "temporarily unavailable" in lowered:
            reason = "provider_overloaded"
        return ModelLimitSignal(reason=reason, detail=_one_line(text or f"status {status}"))
    return None


def _configured_order() -> list[str]:
    raw = os.getenv(FAILOVER_ORDER_ENV_VAR, ",".join(DEFAULT_FAILOVER_ORDER))
    values = [item.strip() for item in raw.split(",") if item.strip()]
    return values or list(DEFAULT_FAILOVER_ORDER)


def _max_attempts() -> int:
    raw = os.getenv(FAILOVER_MAX_ATTEMPTS_ENV_VAR, "2").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 2


def _model_available(model_id: str) -> bool:
    try:
        from auth_registry import get_auth_statuses  # noqa: PLC0415
        from model_control import _MODEL_AUTH_IDS  # noqa: PLC0415
    except Exception:
        return True

    auth_id = _MODEL_AUTH_IDS.get(model_id)
    if not auth_id:
        return True
    try:
        statuses = {item.id: item for item in get_auth_statuses(live=True)}
    except Exception:
        return True
    status = statuses.get(auth_id)
    return bool(status and status.state in {"available", "configured"})


def _resolve_backend_model(model_id: str) -> Model:
    from config import resolve_model_id_without_failover  # noqa: PLC0415

    return _coerce_model(model_id, resolve_model_id_without_failover(model_id))


def _coerce_model(model_id: str, model: str | Model) -> Model:
    if isinstance(model, Model):
        return model
    if model == model_id and "/" in model_id:
        try:
            from config import resolve_model_id_without_failover  # noqa: PLC0415

            resolved = resolve_model_id_without_failover(model_id)
        except Exception:
            resolved = model
        if isinstance(resolved, Model):
            return resolved
        if resolved != model:
            return _coerce_model(model_id, resolved)
    if "/" not in model_id:
        client = get_default_openai_client() or AsyncOpenAI(http_client=shared_http_client())
        return OpenAIResponsesModel(model=model_id, openai_client=client)
    raise TypeError(f"Cannot coerce non-OpenAI model string into a Model: {model_id}")


def _settings_for_model(model_id: str, base_settings: ModelSettings | None = None) -> ModelSettings:
    from config import build_model_settings_for_value  # noqa: PLC0415

    reasoning = getattr(base_settings, "reasoning", None) if base_settings is not None else None
    reasoning_effort = getattr(reasoning, "effort", None) or os.getenv(
        "OPENSWARM_MODEL_FAILOVER_REASONING_EFFORT",
        "medium",
    )
    settings = build_model_settings_for_value(
        model_id,
        reasoning_effort=reasoning_effort,
        verbosity=getattr(base_settings, "verbosity", None) if base_settings is not None else None,
        truncation=getattr(base_settings, "truncation", None) if base_settings is not None else None,
    )
    if base_settings is None:
        return settings
    for field in (
        "temperature",
        "top_p",
        "frequency_penalty",
        "presence_penalty",
        "tool_choice",
        "parallel_tool_calls",
        "max_tokens",
        "metadata",
        "store",
        "prompt_cache_retention",
        "include_usage",
        "response_include",
        "top_logprobs",
        "extra_query",
        "extra_body",
        "extra_headers",
        "extra_args",
    ):
        if getattr(settings, field, None) is None:
            setattr(settings, field, copy.deepcopy(getattr(base_settings, field, None)))
    return settings


def _usage_model_id(model_id: str) -> str:
    if model_id.startswith("litellm/"):
        return model_id[len("litellm/") :]
    return model_id


def _same_model_id(left: str, right: str) -> bool:
    return _usage_model_id(left).casefold() == _usage_model_id(right).casefold()


def _status_code(error: Any) -> int | None:
    for value in (
        getattr(error, "status_code", None),
        getattr(error, "status", None),
        getattr(getattr(error, "response", None), "status_code", None),
        getattr(error, "api_error_status", None),
    ):
        try:
            if value is not None:
                return int(value)
        except (TypeError, ValueError):
            continue
    payload = getattr(error, "payload", None)
    if isinstance(payload, dict):
        for key in ("status", "status_code", "api_error_status"):
            try:
                if payload.get(key) is not None:
                    return int(payload[key])
            except (TypeError, ValueError):
                continue
    return None


def _is_auth_error(text: str, status: int | None) -> bool:
    if status in {401, 403}:
        return True
    return bool(text and _AUTH_ERROR_RE.search(text))


def _error_text(error: Any) -> str:
    parts: list[str] = []
    current = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        parts.append(str(current))
        payload = getattr(current, "payload", None)
        if payload is not None:
            parts.append(_stringify_payload(payload))
        response = getattr(current, "response", None)
        response_text = getattr(response, "text", None)
        if response_text:
            parts.append(str(response_text)[:1000])
        current = getattr(current, "__cause__", None) or getattr(current, "__context__", None)
    return " ".join(part for part in parts if part)


def _stringify_payload(payload: Any) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, default=str)[:2000]
    except (TypeError, ValueError):
        return str(payload)[:2000]


def _one_line(value: str, limit: int = 320) -> str:
    text = " ".join(str(value).split())
    return text[:limit]
