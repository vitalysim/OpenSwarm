import mimetypes
import os
from typing import Optional

from agency_swarm.tools import BaseTool
from pydantic import Field
from workspace_context import resolve_input_path


class ReadFile(BaseTool):
    """
    Reads a file from the local filesystem.
    Use this tool to read file contents before editing or to understand existing code.

    Usage:
    - Relative paths are resolved against the current OpenSwarm working directory
    - By default, it reads up to 2000 lines starting from the beginning
    - You can optionally specify a line offset and limit for long files
    - Results are returned with line numbers in cat -n format
    """

    file_path: str = Field(..., description="Path to the file to read. Relative paths resolve from the current working directory.")
    offset: Optional[int] = Field(
        None,
        description="The line number to start reading from. Only provide if the file is too large to read at once",
    )
    limit: Optional[int] = Field(
        None,
        description="The number of lines to read. Only provide if the file is too large to read at once.",
    )

    def run(self):
        try:
            resolved_path = resolve_input_path(self.file_path)
            abs_path = str(resolved_path)
            try:
                if hasattr(self, '_context') and self._context is not None:
                    read_files = self._context.get("read_files", set())
                    read_files.add(abs_path)
                    self._context.set("read_files", read_files)
            except (AttributeError, TypeError):
                # Context not available in standalone test mode
                pass

            if not resolved_path.exists():
                return f"Error: File does not exist: {resolved_path}"

            if not resolved_path.is_file():
                return f"Error: Path is not a file: {resolved_path}"

            mime_type, _ = mimetypes.guess_type(str(resolved_path))
            if mime_type and mime_type.startswith("image/"):
                return f"[IMAGE FILE: {resolved_path}]\nThis is an image file ({mime_type}). In a multimodal environment, the image content would be displayed visually."

            if str(resolved_path).endswith(".ipynb"):
                return "Error: This is a Jupyter notebook file. Please use a notebook-specific tool instead."

            try:
                with open(resolved_path, "r", encoding="utf-8") as file:
                    lines = file.readlines()
            except UnicodeDecodeError:
                try:
                    with open(resolved_path, "r", encoding="latin-1") as file:
                        lines = file.readlines()
                except UnicodeDecodeError:
                    return f"Error: Unable to decode file {resolved_path}. It may be a binary file."

            if not lines:
                return f"Warning: File exists but has empty contents: {self.file_path}"

            start_line = (self.offset - 1) if self.offset else 0
            start_line = max(0, start_line)

            if self.limit:
                end_line = start_line + self.limit
                selected_lines = lines[start_line:end_line]
            else:
                selected_lines = lines[start_line : start_line + 2000]

            result_lines = []
            for i, line in enumerate(selected_lines, start=start_line + 1):
                if len(line) > 2000:
                    line = line[:1997] + "...\n"
                result_lines.append(f"{i:>6}\t{line.rstrip()}\n")
            result = "".join(result_lines)

            total_lines = len(lines)
            lines_shown = len(selected_lines)

            if lines_shown < total_lines:
                if self.offset or self.limit:
                    result += f"\n[Truncated: showing lines {start_line + 1}-{start_line + lines_shown} of {total_lines} total lines]"
                else:
                    result += f"\n[Truncated: showing first {lines_shown} of {total_lines} total lines]"

            return result.rstrip()

        except PermissionError:
            return f"Error: Permission denied reading file: {self.file_path}"
        except Exception as e:
            return f"Error reading file: {str(e)}"


if __name__ == "__main__":
    # Test the tool with its own file
    current_file = __file__
    tool = ReadFile(file_path=current_file, limit=10)
    print("Reading first 10 lines:")
    print(tool.run())
