from pathlib import Path

from agency_swarm import Agent
from agency_swarm.tools import IPythonInterpreter
from shared_tools import WebResearchSearch
from security_research_tools import LookupCVE, LookupMitreKnowledge, ManageSecurityResearchNote, UpdateSecurityResearchProgress

from config import get_agent_model, get_agent_model_settings


MODEL_ENV_VAR = "SECURITY_LAB_ANALYST_MODEL"
_CURRENT_DIR = Path(__file__).parent


def create_security_lab_analyst() -> Agent:
    return Agent(
        name="Security Lab Analyst",
        description="Performs defensive lab analysis, artifact review, reproduction planning, and structured validation notes.",
        instructions=str(_CURRENT_DIR / "instructions.md"),
        model=get_agent_model(MODEL_ENV_VAR),
        model_settings=get_agent_model_settings(MODEL_ENV_VAR, reasoning_effort="high", truncation="auto"),
        tools=[WebResearchSearch, LookupCVE, LookupMitreKnowledge, ManageSecurityResearchNote, UpdateSecurityResearchProgress, IPythonInterpreter],
    )
