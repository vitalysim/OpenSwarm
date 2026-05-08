from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

import model_control
from auth_registry import AuthStatus
from patches.patch_openswarm_model_control import install_factory_model_control_routes


def _status(auth_id: str) -> AuthStatus:
    return AuthStatus(
        id=auth_id,
        name=auth_id,
        category="subscription",
        state="available",
        detail="available",
        capabilities=("text",),
    )


def _agency(name: str, swarm_id: str, agent_names: list[str]) -> SimpleNamespace:
    agents = {agent_name: SimpleNamespace(name=agent_name, model=None, model_settings=None) for agent_name in agent_names}
    return SimpleNamespace(
        name=name,
        openswarm_swarm_id=swarm_id,
        agents=agents,
        entry_points=[next(iter(agents.values()))],
    )


def test_factory_routes_are_isolated_by_route_agency_id(monkeypatch):
    monkeypatch.setenv("DEFAULT_MODEL", "subscription/codex")
    monkeypatch.setattr(
        model_control,
        "get_auth_statuses",
        lambda live=True: [_status("codex"), _status("claude"), _status("openai_api")],
    )
    app = FastAPI()
    factories = {
        "open-swarm": lambda **_: _agency("OpenSwarm", "open-swarm", ["Orchestrator", "Slides Agent"]),
        "security-research": lambda **_: _agency(
            "Security Research",
            "security-research",
            ["Security Research Orchestrator", "Vulnerability Researcher", "Slides Agent"],
        ),
    }

    install_factory_model_control_routes(app, factories)
    client = TestClient(app)

    open_state = client.get("/open-swarm/openswarm/models").json()
    security_state = client.get("/security-research/openswarm/models").json()

    assert {item["name"] for item in open_state["agents"]} >= {"Orchestrator", "Slides Agent"}
    assert "Security Research Orchestrator" not in {item["name"] for item in open_state["agents"]}
    assert {item["name"] for item in security_state["agents"]} >= {
        "Security Research Orchestrator",
        "Vulnerability Researcher",
        "Slides Agent",
    }
    security_slides = next(item for item in security_state["agents"] if item["name"] == "Slides Agent")
    assert security_slides["envKey"] == "SECURITY_RESEARCH_SLIDES_AGENT_MODEL"
