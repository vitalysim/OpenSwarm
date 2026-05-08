"""Project-local OpenSwarm skill discovery and loading.

OpenSwarm skills are intentionally provider-neutral. They use the familiar
`SKILL.md` folder shape, but v1 only loads instructions and read-only resources;
it does not execute bundled scripts.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_SKILLS_DIR = REPO_ROOT / "openswarm_skills"
SKILLS_DIR_ENV = "OPENSWARM_SKILLS_DIR"
MAX_SKILL_MD_BYTES = 256 * 1024
MAX_RESOURCE_BYTES = 32 * 1024
MAX_RESOURCE_FILES = 24
TEXT_RESOURCE_SUFFIXES = {
    ".css",
    ".csv",
    ".html",
    ".json",
    ".md",
    ".py",
    ".txt",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
}


class SkillRegistryError(ValueError):
    """Raised when the skills folder contains unsafe or invalid state."""


@dataclass(frozen=True)
class SkillResource:
    relative_path: str
    path: Path
    size_bytes: int
    text_preview: str | None = None


@dataclass(frozen=True)
class OpenSwarmSkill:
    name: str
    description: str
    location: Path
    directory: Path
    content: str
    resources: tuple[SkillResource, ...]

    def metadata_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "location": str(self.location),
            "directory": str(self.directory),
            "resource_count": len(self.resources),
        }

    def load_dict(self) -> dict[str, Any]:
        return {
            **self.metadata_dict(),
            "content": self.content,
            "resources": [
                {
                    "relative_path": item.relative_path,
                    "path": str(item.path),
                    "size_bytes": item.size_bytes,
                    **({"text_preview": item.text_preview} if item.text_preview is not None else {}),
                }
                for item in self.resources
            ],
            "execution": {
                "scripts_executed": False,
                "note": "OpenSwarm skills v1 loads instructions and read-only resources only.",
            },
        }


def get_skills_root() -> Path:
    raw = os.getenv(SKILLS_DIR_ENV, "").strip()
    if not raw:
        return DEFAULT_SKILLS_DIR
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def list_skills(root: Path | None = None) -> list[OpenSwarmSkill]:
    skills_root = _safe_root(root or get_skills_root())
    if not skills_root.exists():
        return []
    if not skills_root.is_dir():
        raise SkillRegistryError(f"OpenSwarm skills path is not a directory: {skills_root}")

    found: dict[str, OpenSwarmSkill] = {}
    duplicates: dict[str, list[Path]] = {}
    for skill_md in sorted(skills_root.glob("*/SKILL.md")):
        skill = _load_skill_file(skill_md, skills_root)
        existing = found.get(skill.name)
        if existing:
            duplicates.setdefault(skill.name, [existing.location]).append(skill.location)
            continue
        found[skill.name] = skill

    if duplicates:
        details = "; ".join(
            f"{name}: {', '.join(str(path) for path in paths)}" for name, paths in sorted(duplicates.items())
        )
        raise SkillRegistryError(f"Duplicate OpenSwarm skill names are not allowed: {details}")

    return sorted(found.values(), key=lambda item: item.name.casefold())


def load_skill(name: str, root: Path | None = None) -> OpenSwarmSkill:
    target = name.strip()
    if not target:
        raise SkillRegistryError("Skill name is required.")

    folded = target.casefold()
    for skill in list_skills(root):
        if skill.name.casefold() == folded or skill.directory.name.casefold() == folded:
            return skill
    raise SkillRegistryError(f"OpenSwarm skill not found: {target}")


def list_skills_json(root: Path | None = None) -> str:
    return json.dumps(
        {
            "skills_dir": str(_safe_root(root or get_skills_root())),
            "skills": [skill.metadata_dict() for skill in list_skills(root)],
        },
        indent=2,
    )


def load_skill_json(name: str, root: Path | None = None) -> str:
    return json.dumps(load_skill(name, root).load_dict(), indent=2)


def _safe_root(root: Path) -> Path:
    return root.expanduser().resolve()


def _safe_child(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise SkillRegistryError(f"OpenSwarm skill path escapes skills root: {path}") from exc
    return resolved


def _load_skill_file(skill_md: Path, root: Path) -> OpenSwarmSkill:
    path = _safe_child(skill_md, root)
    directory = _safe_child(path.parent, root)
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise SkillRegistryError(f"Cannot read OpenSwarm skill file: {path}") from exc
    if size > MAX_SKILL_MD_BYTES:
        raise SkillRegistryError(f"OpenSwarm skill file is too large: {path}")

    raw = path.read_text(encoding="utf-8")
    metadata, content = _parse_frontmatter(raw, path)
    name = metadata.get("name", "").strip()
    description = metadata.get("description", "").strip()
    if not name:
        raise SkillRegistryError(f"OpenSwarm skill is missing frontmatter field `name`: {path}")
    if not description:
        raise SkillRegistryError(f"OpenSwarm skill is missing frontmatter field `description`: {path}")

    return OpenSwarmSkill(
        name=name,
        description=description,
        location=path,
        directory=directory,
        content=content.strip(),
        resources=_collect_resources(directory, path, root),
    )


def _parse_frontmatter(raw: str, path: Path) -> tuple[dict[str, str], str]:
    lines = raw.splitlines()
    if not lines or lines[0].strip() != "---":
        raise SkillRegistryError(f"OpenSwarm skill is missing YAML frontmatter: {path}")

    end_index: int | None = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = index
            break
    if end_index is None:
        raise SkillRegistryError(f"OpenSwarm skill frontmatter is not closed: {path}")

    metadata: dict[str, str] = {}
    for line in lines[1:end_index]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        metadata[key.strip()] = _clean_scalar(value.strip())

    return metadata, "\n".join(lines[end_index + 1 :])


def _clean_scalar(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _collect_resources(directory: Path, skill_md: Path, root: Path) -> tuple[SkillResource, ...]:
    resources: list[SkillResource] = []
    for candidate in sorted(directory.rglob("*")):
        if len(resources) >= MAX_RESOURCE_FILES:
            break
        if candidate == skill_md or not candidate.is_file():
            continue
        path = _safe_child(candidate, root)
        try:
            size = path.stat().st_size
        except OSError:
            continue
        relative = path.relative_to(directory).as_posix()
        preview: str | None = None
        if path.suffix.casefold() in TEXT_RESOURCE_SUFFIXES and size <= MAX_RESOURCE_BYTES:
            try:
                preview = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                preview = None
        resources.append(
            SkillResource(
                relative_path=relative,
                path=path,
                size_bytes=size,
                text_preview=preview,
            )
        )
    return tuple(resources)
