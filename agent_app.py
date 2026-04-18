import argparse
import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import urljoin

import httpx
from agent_framework import Agent
from agent_framework.openai import OpenAIChatCompletionClient
from dotenv import load_dotenv

from tools import all_tools
from tools.date import get_current_system_time

DEFAULT_PROMPT_PATH = Path("prompts/system_prompt.md")


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
        return fallback_prompt

    try:
        response = httpx.get(prompt_url, timeout=10.0)
        response.raise_for_status()
        prompt = response.text.strip()
        return prompt or fallback_prompt
    except httpx.HTTPError:
        return fallback_prompt


def create_agent() -> Agent:
    return Agent(
        client=OpenAIChatCompletionClient(
            model=os.environ["OPENAI_MODEL"],
            api_key=os.environ["OPENAI_API_KEY"],
        ),
        name="BuddyAgent",
        instructions=load_system_prompt(),
        tools=all_tools(),
    )


async def run_agent(agent: Agent, user_prompt: str) -> str:

    try:
        result = await agent.run(user_prompt)
        return str(result)
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


async def run_interactive_session(agent: Agent) -> None:
    """Run a text-based interactive chat loop with the agent."""
    print("Interactive session started. Type 'exit' or 'quit' to end.")

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

        print("Buddy> Processing...", flush=True)
        answer = await run_agent(agent, user_prompt)
        print(f"Buddy> {answer}")


async def main() -> None:
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
    args = parser.parse_args()

    load_local_env()

    # Validate configuration and connectivity before attempting agent run
    if not validate_api_config():
        sys.exit(1)

    if not check_api_reachable():
        sys.exit(1)

    agent = create_agent()

    if args.interactive:
        await run_interactive_session(agent)
        return

    print("Buddy> Processing...", flush=True)
    answer = await run_agent(agent, args.prompt)
    print(answer)


if __name__ == "__main__":
    asyncio.run(main())

