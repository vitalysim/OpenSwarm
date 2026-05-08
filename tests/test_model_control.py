from __future__ import annotations

from types import SimpleNamespace

import model_control
from auth_registry import AuthStatus


def _status(auth_id: str, state: str = "available") -> AuthStatus:
    return AuthStatus(
        id=auth_id,
        name=auth_id,
        category="subscription" if auth_id in {"codex", "claude"} else "model_api",
        state=state,
        detail=state,
        capabilities=("text",),
    )


def _agency():
    agents = {
        "Orchestrator": SimpleNamespace(name="Orchestrator", model=None, model_settings=None),
        "Slides Agent": SimpleNamespace(name="Slides Agent", model=None, model_settings=None),
    }
    return SimpleNamespace(name="OpenSwarm", agents=agents, entry_points=[agents["Orchestrator"]])


def _security_agency():
    agents = {
        "Security Research Orchestrator": SimpleNamespace(name="Security Research Orchestrator", model=None, model_settings=None),
        "Vulnerability Researcher": SimpleNamespace(name="Vulnerability Researcher", model=None, model_settings=None),
        "Slides Agent": SimpleNamespace(name="Slides Agent", model=None, model_settings=None),
    }
    return SimpleNamespace(
        name="Security Research",
        openswarm_swarm_id="security-research",
        agents=agents,
        entry_points=[agents["Security Research Orchestrator"]],
    )


def test_build_model_state_resolves_default_model(monkeypatch):
    monkeypatch.setenv("DEFAULT_MODEL", "subscription/codex")
    monkeypatch.delenv("ORCHESTRATOR_MODEL", raising=False)
    monkeypatch.setattr(
        model_control,
        "get_auth_statuses",
        lambda live=True: [_status("codex"), _status("claude"), _status("openai_api")],
    )

    state = model_control.build_model_state(_agency(), live=True)

    orchestrator = next(item for item in state["agents"] if item["name"] == "Orchestrator")
    assert orchestrator["model"] == "subscription/codex"
    assert orchestrator["resolvedFrom"] == "default"
    assert orchestrator["isEntryPoint"] is True
    assert orchestrator["available"] is True


def test_set_agent_model_updates_live_agent_and_env(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    monkeypatch.setattr(model_control, "ENV_PATH", env_path)
    monkeypatch.setenv("DEFAULT_MODEL", "subscription/codex")
    monkeypatch.delenv("SLIDES_AGENT_MODEL", raising=False)
    monkeypatch.setattr(
        model_control,
        "get_auth_statuses",
        lambda live=True: [_status("codex"), _status("claude"), _status("openai_api")],
    )
    agency = _agency()

    state = model_control.set_agent_model(agency, "Slides Agent", "gpt-5.2")

    assert agency.agents["Slides Agent"].model == "gpt-5.2"
    assert agency.agents["Slides Agent"].model_settings.reasoning is not None
    assert "SLIDES_AGENT_MODEL='gpt-5.2'" in env_path.read_text(encoding="utf-8")
    slides = next(item for item in state["agents"] if item["name"] == "Slides Agent")
    assert slides["model"] == "gpt-5.2"
    assert slides["resolvedFrom"] == "agent"


def test_security_model_state_uses_distinct_agent_definitions(monkeypatch):
    monkeypatch.setenv("DEFAULT_MODEL", "subscription/codex")
    monkeypatch.delenv("VULNERABILITY_RESEARCHER_MODEL", raising=False)
    monkeypatch.setattr(
        model_control,
        "get_auth_statuses",
        lambda live=True: [_status("codex"), _status("claude"), _status("openai_api")],
    )

    state = model_control.build_model_state(_security_agency(), live=True)

    names = {item["name"] for item in state["agents"]}
    assert "Security Research Orchestrator" in names
    assert "Vulnerability Researcher" in names
    assert "Slides Agent" in names
    vulnerability = next(item for item in state["agents"] if item["name"] == "Vulnerability Researcher")
    assert vulnerability["envKey"] == "VULNERABILITY_RESEARCHER_MODEL"
    slides = next(item for item in state["agents"] if item["name"] == "Slides Agent")
    assert slides["envKey"] == "SECURITY_RESEARCH_SLIDES_AGENT_MODEL"


def test_set_security_agent_model_updates_security_env(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    monkeypatch.setattr(model_control, "ENV_PATH", env_path)
    monkeypatch.setenv("DEFAULT_MODEL", "subscription/codex")
    monkeypatch.setattr(
        model_control,
        "get_auth_statuses",
        lambda live=True: [_status("codex"), _status("claude"), _status("openai_api")],
    )
    agency = _security_agency()

    state = model_control.set_agent_model(
        agency,
        "Vulnerability Researcher",
        "gpt-5.2",
        agency_id="security-research",
    )

    assert agency.agents["Vulnerability Researcher"].model == "gpt-5.2"
    assert "VULNERABILITY_RESEARCHER_MODEL='gpt-5.2'" in env_path.read_text(encoding="utf-8")
    assert "Slides Agent" in {item["name"] for item in state["agents"]}
    assert "Docs Agent" not in {item["name"] for item in state["agents"]}


def test_set_security_slides_agent_model_uses_security_env(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    monkeypatch.setattr(model_control, "ENV_PATH", env_path)
    monkeypatch.setenv("DEFAULT_MODEL", "subscription/codex")
    monkeypatch.delenv("SLIDES_AGENT_MODEL", raising=False)
    monkeypatch.delenv("SECURITY_RESEARCH_SLIDES_AGENT_MODEL", raising=False)
    monkeypatch.setattr(
        model_control,
        "get_auth_statuses",
        lambda live=True: [_status("codex"), _status("claude"), _status("openai_api")],
    )
    agency = _security_agency()

    state = model_control.set_agent_model(
        agency,
        "Slides Agent",
        "subscription/claude",
        agency_id="security-research",
    )

    assert agency.agents["Slides Agent"].model is not None
    env_lines = env_path.read_text(encoding="utf-8").splitlines()
    assert "SECURITY_RESEARCH_SLIDES_AGENT_MODEL='subscription/claude'" in env_lines
    assert not any(line.startswith("SLIDES_AGENT_MODEL=") for line in env_lines)
    slides = next(item for item in state["agents"] if item["name"] == "Slides Agent")
    assert slides["envKey"] == "SECURITY_RESEARCH_SLIDES_AGENT_MODEL"


def test_compat_exports_include_security_env_vars():
    env_keys = {env_key for _, env_key in model_control.AGENT_MODEL_ENV_VARS}
    assert "ORCHESTRATOR_MODEL" in env_keys
    assert "SECURITY_RESEARCH_ORCHESTRATOR_MODEL" in env_keys
    assert "SECURITY_RESEARCH_SLIDES_AGENT_MODEL" in env_keys
    assert model_control.SUBSCRIPTION_FIRST_MODELS["VULNERABILITY_RESEARCHER_MODEL"]
    assert model_control.SUBSCRIPTION_FIRST_MODELS["SECURITY_RESEARCH_SLIDES_AGENT_MODEL"]
