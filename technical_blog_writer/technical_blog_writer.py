from pathlib import Path

from agency_swarm import Agent
from shared_tools import ListOpenSwarmSkills, LoadOpenSwarmSkill, WebResearchSearch
from security_research_tools import (
    CreateSecurityResearchDeliverable,
    LoadSecurityDesignLanguage,
    ManageSecurityResearchNote,
    ManageSecurityResearchResource,
)

from config import get_agent_model, get_agent_model_settings


MODEL_ENV_VAR = "TECHNICAL_BLOG_WRITER_MODEL"
_CURRENT_DIR = Path(__file__).parent


def create_technical_blog_writer() -> Agent:
    return Agent(
        name="Technical Blog Writer",
        description="Turns validated security research into clear technical articles, advisories, and executive summaries.",
        instructions=str(_CURRENT_DIR / "instructions.md"),
        model=get_agent_model(MODEL_ENV_VAR),
        model_settings=get_agent_model_settings(MODEL_ENV_VAR, reasoning_effort="medium", truncation="auto"),
        tools=[
            ListOpenSwarmSkills,
            LoadOpenSwarmSkill,
            WebResearchSearch,
            CreateSecurityResearchDeliverable,
            ManageSecurityResearchNote,
            ManageSecurityResearchResource,
            LoadSecurityDesignLanguage,
        ],
    )
