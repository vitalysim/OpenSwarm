from pathlib import Path

from agency_swarm import Agent
from shared_tools import WebResearchSearch
from security_research_tools import (
    LoadSecurityDesignLanguage,
    LookupCISAKEV,
    LookupCVE,
    LookupEPSS,
    LookupMitreKnowledge,
    ManageSecurityResearchNote,
    ManageSecurityResearchResource,
    UpdateSecurityResearchProgress,
)

from config import get_agent_model, get_agent_model_settings


MODEL_ENV_VAR = "SECURITY_RESEARCH_LEAD_MODEL"
_CURRENT_DIR = Path(__file__).parent


def create_security_research_lead() -> Agent:
    return Agent(
        name="Security Research Lead",
        description="Senior security researcher who scopes investigations, reviews evidence, and synthesizes defensible conclusions.",
        instructions=str(_CURRENT_DIR / "instructions.md"),
        model=get_agent_model(MODEL_ENV_VAR),
        model_settings=get_agent_model_settings(MODEL_ENV_VAR, reasoning_effort="high", truncation="auto"),
        tools=[
            WebResearchSearch,
            LookupCVE,
            LookupCISAKEV,
            LookupEPSS,
            LookupMitreKnowledge,
            ManageSecurityResearchNote,
            ManageSecurityResearchResource,
            UpdateSecurityResearchProgress,
            LoadSecurityDesignLanguage,
        ],
    )
