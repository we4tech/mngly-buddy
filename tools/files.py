from pathlib import Path
from typing import Annotated

from agent_framework import tool
from pydantic import Field

PROJECT_DIR = Path(__file__).resolve().parents[1]


@tool(approval_mode="never_require")
def get_file_content(
    path: Annotated[
        str,
        Field(description="Path to the file to read, relative to the project directory."),
    ],
) -> str:
    """Read the contents of a file inside the project directory."""
    target = (PROJECT_DIR / path).resolve()

    if not target.is_relative_to(PROJECT_DIR):
        return f"Access denied: '{path}' is outside the project directory."

    if not target.exists():
        return f"File not found: '{path}'."

    if not target.is_file():
        return f"'{path}' is not a file."

    return target.read_text(encoding="utf-8")
