from pathlib import Path

from agency_swarm import Agent
from shared_tools import WebResearchSearch
from security_research_tools import ManageSecurityResearchNote, ManageSecurityResearchResource

from config import get_agent_model, get_agent_model_settings


MODEL_ENV_VAR = "OSINT_ENRICHMENT_SPECIALIST_MODEL"
_CURRENT_DIR = Path(__file__).parent


def create_osint_enrichment_specialist() -> Agent:
    return Agent(
        name="OSINT Enrichment Specialist",
        description="Collects, validates, and organizes public-source evidence for security research.",
        instructions=str(_CURRENT_DIR / "instructions.md"),
        model=get_agent_model(MODEL_ENV_VAR),
        model_settings=get_agent_model_settings(MODEL_ENV_VAR, reasoning_effort="medium", truncation="auto"),
        tools=[WebResearchSearch, ManageSecurityResearchNote, ManageSecurityResearchResource],
    )
