import argparse
import asyncio
import inspect
import os
import random
import re
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import httpx
from rich.console import Console
from rich.markdown import Markdown
from agent_framework import Agent, AgentSession, FunctionInvocationContext, FunctionMiddleware, MCPStdioTool
from agent_framework.openai import OpenAIChatCompletionClient
from dotenv import load_dotenv

from data_access.redis_history import RedisHistoryProvider

from tools import all_tool_functions
from training.chatml_logger import save_interaction

MCP_SERVER_PATH = Path(__file__).parent / "mcp_server.py"

DEFAULT_PROMPT_PATH = Path("prompts/system_prompt.md")

_verbose = False
_speak = False
_mic = False
_console: "Console | None" = None

_WORKING_PHRASES = [
    "Working on it, give me a few seconds.",
    "Ooh, good one! Let me think.",
    "On it! Back in a flash.",
    "Great question! Give me just a moment.",
    "Let me look that up for you!",
    "Hmm, let me figure this out.",
    "One moment, I am on the case!",
    "You got it! Just a tiny bit.",
    "Thinking really hard right now.",
    "Hold on, I am checking for you!",
    "Almost there, just a second.",
    "Sure thing! Searching now.",
    "Let me find the answer for you.",
    "Okay okay, give me just a sec.",
    "On my way to finding that out!",
]


def vlog(msg: str) -> None:
    """Print a dim verbose line when --verbose is active."""
    if _verbose and _console is not None:
        _console.print(f"[dim]  ▸ {msg}[/dim]")


