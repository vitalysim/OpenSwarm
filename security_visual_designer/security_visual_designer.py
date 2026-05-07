from pathlib import Path

from agency_swarm import Agent
from agency_swarm.tools import LoadFileAttachment
from image_generation_agent.tools.CombineImages import CombineImages
from image_generation_agent.tools.EditImages import EditImages
from image_generation_agent.tools.GenerateImages import GenerateImages
from image_generation_agent.tools.RemoveBackground import RemoveBackground
from shared_tools import CopyFile
from security_research_tools import LoadSecurityDesignLanguage, ManageSecurityResearchNote, ManageSecurityResearchResource

from config import get_agent_model, get_agent_model_settings


MODEL_ENV_VAR = "SECURITY_VISUAL_DESIGNER_MODEL"
_CURRENT_DIR = Path(__file__).parent


def create_security_visual_designer() -> Agent:
    return Agent(
        name="Security Visual Designer",
        description="Creates design direction, diagrams, timelines, and visual briefs for security research deliverables.",
        instructions=str(_CURRENT_DIR / "instructions.md"),
        model=get_agent_model(MODEL_ENV_VAR),
        model_settings=get_agent_model_settings(MODEL_ENV_VAR, reasoning_effort="medium", truncation="auto"),
        tools=[
            LoadSecurityDesignLanguage,
            GenerateImages,
            EditImages,
            CombineImages,
            RemoveBackground,
            LoadFileAttachment,
            CopyFile,
            ManageSecurityResearchNote,
            ManageSecurityResearchResource,
        ],
    )
