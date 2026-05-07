"""OpenSwarm runtime model catalog and per-agent model controls."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

from dotenv import set_key

from auth_registry import AuthStatus, get_auth_statuses
from config import build_model_settings_for_value, get_configured_model_value, resolve_model_id


ENV_PATH = Path(__file__).parent / ".env"


@dataclass(frozen=True)
class AgentModelDefinition:
    name: str
    env_key: str
    reasoning_effort: str | None = "medium"
    verbosity: str | None = None
    truncation: str | None = None


AGENT_MODEL_DEFINITIONS: tuple[AgentModelDefinition, ...] = (
    AgentModelDefinition("Orchestrator", "ORCHESTRATOR_MODEL", reasoning_effort="medium"),
    AgentModelDefinition("General Agent", "GENERAL_AGENT_MODEL", reasoning_effort="medium"),
    AgentModelDefinition("Deep Research Agent", "DEEP_RESEARCH_MODEL", reasoning_effort="high"),
    AgentModelDefinition("Data Analyst", "DATA_ANALYST_MODEL", reasoning_effort="medium", truncation="auto"),
    AgentModelDefinition("Docs Agent", "DOCS_AGENT_MODEL", reasoning_effort="medium"),
    AgentModelDefinition("Slides Agent", "SLIDES_AGENT_MODEL", reasoning_effort="high", verbosity="medium"),
    AgentModelDefinition("Image Agent", "IMAGE_AGENT_MODEL", reasoning_effort="medium", truncation="auto"),
    AgentModelDefinition("Video Agent", "VIDEO_AGENT_MODEL", reasoning_effort="medium", truncation="auto"),
)

OPEN_SWARM_AGENT_MODEL_DEFINITIONS = AGENT_MODEL_DEFINITIONS

SECURITY_RESEARCH_AGENT_MODEL_DEFINITIONS: tuple[AgentModelDefinition, ...] = (
    AgentModelDefinition("Security Research Orchestrator", "SECURITY_RESEARCH_ORCHESTRATOR_MODEL", reasoning_effort="high", truncation="auto"),
    AgentModelDefinition("Security Research Lead", "SECURITY_RESEARCH_LEAD_MODEL", reasoning_effort="high", truncation="auto"),
    AgentModelDefinition("Threat Intelligence Analyst", "THREAT_INTELLIGENCE_ANALYST_MODEL", reasoning_effort="high", truncation="auto"),
    AgentModelDefinition("Vulnerability Researcher", "VULNERABILITY_RESEARCHER_MODEL", reasoning_effort="high", truncation="auto"),
    AgentModelDefinition("OSINT Enrichment Specialist", "OSINT_ENRICHMENT_SPECIALIST_MODEL", reasoning_effort="medium", truncation="auto"),
    AgentModelDefinition("Security Lab Analyst", "SECURITY_LAB_ANALYST_MODEL", reasoning_effort="high", truncation="auto"),
    AgentModelDefinition("Technical Blog Writer", "TECHNICAL_BLOG_WRITER_MODEL", reasoning_effort="medium", truncation="auto"),
    AgentModelDefinition("Security Visual Designer", "SECURITY_VISUAL_DESIGNER_MODEL", reasoning_effort="medium", truncation="auto"),
)

SWARM_AGENT_MODEL_DEFINITIONS: dict[str, tuple[AgentModelDefinition, ...]] = {
    "open-swarm": OPEN_SWARM_AGENT_MODEL_DEFINITIONS,
    "security-research": SECURITY_RESEARCH_AGENT_MODEL_DEFINITIONS,
}

AGENT_MODEL_ENV_VARS = [
    (item.name, item.env_key)
    for definitions in SWARM_AGENT_MODEL_DEFINITIONS.values()
    for item in definitions
]

SUBSCRIPTION_FIRST_MODELS = {
    "DEFAULT_MODEL": "subscription/codex",
    "ORCHESTRATOR_MODEL": "subscription/codex",
    "GENERAL_AGENT_MODEL": "subscription/codex",
    "DATA_ANALYST_MODEL": "subscription/codex",
    "DEEP_RESEARCH_MODEL": "subscription/claude",
    "DOCS_AGENT_MODEL": "subscription/claude",
    "SLIDES_AGENT_MODEL": "subscription/claude",
    "IMAGE_AGENT_MODEL": "subscription/claude",
    "VIDEO_AGENT_MODEL": "subscription/claude",
    "SECURITY_RESEARCH_ORCHESTRATOR_MODEL": "subscription/codex",
    "SECURITY_RESEARCH_LEAD_MODEL": "subscription/codex",
    "THREAT_INTELLIGENCE_ANALYST_MODEL": "subscription/claude",
    "VULNERABILITY_RESEARCHER_MODEL": "subscription/codex",
    "OSINT_ENRICHMENT_SPECIALIST_MODEL": "subscription/claude",
    "SECURITY_LAB_ANALYST_MODEL": "subscription/codex",
    "TECHNICAL_BLOG_WRITER_MODEL": "subscription/claude",
    "SECURITY_VISUAL_DESIGNER_MODEL": "subscription/claude",
}

MODEL_OPTIONS = [
    ("Codex subscription", "subscription/codex"),
    ("Claude Code subscription", "subscription/claude"),
    ("OpenAI API", "gpt-5.2"),
    ("Anthropic API", "litellm/anthropic/claude-sonnet-4-6"),
    ("Google Gemini API", "litellm/gemini/gemini-3-flash"),
]

_MODEL_AUTH_IDS = {
    "subscription/codex": "codex",
    "subscription/claude": "claude",
    "gpt-5.2": "openai_api",
    "litellm/anthropic/claude-sonnet-4-6": "anthropic_api",
    "litellm/gemini/gemini-3-flash": "google_api",
}

_MODEL_PROVIDERS = {
    "subscription/codex": ("codex", "subscription"),
    "subscription/claude": ("claude", "subscription"),
    "gpt-5.2": ("openai", "api"),
    "litellm/anthropic/claude-sonnet-4-6": ("anthropic", "api"),
    "litellm/gemini/gemini-3-flash": ("google", "api"),
}


def build_model_state(
    agency: Any,
    *,
    live: bool = True,
    swarm_id: str | None = None,
    agency_id: str | None = None,
    definitions: tuple[AgentModelDefinition, ...] | None = None,
) -> dict[str, Any]:
    """Return current model routing and availability for an Agency instance."""
    auth_statuses = {status.id: status for status in get_auth_statuses(live=live)}
    agents_by_name = _agency_agents_by_name(agency)
    entry_points = _agency_entry_point_names(agency)
    resolved_swarm_id = _resolve_swarm_id(agency, swarm_id=swarm_id, agency_id=agency_id)
    resolved_definitions = definitions or _agent_definitions_for_swarm(resolved_swarm_id)

    return {
        "agency": getattr(agency, "name", None) or "agency",
        "agencyId": agency_id or resolved_swarm_id or getattr(agency, "name", None) or "agency",
        "swarmId": resolved_swarm_id,
        "defaultModel": get_configured_model_value(None),
        "catalog": [_catalog_item(title, model, auth_statuses) for title, model in MODEL_OPTIONS],
        "allowCustom": True,
        "agents": [
            _agent_state(item, agents_by_name, entry_points, auth_statuses)
            for item in resolved_definitions
        ],
    }


def set_agent_model(
    agency: Any,
    agent_name: str,
    model_id: str,
    *,
    persist: bool = True,
    swarm_id: str | None = None,
    agency_id: str | None = None,
    definitions: tuple[AgentModelDefinition, ...] | None = None,
) -> dict[str, Any]:
    """Update one live agent and persist the chosen model id to .env."""
    clean_agent_name = agent_name.strip()
    clean_model_id = model_id.strip()
    if not clean_agent_name:
        raise ValueError("Agent name is required")
    if not clean_model_id:
        raise ValueError("Model id is required")

    resolved_swarm_id = _resolve_swarm_id(agency, swarm_id=swarm_id, agency_id=agency_id)
    resolved_definitions = definitions or _agent_definitions_for_swarm(resolved_swarm_id)
    definition = _agent_definition(clean_agent_name, definitions=resolved_definitions)
    if not definition:
        raise ValueError(f"Unknown agent for swarm {resolved_swarm_id or 'agency'}: {clean_agent_name}")

    agents_by_name = _agency_agents_by_name(agency)
    agent = agents_by_name.get(definition.name)
    if agent is None:
        raise ValueError(f"Agent is not loaded in this agency: {definition.name}")

    resolved_model = resolve_model_id(clean_model_id)
    agent.model = resolved_model
    agent.model_settings = build_model_settings_for_value(
        clean_model_id,
        reasoning_effort=definition.reasoning_effort,
        verbosity=definition.verbosity,
        truncation=definition.truncation,
    )

    os.environ[definition.env_key] = clean_model_id
    if persist:
        _set_env_value(definition.env_key, clean_model_id)

    return build_model_state(
        agency,
        live=True,
        swarm_id=resolved_swarm_id,
        agency_id=agency_id,
        definitions=resolved_definitions,
    )


def get_agent_model_definitions(
    *,
    swarm_id: str | None = None,
    agency_id: str | None = None,
    agency: Any | None = None,
) -> tuple[AgentModelDefinition, ...]:
    resolved_swarm_id = _resolve_swarm_id(agency, swarm_id=swarm_id, agency_id=agency_id)
    return _agent_definitions_for_swarm(resolved_swarm_id)


def _agent_state(
    definition: AgentModelDefinition,
    agents_by_name: dict[str, Any],
    entry_points: set[str],
    auth_statuses: dict[str, AuthStatus],
) -> dict[str, Any]:
    model_id, resolved_from = _configured_agent_model(definition.env_key)
    catalog_status = _catalog_availability(model_id, auth_statuses)
    return {
        "name": definition.name,
        "id": definition.name,
        "envKey": definition.env_key,
        "model": model_id,
        "modelLabel": _model_label(model_id),
        "resolvedFrom": resolved_from,
        "isEntryPoint": definition.name in entry_points,
        "loaded": definition.name in agents_by_name,
        "available": catalog_status["available"],
        "status": catalog_status["state"],
        "statusDetail": catalog_status["detail"],
    }


def _catalog_item(title: str, model_id: str, auth_statuses: dict[str, AuthStatus]) -> dict[str, Any]:
    provider, source = _MODEL_PROVIDERS.get(model_id, ("custom", "custom"))
    status = _catalog_availability(model_id, auth_statuses)
    return {
        "id": model_id,
        "label": title,
        "provider": provider,
        "source": source,
        "available": status["available"],
        "status": status["state"],
        "statusDetail": status["detail"],
    }


def _catalog_availability(model_id: str, auth_statuses: dict[str, AuthStatus]) -> dict[str, Any]:
    auth_id = _MODEL_AUTH_IDS.get(model_id)
    if not auth_id:
        return {
            "available": True,
            "state": "custom",
            "detail": "Custom model id; availability is checked when the agent runs.",
        }
    status = auth_statuses.get(auth_id)
    if not status:
        return {"available": False, "state": "missing", "detail": "No auth status is registered."}
    return {
        "available": status.state in {"available", "configured"},
        "state": status.state,
        "detail": status.detail,
    }


def _configured_agent_model(env_key: str) -> tuple[str, str]:
    agent_value = os.getenv(env_key, "").strip()
    if agent_value:
        return agent_value, "agent"
    return get_configured_model_value(None), "default"


def _model_label(model_id: str) -> str:
    for title, option_model in MODEL_OPTIONS:
        if option_model == model_id:
            return title
    return model_id


def _agent_definition(
    agent_name: str,
    *,
    definitions: tuple[AgentModelDefinition, ...],
) -> AgentModelDefinition | None:
    folded = agent_name.casefold()
    for item in definitions:
        if item.name.casefold() == folded or item.env_key.casefold() == folded:
            return item
    return None


def _agent_definitions_for_swarm(swarm_id: str | None) -> tuple[AgentModelDefinition, ...]:
    if swarm_id:
        definitions = SWARM_AGENT_MODEL_DEFINITIONS.get(_normalize_swarm_id(swarm_id))
        if definitions:
            return definitions
    return AGENT_MODEL_DEFINITIONS


def _resolve_swarm_id(
    agency: Any | None = None,
    *,
    swarm_id: str | None = None,
    agency_id: str | None = None,
) -> str | None:
    for candidate in (
        swarm_id,
        agency_id,
        getattr(agency, "openswarm_swarm_id", None) if agency is not None else None,
        getattr(agency, "name", None) if agency is not None else None,
    ):
        if not candidate:
            continue
        normalized = _normalize_swarm_id(str(candidate))
        if normalized in SWARM_AGENT_MODEL_DEFINITIONS:
            return normalized
    return None


def _normalize_swarm_id(value: str) -> str:
    return value.strip().replace("_", "-").replace(" ", "-").casefold()


def _agency_agents_by_name(agency: Any) -> dict[str, Any]:
    agents = getattr(agency, "agents", None)
    if isinstance(agents, dict):
        return {str(name): agent for name, agent in agents.items()}
    result: dict[str, Any] = {}
    for agent in agents or []:
        name = getattr(agent, "name", None)
        if name:
            result[str(name)] = agent
    return result


def _agency_entry_point_names(agency: Any) -> set[str]:
    result: set[str] = set()
    for item in getattr(agency, "entry_points", None) or []:
        if isinstance(item, str):
            result.add(item)
            continue
        name = getattr(item, "name", None)
        if name:
            result.add(str(name))
    return result


def _set_env_value(key: str, value: str) -> None:
    if not ENV_PATH.exists():
        ENV_PATH.write_text("", encoding="utf-8")
    set_key(str(ENV_PATH), key, value)
