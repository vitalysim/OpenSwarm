from agency_swarm.tools import BaseTool
from pydantic import Field

from openswarm_skill_registry import SkillRegistryError, list_skills_json, load_skill_json


class ListOpenSwarmSkills(BaseTool):
    """
    List project-local OpenSwarm skills available from openswarm_skills/.

    Use this before selecting a reusable workflow, style guide, report format,
    or domain-specific instruction set. Skills are provider-neutral and work
    with OpenAI, Claude, Codex, and API-backed models.
    """

    def run(self) -> str:
        try:
            return list_skills_json()
        except SkillRegistryError as exc:
            return f"Error listing OpenSwarm skills: {exc}"


class LoadOpenSwarmSkill(BaseTool):
    """
    Load one project-local OpenSwarm skill by name.

    This returns SKILL.md instructions and read-only bundled resources. It does
    not execute scripts or commands from the skill.
    """

    name: str = Field(..., description="OpenSwarm skill name from ListOpenSwarmSkills.")

    def run(self) -> str:
        try:
            return load_skill_json(self.name)
        except SkillRegistryError as exc:
            return f"Error loading OpenSwarm skill: {exc}"
