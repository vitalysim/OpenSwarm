from __future__ import annotations

import json
from pathlib import Path

import pytest

from openswarm_skill_registry import SkillRegistryError, list_skills, load_skill
from shared_tools import ListOpenSwarmSkills, LoadOpenSwarmSkill


def _write_skill(root: Path, folder: str, name: str, description: str, body: str = "Use this skill.") -> Path:
    skill_dir = root / folder
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n\n{body}\n",
        encoding="utf-8",
    )
    return skill_dir


def test_discovers_and_loads_project_local_skill(monkeypatch, tmp_path):
    root = tmp_path / "openswarm_skills"
    skill_dir = _write_skill(root, "incident-brief", "incident-brief", "Write incident briefs.")
    (skill_dir / "references").mkdir()
    (skill_dir / "references" / "style.md").write_text("Keep claims evidence-first.", encoding="utf-8")

    monkeypatch.setenv("OPENSWARM_SKILLS_DIR", str(root))

    skills = list_skills()
    assert [skill.name for skill in skills] == ["incident-brief"]

    loaded = load_skill("incident-brief")
    assert loaded.description == "Write incident briefs."
    assert "Use this skill." in loaded.content
    assert loaded.resources[0].relative_path == "references/style.md"
    assert loaded.resources[0].text_preview == "Keep claims evidence-first."


def test_tools_return_json_and_do_not_execute_scripts(monkeypatch, tmp_path):
    root = tmp_path / "openswarm_skills"
    skill_dir = _write_skill(root, "deck-style", "deck-style", "Security deck style.")
    (skill_dir / "scripts").mkdir()
    (skill_dir / "scripts" / "build.py").write_text("raise SystemExit('should not run')", encoding="utf-8")
    monkeypatch.setenv("OPENSWARM_SKILLS_DIR", str(root))

    listed = json.loads(ListOpenSwarmSkills().run())
    assert listed["skills"][0]["name"] == "deck-style"

    loaded = json.loads(LoadOpenSwarmSkill(name="deck-style").run())
    assert loaded["execution"]["scripts_executed"] is False
    assert loaded["resources"][0]["relative_path"] == "scripts/build.py"


def test_rejects_missing_frontmatter(tmp_path):
    root = tmp_path / "openswarm_skills"
    broken = root / "broken"
    broken.mkdir(parents=True)
    (broken / "SKILL.md").write_text("# Missing frontmatter", encoding="utf-8")

    with pytest.raises(SkillRegistryError, match="missing YAML frontmatter"):
        list_skills(root)


def test_rejects_duplicate_skill_names(tmp_path):
    root = tmp_path / "openswarm_skills"
    _write_skill(root, "one", "duplicate", "First.")
    _write_skill(root, "two", "duplicate", "Second.")

    with pytest.raises(SkillRegistryError, match="Duplicate OpenSwarm skill names"):
        list_skills(root)


def test_rejects_symlink_resource_escape(tmp_path):
    root = tmp_path / "openswarm_skills"
    skill_dir = _write_skill(root, "safe", "safe", "Safe skill.")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    (skill_dir / "outside.txt").symlink_to(outside)

    with pytest.raises(SkillRegistryError, match="escapes skills root"):
        list_skills(root)
