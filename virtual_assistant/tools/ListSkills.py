from agency_swarm.tools import BaseTool

from openswarm_skill_registry import SkillRegistryError, list_skills_json


class ListSkills(BaseTool):
    """
    Lists all project-local OpenSwarm skills currently available to you.
    """

    def run(self):
        try:
            return list_skills_json()
        except SkillRegistryError as exc:
            return f"Error listing OpenSwarm skills: {exc}"


if __name__ == "__main__":
    # Test the tool
    tool = ListSkills()
    result = tool.run()
    print(result)
