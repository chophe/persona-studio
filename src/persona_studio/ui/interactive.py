from __future__ import annotations

import sys
from pathlib import Path

import questionary
from rich.console import Console

from persona_studio.language import LABELS

console = Console()


def interactive_mode() -> bool:
    """Detect whether attached stdin supports interactive prompting."""
    try:
        return bool(console.is_interactive and sys.stdin.isatty())
    except Exception:
        return False


def pick_lang(current: str | None) -> str:
    value = current or "fa"
    choice = questionary.select(
        "Result language",
        choices=[
            questionary.Choice(title=LABELS[code], value=code) for code in LABELS
        ],
        default=value,
    ).unsafe_ask()
    return str(choice)


def pick_folder(message: str, default: Path | None = None) -> Path:
    result = questionary.path(
        message, default=str(default) if default else ""
    ).unsafe_ask()
    return Path(str(result))


def confirm(message: str, default: bool = True) -> bool:
    return bool(questionary.confirm(message, default=default).unsafe_ask())
