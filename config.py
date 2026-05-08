"""Shared model configuration helpers — read by all agents at startup."""
import os

from subscription_models import is_subscription_model_id


OPENAI_REASONING_SUMMARY = "auto"


def get_configured_model_value(agent_env_var: str | None = None, fallback: str = "gpt-5.2") -> str:
    """Return the raw configured model id for an agent or the global default."""
    if agent_env_var:
        agent_value = os.getenv(agent_env_var, "").strip()
        if agent_value:
            return agent_value
    return os.getenv("DEFAULT_MODEL", "").strip() or fallback


def get_default_model(fallback: str = "gpt-5.2"):
    """Return the configured default model for standard agents."""
    return get_agent_model(None, fallback=fallback)


def get_agent_model(agent_env_var: str | None = None, fallback: str = "gpt-5.2"):
    """Return the configured model object/id for a specific agent."""
    return resolve_model_id(get_configured_model_value(agent_env_var, fallback=fallback))


def is_openai_provider(agent_env_var: str | None = None, fallback: str = "gpt-5.2") -> bool:
    """Return True when the configured provider is OpenAI (not LiteLLM).

    OpenAI model IDs never contain a slash (e.g. 'gpt-5.2', 'o3').
    Any 'provider/model' string (e.g. 'anthropic/claude-sonnet-4-6',
    'litellm/gemini/gemini-3-flash') is treated as a LiteLLM-routed model.
    Subscription models are subprocess-backed and are not OpenAI API providers.
    """
    model = get_configured_model_value(agent_env_var, fallback=fallback)
    return is_openai_model_value(model)


def is_openai_model_value(model: str | None) -> bool:
    """Return True when a raw model id is handled directly by the OpenAI API."""
    return bool(model and "/" not in model and not is_subscription_model_id(model))


def get_agent_model_settings(
    agent_env_var: str | None = None,
    *,
    fallback: str = "gpt-5.2",
    reasoning_effort: str | None = "medium",
    verbosity: str | None = None,
    truncation: str | None = None,
):
    """Return ModelSettings matching the configured model provider for an agent."""
    model = get_configured_model_value(agent_env_var, fallback=fallback)
    return build_model_settings_for_value(
        model,
        reasoning_effort=reasoning_effort,
        verbosity=verbosity,
        truncation=truncation,
    )


def build_model_settings_for_value(
    model: str,
    *,
    reasoning_effort: str | None = "medium",
    verbosity: str | None = None,
    truncation: str | None = None,
):
    """Build Agency Swarm ModelSettings for a raw model id.

    The OpenAI Responses API accepts reasoning and verbosity settings directly.
    LiteLLM-routed models and subprocess-backed subscription models do not.
    """
    from agency_swarm import ModelSettings  # noqa: PLC0415
    from openai.types.shared import Reasoning  # noqa: PLC0415

    openai_model = is_openai_model_value(model)
    return ModelSettings(
        reasoning=(
            Reasoning(effort=reasoning_effort, summary=OPENAI_REASONING_SUMMARY)
            if openai_model and reasoning_effort
            else None
        ),
        verbosity=verbosity if openai_model else None,
        truncation=truncation,
    )


def resolve_model_id(model: str):
    """Return an Agency Swarm-compatible model object/id for a raw model id."""
    from model_failover import maybe_wrap_model  # noqa: PLC0415

    return maybe_wrap_model(model, resolve_model_id_without_failover(model))


def resolve_model_id_without_failover(model: str):
    """Return a model object/id without request-local fallback wrapping."""
    return _resolve(model)


def _resolve(model: str):
    """Route 'provider/model' strings through LitellmModel.

    Handles both explicit 'litellm/<model>' and bare 'provider/model' forms.
    OpenAI model IDs contain no slash, so they pass through unchanged.
    """
    if is_subscription_model_id(model):
        from subscription_models import create_subscription_model  # noqa: PLC0415
        return create_subscription_model(model)
    if "/" not in model:
        return model
    bare = model[len("litellm/"):] if model.startswith("litellm/") else model
    try:
        from agency_swarm import LitellmModel  # noqa: PLC0415
        return LitellmModel(model=bare)
    except ImportError:
        return model
