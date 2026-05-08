from __future__ import annotations

import pytest

from workspace_context import (
    CLIENT_CONFIG_WORKING_DIRECTORY_KEY,
    extract_working_directory_from_client_config,
    get_current_working_directory,
    reset_current_working_directory,
    resolve_input_path,
    resolve_output_path,
    set_current_working_directory,
)
from virtual_assistant.tools.ReadFile import ReadFile
from virtual_assistant.tools.WriteFile import WriteFile


def test_context_resolves_relative_paths_under_current_working_directory(tmp_path):
    token = set_current_working_directory(tmp_path)
    try:
        target = tmp_path / "notes" / "case.md"
        target.parent.mkdir()
        target.write_text("# Case\n", encoding="utf-8")

        assert get_current_working_directory() == tmp_path
        assert resolve_input_path("notes/case.md") == target
        output = resolve_output_path("out/result.md")
        assert output == tmp_path / "out" / "result.md"
        assert output.parent.exists()
    finally:
        reset_current_working_directory(token)


def test_relative_paths_cannot_escape_current_working_directory(tmp_path):
    token = set_current_working_directory(tmp_path)
    try:
        with pytest.raises(ValueError):
            resolve_input_path("../escape.md")
    finally:
        reset_current_working_directory(token)


def test_client_config_working_directory_is_extracted_and_stripped(tmp_path):
    directory, sanitized = extract_working_directory_from_client_config(
        {
            CLIENT_CONFIG_WORKING_DIRECTORY_KEY: str(tmp_path),
            "model": "gpt-5.2",
        }
    )

    assert directory == str(tmp_path)
    assert sanitized == {"model": "gpt-5.2"}


def test_read_and_write_file_tools_accept_relative_paths(tmp_path):
    token = set_current_working_directory(tmp_path)
    try:
        write_result = WriteFile(file_path="notes/case.md", content="# Case\n").run()
        assert "Successfully created file" in write_result
        assert (tmp_path / "notes" / "case.md").read_text(encoding="utf-8") == "# Case\n"

        read_result = ReadFile(file_path="notes/case.md").run()
        assert "# Case" in read_result
    finally:
        reset_current_working_directory(token)
