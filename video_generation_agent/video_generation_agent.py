from agency_swarm import Agent
from agency_swarm.tools import LoadFileAttachment
from shared_tools import CopyFile

from config import get_agent_model, get_agent_model_settings


MODEL_ENV_VAR = "VIDEO_AGENT_MODEL"


def create_video_generation_agent() -> Agent:
    return Agent(
        name="Video Agent",
        description="A general-purpose agent for video generation and editing.",
        instructions="instructions.md",
        tools_folder="./tools",
        tools=[LoadFileAttachment, CopyFile],
        model=get_agent_model(MODEL_ENV_VAR),
        model_settings=get_agent_model_settings(MODEL_ENV_VAR, reasoning_effort="medium", truncation="auto"),
        conversation_starters=[
            "Generate a short promo video for my product launch.",
            "Create an animated explainer video about how AI works.",
            "Edit this video clip and add captions.",
            "Turn my blog post into a video with voiceover.",
        ],
    )
