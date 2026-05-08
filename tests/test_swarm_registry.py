from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import swarm_registry


def test_registry_contains_named_swarms():
    assert swarm_registry.get_swarm_registration("open-swarm").name == "OpenSwarm"
    assert swarm_registry.get_swarm_registration("security-research").name == "Security Research"


def test_security_factory_resolves_when_module_is_available(monkeypatch):
    module = ModuleType("security_research")

    def create_agency(**_: object) -> SimpleNamespace:
        return SimpleNamespace(name="Security Research")

    module.create_agency = create_agency  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "security_research", module)

    factory = swarm_registry.get_swarm_factory("security-research")
    agency = factory(load_threads_callback=lambda: [])

    assert agency.name == "Security Research"
    assert agency.openswarm_swarm_id == "security-research"


def test_security_factory_includes_reused_slides_agent(monkeypatch):
    class FakeAgent(SimpleNamespace):
        def __gt__(self, other: object) -> tuple[object, object]:
            return (self, other)

    class FakeAgency:
        def __init__(self, *agents: FakeAgent, **kwargs: object) -> None:
            self.name = kwargs["name"]
            self.agents = {agent.name: agent for agent in agents}
            self.entry_points = [agents[0]]

    agency_swarm = ModuleType("agency_swarm")
    agency_swarm.Agency = FakeAgency  # type: ignore[attr-defined]
    tools = ModuleType("agency_swarm.tools")
    tools.Handoff = object()  # type: ignore[attr-defined]
    tools.SendMessage = object()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "agency_swarm", agency_swarm)
    monkeypatch.setitem(sys.modules, "agency_swarm.tools", tools)

    def add_agent_module(module_name: str, factory_name: str, agent_name: str) -> None:
        module = ModuleType(module_name)

        def factory() -> FakeAgent:
            return FakeAgent(name=agent_name)

        setattr(module, factory_name, factory)
        monkeypatch.setitem(sys.modules, module_name, module)

    add_agent_module("osint_enrichment_specialist", "create_osint_enrichment_specialist", "OSINT Enrichment Specialist")
    add_agent_module("security_lab_analyst", "create_security_lab_analyst", "Security Lab Analyst")
    add_agent_module("security_research_lead", "create_security_research_lead", "Security Research Lead")
    add_agent_module(
        "security_research_orchestrator",
        "create_security_research_orchestrator",
        "Security Research Orchestrator",
    )
    add_agent_module("security_visual_designer", "create_security_visual_designer", "Security Visual Designer")
    add_agent_module("technical_blog_writer", "create_technical_blog_writer", "Technical Blog Writer")
    add_agent_module("threat_intelligence_analyst", "create_threat_intelligence_analyst", "Threat Intelligence Analyst")
    add_agent_module("vulnerability_researcher", "create_vulnerability_researcher", "Vulnerability Researcher")

    slides_module = ModuleType("slides_agent")
    captured: dict[str, str] = {}

    def create_slides_agent(model_env_var: str = "SLIDES_AGENT_MODEL") -> FakeAgent:
        captured["model_env_var"] = model_env_var
        return FakeAgent(name="Slides Agent")

    slides_module.create_slides_agent = create_slides_agent  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "slides_agent", slides_module)

    agency = swarm_registry.create_security_research_agency(load_threads_callback=lambda: [])

    assert "Slides Agent" in agency.agents
    assert captured["model_env_var"] == "SECURITY_RESEARCH_SLIDES_AGENT_MODEL"
    assert agency.openswarm_swarm_id == "security-research"
