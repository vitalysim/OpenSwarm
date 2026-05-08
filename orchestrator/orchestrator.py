from agency_swarm import Agent
from dotenv import load_dotenv

from config import get_agent_model, get_agent_model_settings
from shared_tools import ListOpenSwarmSkills, LoadOpenSwarmSkill

load_dotenv()

MODEL_ENV_VAR = "ORCHESTRATOR_MODEL"


def create_orchestrator() -> Agent:
    return Agent(
        name="Orchestrator",
        description=(
            "Primary coordinator that plans multi-agent workflows, runs independent workstreams in parallel, "
            "and hands off to a specialist when tight user iteration is needed."
        ),
        instructions="./instructions.md",
        model=get_agent_model(MODEL_ENV_VAR),
        model_settings=get_agent_model_settings(MODEL_ENV_VAR, reasoning_effort="medium"),
        tools=[ListOpenSwarmSkills, LoadOpenSwarmSkill],
        conversation_starters=[
            "What can this agency do?",
            "Build a full launch package: research, slides, docs, and creative assets.",
            "Analyze my data and then turn insights into a polished executive deck.",
            "Coordinate a workflow for proposal doc + promo visuals + short product video.",
        ],
    )


if __name__ == "__main__":
    from agency_swarm import Agency
    Agency(create_orchestrator()).terminal_demo()
