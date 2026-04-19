import argparse
import asyncio
import inspect
import os
import shlex
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import httpx
from rich.console import Console
from rich.markdown import Markdown
from agent_framework import Agent, AgentSession, InMemoryHistoryProvider
from agent_framework.openai import OpenAIChatCompletionClient
from dotenv import load_dotenv

from tools import all_tools, all_tool_functions
from training.chatml_logger import save_interaction

DEFAULT_PROMPT_PATH = Path("prompts/system_prompt.md")

_verbose = False
_console: "Console | None" = None


def vlog(msg: str) -> None:
    """Print a dim verbose line when --verbose is active."""
    if _verbose and _console is not None:
        _console.print(f"[dim]  ▸ {msg}[/dim]")


def load_local_env() -> None:
    """Load .env.local and map custom variable names to OpenAI-compatible names."""
    load_dotenv(".env.local")

    if os.getenv("API_URL") and not os.getenv("OPENAI_BASE_URL"):
        os.environ["OPENAI_BASE_URL"] = os.environ["API_URL"]

    if os.getenv("LLM_MODEL") and not os.getenv("OPENAI_MODEL"):
        os.environ["OPENAI_MODEL"] = os.environ["LLM_MODEL"]

    # Many local OpenAI-compatible hosts ignore API keys, but the client still expects one.
    if not os.getenv("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = "sk-local-dev"

    vlog(f"API URL  : {os.getenv('OPENAI_BASE_URL', '(not set)')}")
    vlog(f"Model    : {os.getenv('OPENAI_MODEL', '(not set)')}")
    vlog(f"API key  : {'(set)' if os.getenv('OPENAI_API_KEY') else '(not set)'}")


def validate_api_config() -> bool:
    """Validate that API_URL and model are configured. Return True if valid."""
    api_url = os.getenv("OPENAI_BASE_URL", "").strip()
    model = os.getenv("OPENAI_MODEL", "").strip()

    if not api_url:
        print("❌ API_URL not configured. Set API_URL in .env.local", file=sys.stderr)
        return False

    if not model:
        print("❌ LLM_MODEL not configured. Set LLM_MODEL in .env.local", file=sys.stderr)
        return False

    return True


def check_api_reachable() -> bool:
    """Check if the API endpoint is reachable and responding. Return True if healthy."""
    api_url = os.getenv("OPENAI_BASE_URL", "").strip()

    try:
        endpoint = urljoin(api_url.rstrip("/") + "/", "models")
        response = httpx.get(endpoint, timeout=5.0)

        if response.status_code >= 400:
            print(
                f"❌ API returned HTTP {response.status_code}. Is the server at {api_url} running?",
                file=sys.stderr,
            )
            return False

        print(f"✓ API reachable at {api_url}")
        return True

    except httpx.ConnectError:
        print(
            f"❌ Cannot connect to API at {api_url}. Is the server running?",
            file=sys.stderr,
        )
        return False
    except httpx.TimeoutException:
        print(f"❌ API at {api_url} is not responding (timeout).", file=sys.stderr)
        return False
    except httpx.HTTPError as exc:
        print(f"❌ API error: {exc}", file=sys.stderr)
        return False


def load_system_prompt() -> str:
    """Load the system prompt from SYSTEM_PROMPT_URL with a local fallback file."""
    prompt_url = os.getenv("SYSTEM_PROMPT_URL", "").strip()
    fallback_prompt = DEFAULT_PROMPT_PATH.read_text(encoding="utf-8")

    if not prompt_url:
        vlog(f"System prompt: loaded from local file {DEFAULT_PROMPT_PATH}")
        return fallback_prompt

    try:
        response = httpx.get(prompt_url, timeout=10.0)
        response.raise_for_status()
        prompt = response.text.strip()
        if prompt:
            vlog(f"System prompt: loaded from URL {prompt_url} ({len(prompt)} chars)")
            return prompt
        vlog(f"System prompt: URL returned empty body, falling back to {DEFAULT_PROMPT_PATH}")
        return fallback_prompt
    except httpx.HTTPError as exc:
        vlog(f"System prompt: URL fetch failed ({exc}), falling back to {DEFAULT_PROMPT_PATH}")
        return fallback_prompt


def create_agent() -> tuple[Agent, InMemoryHistoryProvider]:
    from db import get_db_path
    tools = all_tools()
    history = InMemoryHistoryProvider()
    vlog(f"DB path  : {get_db_path()}")
    vlog(f"Tools ({len(tools)}): {', '.join(t.name for t in tools)}")
    agent = Agent(
        client=OpenAIChatCompletionClient(
            model=os.environ["OPENAI_MODEL"],
            api_key=os.environ["OPENAI_API_KEY"],
        ),
        name="BuddyAgent",
        instructions=load_system_prompt(),
        tools=tools,
        context_providers=[history],
    )
    return agent, history


async def run_agent(agent: Agent, user_prompt: str, session: AgentSession | None = None) -> str:
    vlog(f"Sending prompt ({len(user_prompt)} chars) to agent… [session={session.session_id if session else 'none'}]")
    t0 = time.monotonic()
    try:
        result = await agent.run(user_prompt, session=session)
        elapsed = time.monotonic() - t0
        answer = str(result)
        vlog(f"Agent responded in {elapsed:.2f}s ({len(answer)} chars)")
        save_interaction(
            system=agent.default_options.get("instructions", ""),
            user=user_prompt,
            assistant=answer,
        )
        vlog("Interaction saved to training log")
        return answer
    except Exception as exc:
        # Surface helpful error if API returns unexpected response
        print(f"❌ Agent error: {exc}", file=sys.stderr)
        print(
            "\n💡 Troubleshooting tips:",
            file=sys.stderr,
        )
        print(
            "   1. Verify your local server is running at the API_URL in .env.local",
            file=sys.stderr,
        )
        print(
            "   2. Confirm the server supports OpenAI Chat Completions (/v1/chat/completions)",
            file=sys.stderr,
        )
        print(
            "   3. Try making a direct curl request to verify the API responds correctly",
            file=sys.stderr,
        )
        sys.exit(1)


_SLASH_HELP_TEXT = (
    "Type /help to list all tool commands.\n"
    "Usage: /tool_name [param=value ...]\n"
    "String values with spaces must be quoted: /create_note title=\"My note\" content=\"Some text\"\n"
    "Use 'exit' or 'quit' to end the session."
)


def _print_slash_help(console: "Console") -> None:
    tool_fns = all_tool_functions()
    lines = ["**Available slash commands:**\n"]
    for name, fn in sorted(tool_fns.items()):
        sig = inspect.signature(fn)
        params = []
        for pname, param in sig.parameters.items():
            annotation = param.annotation
            type_name = annotation.__name__ if hasattr(annotation, "__name__") else str(annotation)
            if param.default is inspect.Parameter.empty:
                params.append(f"{pname}: {type_name}")
            else:
                params.append(f"{pname}: {type_name} = {param.default!r}")
        param_str = ", ".join(params) if params else "(no args)"
        doc = (fn.__doc__ or "").strip().splitlines()[0] if fn.__doc__ else ""
        lines.append(f"- **/{name}** `{param_str}`  \n  {doc}")
    console.print(Markdown("\n".join(lines)))


def _coerce_arg(value: str, param: inspect.Parameter) -> object:
    """Coerce a string value to the parameter's annotated type."""
    annotation = param.annotation
    if annotation is inspect.Parameter.empty:
        return value
    origin = getattr(annotation, "__origin__", None)
    # Unwrap Annotated[T, ...] from pydantic/typing
    if origin is not None and hasattr(annotation, "__args__"):
        annotation = annotation.__args__[0]
    if annotation is int:
        return int(value)
    if annotation is float:
        return float(value)
    if annotation is bool:
        return value.lower() not in {"0", "false", "no", "off"}
    return value


def handle_slash_command(user_input: str, console: "Console") -> bool:
    """Detect and execute a slash command. Returns True if handled, False otherwise."""
    if not user_input.startswith("/"):
        return False

    parts = user_input[1:]  # strip leading /

    # Special built-ins
    if parts.strip().lower() in {"help", "?"}:
        _print_slash_help(console)
        return True

    # Parse: command_name [key=value ...]
    try:
        tokens = shlex.split(parts)
    except ValueError as exc:
        console.print(f"[red]Parse error:[/red] {exc}")
        return True

    if not tokens:
        return False

    command_name = tokens[0]
    tool_fns = all_tool_functions()

    if command_name not in tool_fns:
        console.print(
            f"[red]Unknown command:[/red] /{command_name}  "
            f"(type /help to see all commands)"
        )
        return True

    fn = tool_fns[command_name]
    sig = inspect.signature(fn)
    kwargs: dict = {}
    errors: list[str] = []

    for token in tokens[1:]:
        if "=" not in token:
            errors.append(f"  Expected key=value, got: {token!r}")
            continue
        key, _, raw_value = token.partition("=")
        key = key.strip()
        if key not in sig.parameters:
            errors.append(f"  Unknown parameter: {key!r}")
            continue
        try:
            kwargs[key] = _coerce_arg(raw_value, sig.parameters[key])
        except (ValueError, TypeError) as exc:
            errors.append(f"  Bad value for {key!r}: {exc}")

    if errors:
        console.print("[red]Argument error(s):[/red]\n" + "\n".join(errors))
        return True

    # Check for missing required parameters
    missing = [
        pname
        for pname, param in sig.parameters.items()
        if param.default is inspect.Parameter.empty and pname not in kwargs
    ]
    if missing:
        console.print(
            f"[red]Missing required parameter(s):[/red] {', '.join(missing)}\n"
            f"Usage: /{command_name} "
            + " ".join(f'{p}=<value>' for p in sig.parameters)
        )
        return True

    vlog(f"/{command_name} called with: {kwargs}")
    t0 = time.monotonic()
    try:
        result = fn(**kwargs)
        elapsed = time.monotonic() - t0
        vlog(f"/{command_name} returned in {elapsed:.3f}s")
        console.print(Markdown(f"```\n{result}\n```"))
    except Exception as exc:
        console.print(f"[red]Tool error:[/red] {exc}")

    return True


async def run_interactive_session(agent: Agent) -> None:
    """Run a text-based interactive chat loop with the agent."""
    console = Console()
    session = AgentSession()
    vlog(f"New session: {session.session_id}")
    console.print("Interactive session started. Type /help for tool commands, or 'exit' to quit.")

    while True:
        try:
            user_prompt = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting interactive session.")
            break

        if not user_prompt:
            continue

        if user_prompt.lower() in {"exit", "quit", "/exit", "/quit"}:
            print("Exiting interactive session.")
            break

        if handle_slash_command(user_prompt, console):
            continue

        print("Buddy> Processing...", flush=True)
        answer = await run_agent(agent, user_prompt, session=session)
        console.print("Buddy> ", end="")
        console.print(Markdown(answer))


async def main() -> None:
    global _verbose, _console
    parser = argparse.ArgumentParser(description="Run a basic Microsoft Agent Framework agent.")
    parser.add_argument(
        "prompt",
        nargs="?",
        default="What is the current system time in my local timezone?",
        help="Prompt to send to the agent.",
    )
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Start a text-based interactive session instead of a single prompt run.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print verbose internal state (config, tool calls, timings).",
    )
    args = parser.parse_args()

    _console = Console()
    _verbose = args.verbose

    vlog("Verbose mode enabled")
    load_local_env()

    # Validate configuration and connectivity before attempting agent run
    if not validate_api_config():
        sys.exit(1)

    if not check_api_reachable():
        sys.exit(1)

    agent, _ = create_agent()

    if args.interactive:
        await run_interactive_session(agent)
        return

    print("Buddy> Processing...", flush=True)
    answer = await run_agent(agent, args.prompt)
    console = Console()
    console.print(Markdown(answer))


if __name__ == "__main__":
    asyncio.run(main())

