"""Central registry for OpenSwarm runtime agencies."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any, Callable


AgencyFactory = Callable[..., Any]


@dataclass(frozen=True)
class SwarmRegistration:
    id: str
    name: str
    factory_imports: tuple[str, ...]
    required_modules: tuple[str, ...] = ()

    def create_agency(self, *args: Any, **kwargs: Any) -> Any:
        factory = _load_factory(self.factory_imports)
        agency = factory(*args, **kwargs)
        setattr(agency, "openswarm_swarm_id", self.id)
        setattr(agency, "openswarm_swarm_name", self.name)
        return agency


SWARM_REGISTRY: tuple[SwarmRegistration, ...] = (
    SwarmRegistration(
        id="open-swarm",
        name="OpenSwarm",
        factory_imports=("swarm:create_agency",),
    ),
    SwarmRegistration(
        id="security-research",
        name="Security Research",
        factory_imports=(
            "security_research:create_security_research_agency",
            "security_research:create_agency",
            "security_research.security_research:create_security_research_agency",
            "security_research.security_research:create_agency",
            "security_research.swarm:create_agency",
            "swarm_registry:create_security_research_agency",
        ),
        required_modules=(
            "security_research_orchestrator",
            "security_research_lead",
            "threat_intelligence_analyst",
            "vulnerability_researcher",
            "osint_enrichment_specialist",
            "security_lab_analyst",
            "technical_blog_writer",
            "security_visual_designer",
        ),
    ),
)


def get_swarm_registration(swarm_id_or_name: str | None) -> SwarmRegistration | None:
    if not swarm_id_or_name:
        return None
    folded = _normalize_swarm_id(swarm_id_or_name)
    for registration in SWARM_REGISTRY:
        if folded in {
            _normalize_swarm_id(registration.id),
            _normalize_swarm_id(registration.name),
            registration.name.casefold(),
        }:
            return registration
    return None


def get_swarm_factory(swarm_id_or_name: str) -> AgencyFactory:
    registration = get_swarm_registration(swarm_id_or_name)
    if registration is None:
        raise KeyError(f"Unknown swarm: {swarm_id_or_name}")
    return registration.create_agency


def get_registered_agency_factories(*, available_only: bool = True) -> dict[str, AgencyFactory]:
    factories: dict[str, AgencyFactory] = {}
    for registration in SWARM_REGISTRY:
        if available_only and not is_swarm_available(registration):
            continue
        factories[registration.id] = registration.create_agency
    return factories


def is_swarm_available(registration: SwarmRegistration | str) -> bool:
    if isinstance(registration, str):
        registration = get_swarm_registration(registration)  # type: ignore[assignment]
        if registration is None:
            return False
    try:
        _load_factory(registration.factory_imports)
        for module_name in registration.required_modules:
            import_module(module_name)
    except ImportError:
        return False
    return True


def create_security_research_agency(load_threads_callback=None) -> Any:
    from agency_swarm import Agency  # noqa: PLC0415
    from agency_swarm.tools import Handoff, SendMessage  # noqa: PLC0415

    from osint_enrichment_specialist import create_osint_enrichment_specialist  # noqa: PLC0415
    from security_lab_analyst import create_security_lab_analyst  # noqa: PLC0415
    from security_research_lead import create_security_research_lead  # noqa: PLC0415
    from security_research_orchestrator import create_security_research_orchestrator  # noqa: PLC0415
    from security_visual_designer import create_security_visual_designer  # noqa: PLC0415
    from technical_blog_writer import create_technical_blog_writer  # noqa: PLC0415
    from threat_intelligence_analyst import create_threat_intelligence_analyst  # noqa: PLC0415
    from vulnerability_researcher import create_vulnerability_researcher  # noqa: PLC0415

    orchestrator = create_security_research_orchestrator()
    research_lead = create_security_research_lead()
    threat_intelligence = create_threat_intelligence_analyst()
    vulnerability_researcher = create_vulnerability_researcher()
    osint_specialist = create_osint_enrichment_specialist()
    lab_analyst = create_security_lab_analyst()
    blog_writer = create_technical_blog_writer()
    visual_designer = create_security_visual_designer()

    all_agents = [
        orchestrator,
        research_lead,
        threat_intelligence,
        vulnerability_researcher,
        osint_specialist,
        lab_analyst,
        blog_writer,
        visual_designer,
    ]

    send_message_flows = [
        (orchestrator, specialist, SendMessage)
        for specialist in all_agents
        if specialist is not orchestrator
    ]
    handoff_flows = [
        (a > b, Handoff)
        for a in all_agents
        for b in all_agents
        if a is not b
    ]

    agency = Agency(
        *all_agents,
        communication_flows=send_message_flows + handoff_flows,
        name="Security Research",
        shared_instructions="shared_instructions.md",
        load_threads_callback=load_threads_callback,
    )
    agency.openswarm_swarm_id = "security-research"
    agency.openswarm_swarm_name = "Security Research"
    return agency


def resolve_swarm_id_for_agency(agency: Any, fallback: str | None = None) -> str | None:
    explicit = getattr(agency, "openswarm_swarm_id", None)
    if explicit:
        return str(explicit)
    registration = get_swarm_registration(getattr(agency, "name", None))
    if registration:
        return registration.id
    return fallback


def is_registered_agency(agency: Any) -> bool:
    return resolve_swarm_id_for_agency(agency) is not None


def _load_factory(import_paths: tuple[str, ...]) -> AgencyFactory:
    errors: list[str] = []
    for import_path in import_paths:
        module_name, _, attr_name = import_path.partition(":")
        if not module_name or not attr_name:
            errors.append(f"{import_path}: invalid import path")
            continue
        try:
            module = import_module(module_name)
        except ImportError as exc:
            errors.append(f"{import_path}: {exc}")
            continue
        try:
            factory = getattr(module, attr_name)
        except AttributeError as exc:
            errors.append(f"{import_path}: {exc}")
            continue
        return factory
    raise ImportError("; ".join(errors))


def _normalize_swarm_id(value: str) -> str:
    return value.strip().replace("_", "-").replace(" ", "-").casefold()
