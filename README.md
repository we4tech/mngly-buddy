# mngly-buddy

Basic Microsoft Agent Framework sample wired to an OpenAI-compatible endpoint.

## What this includes

- A basic `Agent` built with `agent-framework`
- dotenv loading from `.env.local`
- Variable mapping from your custom names:
  - `API_URL` -> `OPENAI_BASE_URL`
  - `LLM_MODEL` -> `OPENAI_MODEL`
- External system prompt loading via `SYSTEM_PROMPT_URL` with local fallback in `prompts/system_prompt.md`
- A custom tool: `get_current_system_time` in `tools/date.py`
- A calendar tool: `search_local_calendar` in `tools/calendar.py`
- Notes tools in `tools/notes.py`:
  - `create_note`
  - `search_notes`
  - `read_note`
- Text-based interactive mode for chatting with the agent
- Minimal tests for local utility behavior

## Setup

1. Create a virtual environment and install dependencies.
2. Copy `.env.example` to `.env.local` and adjust values.

```bash
cd /Users/hossainkhan/projects/mngly-buddy
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env.local
```

Or use:

```bash
cd /Users/hossainkhan/projects/mngly-buddy
make setup
cp .env.example .env.local
```

## Check API Health

Use this before running the agent to confirm your local OpenAI-compatible host is reachable.

```bash
cd /Users/hossainkhan/projects/mngly-buddy
source .venv/bin/activate
python scripts/check_api.py
```

Or use:

```bash
cd /Users/hossainkhan/projects/mngly-buddy
make check
```

## Run

```bash
cd /Users/hossainkhan/projects/mngly-buddy
source .venv/bin/activate
python agent_app.py "What time is it right now?"
```

Or use:

```bash
cd /Users/hossainkhan/projects/mngly-buddy
make run
```

## Interactive Session

Start a text-based chat session and send multiple prompts without restarting the app.

```bash
cd /Users/hossainkhan/projects/mngly-buddy
source .venv/bin/activate
python agent_app.py --interactive
```

Type `exit` or `quit` to end the session.

## Test

```bash
cd /Users/hossainkhan/projects/mngly-buddy
source .venv/bin/activate
pytest
```

Or use:

```bash
cd /Users/hossainkhan/projects/mngly-buddy
make test
```

## Cleanup

Remove local temporary artifacts:

```bash
cd /Users/hossainkhan/projects/mngly-buddy
make clean-artifacts
```

## Notes

- `OPENAI_API_KEY` is still required by most clients even when your local server ignores auth.
- If `SYSTEM_PROMPT_URL` is unreachable, the app falls back to `prompts/system_prompt.md`.

## Calendar

The `search_local_calendar` tool uses the native macOS EventKit API via PyObjC.
This works with iCloud, Google, Exchange, and all other calendar accounts synced to Calendar.app.

On first run, macOS will show a permission prompt. Allow access when asked.
If you previously denied it, re-enable in System Settings -> Privacy & Security -> Calendars.


