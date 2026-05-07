from agency_swarm import Agent
from agency_swarm.tools import IPythonInterpreter
from shared_tools import WebResearchSearch
from virtual_assistant.tools.ScholarSearch import ScholarSearch

from config import get_agent_model, get_agent_model_settings


MODEL_ENV_VAR = "DEEP_RESEARCH_MODEL"


def create_deep_research() -> Agent:
    return Agent(
        name="Deep Research Agent",
        description="Comprehensive deep research agent that conducts thorough research on any topic.",
        instructions="./instructions.md",
        files_folder="./files",
        tools=[WebResearchSearch, ScholarSearch, IPythonInterpreter],
        model=get_agent_model(MODEL_ENV_VAR),
        model_settings=get_agent_model_settings(MODEL_ENV_VAR, reasoning_effort="high"),
        conversation_starters=[
            "Research the latest trends in renewable energy for 2026.",
            "Give me a comprehensive analysis of the AI agent market landscape.",
            "Find recent academic papers on large language model reasoning.",
            "Compare the top 5 project management tools with pros and cons.",
        ],
    )
