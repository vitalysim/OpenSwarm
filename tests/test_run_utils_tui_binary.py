from __future__ import annotations

import sys
from pathlib import Path
import os

import run_utils


def _write_binary(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("placeholder", encoding="utf-8")


def test_resolve_local_tui_bin_prefers_dev_build_over_root_release(tmp_path: Path):
    root_binary = tmp_path / run_utils._resolve_bin_name()
    dist_binary = (
        tmp_path
        / "packages"
        / "openswarm-tui"
        / "packages"
        / "opencode"
        / "dist"
        / run_utils._resolve_dist_dirname()
        / "bin"
        / ("agentswarm.exe" if sys.platform == "win32" else "agentswarm")
    )
    _write_binary(root_binary)
    _write_binary(dist_binary)

    assert run_utils._resolve_local_tui_bin(tmp_path) == dist_binary


def test_resolve_local_tui_bin_uses_root_release_when_dev_build_is_absent(tmp_path: Path):
    root_binary = tmp_path / run_utils._resolve_bin_name()
    _write_binary(root_binary)

    assert run_utils._resolve_local_tui_bin(tmp_path) == root_binary


def test_resolve_local_tui_bin_returns_none_without_binary(tmp_path: Path):
    assert run_utils._resolve_local_tui_bin(tmp_path) is None


def test_staleness_warning_reports_dev_binary_older_than_tui_source(tmp_path: Path):
    dist_binary = (
        tmp_path
        / "packages"
        / "openswarm-tui"
        / "packages"
        / "opencode"
        / "dist"
        / run_utils._resolve_dist_dirname()
        / "bin"
        / ("agentswarm.exe" if sys.platform == "win32" else "agentswarm")
    )
    source = tmp_path / run_utils._TUI_STALENESS_SOURCE_RELATIVE_PATHS[0]
    _write_binary(dist_binary)
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("source", encoding="utf-8")
    os.utime(dist_binary, (100, 100))
    os.utime(source, (200, 200))

    message = run_utils._local_tui_staleness_message(dist_binary, tmp_path)

    assert message is not None
    assert "npm run build:tui" in message
    assert run_utils._TUI_STALENESS_SOURCE_RELATIVE_PATHS[0] in message


def test_staleness_warning_ignores_root_release_binary(tmp_path: Path):
    root_binary = tmp_path / run_utils._resolve_bin_name()
    source = tmp_path / run_utils._TUI_STALENESS_SOURCE_RELATIVE_PATHS[0]
    _write_binary(root_binary)
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("source", encoding="utf-8")
    os.utime(root_binary, (100, 100))
    os.utime(source, (200, 200))

    assert run_utils._local_tui_staleness_message(root_binary, tmp_path) is None


def test_configure_openswarm_skills_env_resolves_relative_path(monkeypatch):
    monkeypatch.setenv("OPENSWARM_SKILLS_DIR", "custom-skills")
    monkeypatch.delenv("OPENCODE_DISABLE_EXTERNAL_SKILLS", raising=False)

    run_utils._configure_openswarm_skills_env()

    assert Path(os.environ["OPENSWARM_SKILLS_DIR"]).is_absolute()
    assert os.environ["OPENSWARM_SKILLS_DIR"].endswith("custom-skills")
    assert os.environ["OPENCODE_DISABLE_EXTERNAL_SKILLS"] == "true"
