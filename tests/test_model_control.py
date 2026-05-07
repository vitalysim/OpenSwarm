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
