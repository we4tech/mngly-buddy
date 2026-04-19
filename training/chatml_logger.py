"""Save agent interactions as ChatML JSONL for fine-tuning."""

import json
import os
from datetime import date
from pathlib import Path

TRAIN_DIR = Path(__file__).resolve().parents[1] / "data" / "data-to-train"


def _get_train_file() -> Path:
    TRAIN_DIR.mkdir(parents=True, exist_ok=True)
    filename = os.getenv("TRAIN_FILE", f"interactions-{date.today().isoformat()}.jsonl")
    return TRAIN_DIR / filename


def save_interaction(system: str, user: str, assistant: str) -> None:
    """Append one ChatML record to the daily JSONL training file."""
    record = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ]
    }
    with _get_train_file().open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
