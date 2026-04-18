from datetime import datetime
from typing import Annotated

from agent_framework import tool
from pydantic import Field


@tool(approval_mode="never_require")
def get_current_system_time(
    format_string: Annotated[
        str,
        Field(description="Optional datetime format string compatible with Python strftime."),
    ] = "%Y-%m-%d %H:%M:%S %Z",
) -> str:
    """Return the current local system time."""
    now = datetime.now().astimezone()
    return now.strftime(format_string)
