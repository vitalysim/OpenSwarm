from pathlib import Path

from agency_swarm import Agent
from shared_tools import ListOpenSwarmSkills, LoadOpenSwarmSkill, WebResearchSearch
from security_research_tools import LoadSecurityDesignLanguage, UpdateSecurityResearchProgress

from config import get_agent_model, get_agent_model_settings


MODEL_ENV_VAR = "SECURITY_RESEARCH_ORCHESTRATOR_MODEL"
_CURRENT_DIR = Path(__file__).parent


def create_security_research_orchestrator() -> Agent:
    return Agent(
        name="Security Research Orchestrator",
        description="Coordinates security research work across intelligence, vulnerability, OSINT, lab, writing, and design specialists.",
        instructions=str(_CURRENT_DIR / "instructions.md"),
        model=get_agent_model(MODEL_ENV_VAR),
        model_settings=get_agent_model_settings(MODEL_ENV_VAR, reasoning_effort="high", truncation="auto"),
        tools=[
            ListOpenSwarmSkills,
            LoadOpenSwarmSkill,
            WebResearchSearch,
            UpdateSecurityResearchProgress,
            LoadSecurityDesignLanguage,
        ],
        conversation_starters=[
            "Coordinate a public vulnerability research brief for this CVE.",
            "Plan an OSINT-backed threat intelligence report.",
            "Turn these findings into a blog post and visual package.",
        ],
    )
