"""Request-scoped OpenSwarm working-directory helpers."""

from __future__ import annotations

from contextvars import ContextVar, Token
import os
from pathlib import Path
from typing import Any


CLIENT_CONFIG_WORKING_DIRECTORY_KEY = "openswarm_working_directory"
_CURRENT_WORKING_DIRECTORY: ContextVar[str | None] = ContextVar("openswarm_working_directory", default=None)
_REPO_ROOT = Path(__file__).resolve().parent


def normalize_working_directory(value: str | os.PathLike[str] | None) -> Path | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (_REPO_ROOT / path).resolve()
    else:
        path = path.resolve()
    if not path.exists() or not path.is_dir():
        return None
    return path


def set_current_working_directory(directory: str | os.PathLike[str] | None) -> Token[str | None]:
    path = normalize_working_directory(directory)
    return _CURRENT_WORKING_DIRECTORY.set(str(path) if path is not None else None)


def reset_current_working_directory(token: Token[str | None]) -> None:
    _CURRENT_WORKING_DIRECTORY.reset(token)


def has_active_working_directory() -> bool:
    if _CURRENT_WORKING_DIRECTORY.get():
        return True
    return bool(os.getenv("OPENSWARM_WORKING_DIRECTORY") or os.getenv("AGENTSWARM_RUN_PROJECT"))


def get_current_working_directory() -> Path:
    for raw in (
        _CURRENT_WORKING_DIRECTORY.get(),
        os.getenv("OPENSWARM_WORKING_DIRECTORY"),
        os.getenv("AGENTSWARM_RUN_PROJECT"),
    ):
        path = normalize_working_directory(raw)
        if path is not None:
            return path
    return _REPO_ROOT


def get_artifact_root() -> Path:
    root = get_current_working_directory()
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_input_path(path_value: str | os.PathLike[str], *, allow_absolute: bool = True) -> Path:
    return _resolve_path(path_value, allow_absolute=allow_absolute)


def resolve_output_path(path_value: str | os.PathLike[str], *, allow_absolute: bool = True) -> Path:
    path = _resolve_path(path_value, allow_absolute=allow_absolute)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def extract_working_directory_from_client_config(
    client_config: Any,
) -> tuple[str | None, dict[str, Any] | None]:
    if not isinstance(client_config, dict):
        return None, client_config

    cleaned = dict(client_config)
    raw = cleaned.pop(CLIENT_CONFIG_WORKING_DIRECTORY_KEY, None)
    raw = raw if isinstance(raw, str) else None
    path = normalize_working_directory(raw)
    return (str(path) if path is not None else None), (cleaned or None)


def _resolve_path(path_value: str | os.PathLike[str], *, allow_absolute: bool) -> Path:
    raw = str(path_value).strip()
    if not raw:
        raise ValueError("Path must not be empty.")

    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        if not allow_absolute:
            raise ValueError(f"Absolute paths are not allowed here: {raw}")
        return candidate.resolve()

    base = get_current_working_directory().resolve()
    resolved = (base / candidate).resolve()
    if resolved != base and base not in resolved.parents:
        raise ValueError(f"Path escapes current working directory: {raw}")
    return resolved
