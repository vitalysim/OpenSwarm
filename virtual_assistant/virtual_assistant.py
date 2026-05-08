from agency_swarm import Agent
from agency_swarm.tools import (
    PersistentShellTool,
    IPythonInterpreter,
)
from dotenv import load_dotenv

from config import get_agent_model, get_agent_model_settings
from shared_tools import (
    CopyFile,
    ExecuteTool,
    FindTools,
    ListOpenSwarmSkills,
    LoadOpenSwarmSkill,
    ManageConnections,
    SearchTools,
    WebResearchSearch,
)

load_dotenv()

# Class-level rename — idempotent, safe to run once at import time.
IPythonInterpreter.__name__ = "ProgrammaticToolCalling"

MODEL_ENV_VAR = "GENERAL_AGENT_MODEL"


def create_virtual_assistant() -> Agent:
    return Agent(
        name="General Agent",
        description="Your virtual assistant that connects to 10000+ external systems.",
        instructions="./instructions.md",
        files_folder="./files",
        tools_folder="./tools",
        model=get_agent_model(MODEL_ENV_VAR),
        model_settings=get_agent_model_settings(MODEL_ENV_VAR, reasoning_effort="medium"),
        tools=[
            ListOpenSwarmSkills,
            LoadOpenSwarmSkill,
            WebResearchSearch,
            PersistentShellTool,
            IPythonInterpreter,
            CopyFile,
            ExecuteTool,
            FindTools,
            ManageConnections,
            SearchTools,
        ],
        conversation_starters=[
            "Send a summary of my unread emails to Slack.",
            "Schedule a meeting with my team for next Monday.",
            "What external systems do I have connected?",
            "Draft and send a follow-up email to my last meeting attendees.",
        ],
    )


if __name__ == "__main__":
    from agency_swarm import Agency
    Agency(create_virtual_assistant()).terminal_demo()
