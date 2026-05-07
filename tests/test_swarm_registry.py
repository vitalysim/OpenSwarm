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
