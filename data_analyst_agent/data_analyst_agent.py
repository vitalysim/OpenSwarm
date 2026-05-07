import os
from agency_swarm import Agent, ModelSettings
from openai.types.shared.reasoning import Reasoning
from agency_swarm.tools import (
    PersistentShellTool,
    IPythonInterpreter,
    LoadFileAttachment,
)
from shared_tools import CopyFile, ExecuteTool, FindTools, ManageConnections, SearchTools, WebResearchSearch

from config import get_agent_model, is_openai_provider

current_dir = os.path.dirname(os.path.abspath(__file__))
instructions_path = os.path.join(current_dir, "instructions.md")
MODEL_ENV_VAR = "DATA_ANALYST_MODEL"

def create_data_analyst() -> Agent:
    return Agent(
        name="Data Analyst",
        description="Advanced data analytics agent that generates charts and provides actionable insights.",
        instructions=instructions_path,
        tools_folder=os.path.join(current_dir, "tools"),
        model=get_agent_model(MODEL_ENV_VAR),
        tools=[
            WebResearchSearch,
            PersistentShellTool,
            IPythonInterpreter,
            LoadFileAttachment,
            CopyFile,
            ExecuteTool,
            FindTools,
            ManageConnections,
            SearchTools,
        ],
        model_settings=ModelSettings(
            reasoning=Reasoning(effort="medium", summary="auto") if is_openai_provider(MODEL_ENV_VAR) else None,
            truncation="auto",
        ),
        conversation_starters=[
            "Analyze this CSV file and show me the key trends.",
            "Create a dashboard with charts from my sales data.",
            "Connect to my Google Analytics and summarize last month's traffic.",
            "Find hidden patterns in this dataset and visualize them.",
        ],
    )
