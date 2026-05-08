"""Utilities for managing document project directories."""

import re
from pathlib import Path

from workspace_context import get_artifact_root


def get_mnt_dir() -> Path:
    return get_artifact_root()


def get_project_dir(project_name: str) -> Path:
    return get_mnt_dir() / project_name / "documents"


def next_docx_version(desired: Path) -> Path:
    """Return desired if it doesn't exist, otherwise the next free _vN path.

    Strips any existing _vN suffix before searching so passing report_v2.docx
    when that file already exists yields report_v3.docx, not report_v2_v2.docx.
    """
    if not desired.exists():
        return desired
    base = re.sub(r"_v\d+$", "", desired.stem)
    n = 2
    while True:
        candidate = desired.parent / f"{base}_v{n}{desired.suffix}"
        if not candidate.exists():
            return candidate
        n += 1