def _strip_markdown(text: str) -> str:
    """Remove common markdown syntax for cleaner TTS output."""
    # Remove fenced code blocks
    text = re.sub(r"```[\s\S]*?```", "", text)
    # Remove inline code
    text = re.sub(r"`[^`]*`", "", text)
    # Remove ATX headers
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Remove bold / italic markers
    text = re.sub(r"\*{1,3}([^*]*)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,3}([^_]*)_{1,3}", r"\1", text)
    # Remove markdown links, keep link text
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def speak_text(text: str) -> None:
    """Speak *text* aloud using the macOS 'say' command with the Junior (kid) voice.

    Speech stops immediately if Enter is pressed while speaking.
    """
    import threading

    clean = _strip_markdown(text)
    if not clean:
        return

    proc = subprocess.Popen(
        ["say", clean],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    def _enter_watcher() -> None:
        try:
            sys.stdin.readline()
        except (EOFError, OSError):
            pass
        proc.terminate()

    watcher = threading.Thread(target=_enter_watcher, daemon=True)
    watcher.start()
    proc.wait()


def speak_async(text: str) -> "subprocess.Popen[bytes]":
    """Start speaking *text* in the background; returns the Popen handle.

    Call ``proc.terminate()`` on the returned handle to stop playback early.
    """
    clean = _strip_markdown(text)
    if not clean:
        return subprocess.Popen(["true"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return subprocess.Popen(
        ["say", clean],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def listen_voice_input() -> str | None:
    """Record a spoken phrase and return its transcription, or None on failure.

    Recording stops automatically after 2 seconds of silence, when the
    phrase_time_limit (60 s) is reached, or immediately when Enter is pressed.
    """
    import threading
    import speech_recognition as sr  # lazy import — only needed when --mic is active

    recognizer = sr.Recognizer()
    recognizer.pause_threshold = 2.0      # stop after 2 s of silence
    recognizer.non_speaking_duration = 1.0

    microphone = sr.Microphone()

    # Calibrate for ambient noise before opening the background listener
    with microphone as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.5)

    captured: list[sr.AudioData] = []
    done_event = threading.Event()

    def _on_phrase(_recognizer: sr.Recognizer, audio: sr.AudioData) -> None:
        """Called by listen_in_background when a complete phrase is detected."""
        captured.append(audio)
        done_event.set()

    # Start background listener — stops on silence (pause_threshold) or phrase_time_limit
    stop_fn = recognizer.listen_in_background(microphone, _on_phrase, phrase_time_limit=60)

    print("You> [🎤 listening… speak, then pause — or press Enter to stop] ", end="", flush=True)

    def _enter_watcher() -> None:
        """Signal done_event as soon as Enter is pressed."""
        try:
            sys.stdin.readline()
        except (EOFError, OSError):
            pass
        done_event.set()

    threading.Thread(target=_enter_watcher, daemon=True).start()

    done_event.wait()          # unblocked by speech-end OR Enter key
    stop_fn(wait_for_stop=False)

    if not captured:
        print("(stopped before speech was captured)")
        return None

    try:
        text = recognizer.recognize_google(captured[0])  # type: ignore[attr-defined]
        print(text)
        return text
    except sr.UnknownValueError:
        print("(could not understand audio)")
        return None
    except sr.RequestError as exc:
        print(f"(speech recognition error: {exc})")
        return None


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


def create_mcp_tool() -> MCPStdioTool:
    """Create the MCPStdioTool that launches the buddy-tools MCP server."""
    return MCPStdioTool(
        name="buddy-tools",
        command=sys.executable,
        args=[str(MCP_SERVER_PATH)],
        approval_mode="never_require",
    )


def create_agent(mcp_tool: MCPStdioTool) -> tuple[Agent, RedisHistoryProvider]:
    from db import get_redis_url

    class ToolCallLogger(FunctionMiddleware):
        async def process(self, context: FunctionInvocationContext, call_next) -> None:
            print(f"  🔧 [{context.function.name}]", flush=True)
            await call_next()

    history = RedisHistoryProvider()
    vlog(f"Redis URL: {get_redis_url()}")
    vlog("History: Redis-backed (buddy:history:<session_id>)")
    vlog("Tools: buddy-tools MCP server")
    agent = Agent(
        client=OpenAIChatCompletionClient(
            model=os.environ["OPENAI_MODEL"],
            api_key=os.environ["OPENAI_API_KEY"],
        ),
        name="BuddyAgent",
        instructions=load_system_prompt(),
        tools=mcp_tool,
        context_providers=[history],
        default_options={
            "allow_multiple_tool_calls": True
        },
        middleware=[ToolCallLogger()],
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
    if _mic:
        console.print("Interactive session started (voice input). Say 'exit' or 'quit' to stop.")
    else:
        console.print("Interactive session started. Type /help for tool commands, or 'exit' to quit.")

    while True:
        try:
            if _mic:
                user_prompt_raw = listen_voice_input()
                if user_prompt_raw is None:
                    continue
                user_prompt = user_prompt_raw.strip()
            else:
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

        print("Buddy> Processing… (Ctrl+C to cancel)", flush=True)
        working_proc = speak_async(random.choice(_WORKING_PHRASES)) if _speak else None
        loop = asyncio.get_running_loop()
        task = asyncio.create_task(run_agent(agent, user_prompt, session=session))

        def _on_sigint() -> None:
            task.cancel()

        loop.add_signal_handler(signal.SIGINT, _on_sigint)
        try:
            answer = await task
        except asyncio.CancelledError:
            if working_proc:
                working_proc.terminate()
            console.print("\n[yellow]⚠  Request cancelled.[/yellow]")
            continue
        finally:
            loop.remove_signal_handler(signal.SIGINT)
            if working_proc:
                working_proc.terminate()

        console.print("Buddy> ", end="")
        console.print(Markdown(answer))
        if _speak:
            speak_text(answer)


async def main() -> None:
    global _verbose, _speak, _mic, _console
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
    parser.add_argument(
        "-s",
        "--speak",
        action="store_true",
        help="Speak agent responses aloud using the Junior (kid) voice via macOS 'say'.",
    )
    parser.add_argument(
        "-m",
        "--mic",
        action="store_true",
        help="Use microphone voice input instead of keyboard (interactive mode only).",
    )
    args = parser.parse_args()

    _console = Console()
    _verbose = args.verbose
    _speak = args.speak
    _mic = args.mic

    vlog("Verbose mode enabled")
    load_local_env()

    # Validate configuration and connectivity before attempting agent run
    if not validate_api_config():
        sys.exit(1)

    if not check_api_reachable():
        sys.exit(1)

    mcp_tool = create_mcp_tool()
    async with mcp_tool:
        agent, _ = create_agent(mcp_tool)

        if args.interactive:
            await run_interactive_session(agent)
            return

        print("Buddy> Processing...", flush=True)
        answer = await run_agent(agent, args.prompt)
        console = Console()
        console.print(Markdown(answer))
        if _speak:
            speak_text(answer)


if __name__ == "__main__":
    asyncio.run(main())

