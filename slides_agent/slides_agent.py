from agency_swarm import Agent
from agency_swarm.tools import IPythonInterpreter, PersistentShellTool, LoadFileAttachment
from datetime import datetime, timezone
from pathlib import Path
from virtual_assistant.tools.ReadFile import ReadFile
from shared_tools import ListOpenSwarmSkills, LoadOpenSwarmSkill, WebResearchSearch
from shared_tools.CopyFile import CopyFile

from config import get_agent_model, get_agent_model_settings

# Import slide tools
from .tools import (
    InsertNewSlides,
    ModifySlide,
    ManageTheme,
    DeleteSlide,
    SlideScreenshot,
    ReadSlide,
    BuildPptxFromHtmlSlides,
    RestoreSnapshot,
    CreatePptxThumbnailGrid,
    CheckSlideCanvasOverflow,
    CheckSlide,
    DownloadImage,
    EnsureRasterImage,
    ImageSearch,
    GenerateImage,
)

_INSTRUCTIONS_PATH = Path(__file__).parent / "instructions.md"
MODEL_ENV_VAR = "SLIDES_AGENT_MODEL"


def _list_existing_projects() -> str:
    from .tools.slide_file_utils import get_mnt_dir
    base = get_mnt_dir()
    if not base.exists():
        return "(none)"
    dirs = sorted(d.name for d in base.iterdir() if d.is_dir())
    return "\n".join(f"  - {d}" for d in dirs) if dirs else "(none)"


def _build_instructions() -> str:
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    body = _INSTRUCTIONS_PATH.read_text(encoding="utf-8")
    projects_block = _list_existing_projects()
    return (
        f"{body}\n\n"
        f"Current date/time (UTC): {now_utc}\n\n"
        f"Existing project folders (do NOT reuse these names for a new presentation):\n{projects_block}"
    )


def create_slides_agent(model_env_var: str = MODEL_ENV_VAR) -> Agent:
    return Agent(
        name="Slides Agent",
        description="PowerPoint presentation specialist for creating, editing, and analyzing .pptx files",
        instructions=_build_instructions(),
        # files_folder=os.path.join(current_dir, "files"),
        # tools_folder=os.path.join(current_dir, "tools"),
        tools=[
            ListOpenSwarmSkills,
            LoadOpenSwarmSkill,
            # Slide creation and management: InsertNewSlides then ModifySlide
            InsertNewSlides,
            ModifySlide,
            ManageTheme,
            DeleteSlide,
            SlideScreenshot,
            ReadSlide,
            # PPTX building
            BuildPptxFromHtmlSlides,
            RestoreSnapshot,
            CreatePptxThumbnailGrid,
            CheckSlideCanvasOverflow,
            CheckSlide,
            # Image download
            DownloadImage,
            EnsureRasterImage,
            GenerateImage,
            # Template-based editing
            # ExtractPptxTextInventory,
            # RearrangePptxSlidesFromTemplate,
            # ApplyPptxTextReplacements,
            ImageSearch,
            # Utility tools
            IPythonInterpreter,
            PersistentShellTool,
            LoadFileAttachment,
            CopyFile,
            ReadFile,
            WebResearchSearch,
        ],
        model=get_agent_model(model_env_var),
        model_settings=get_agent_model_settings(model_env_var, reasoning_effort="high", verbosity="medium"),
        conversation_starters=[
            "Create a new presentation about the benefits of using AI in the workplace.",
            "Edit my existing presentation and improve the design.",
            "Create a pitch deck for my startup idea.",
            "Turn this document into a professional slide deck.",
        ],
    )


if __name__ == "__main__":
    from agency_swarm import Agency
    Agency(create_slides_agent()).terminal_demo(reload=False)
