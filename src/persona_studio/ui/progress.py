from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, Iterator

from alive_progress import alive_bar


@contextmanager
def live_progress(total: int, title: str, enabled: bool = True) -> Iterator[Callable[[], None]]:
    """Yield a callable that advances an animated progress bar by one step.

    Falls back to a no-op when progress is disabled or the item count is empty.
    """
    if not enabled or total <= 0:
        yield lambda: None
        return
    with alive_bar(total, title=title, bar="smooth", spinner="dots", theme="smooth") as bar:
        yield bar


@contextmanager
def live_spinner(title: str, enabled: bool = True) -> Iterator[Callable[[], None]]:
    """Yield a callable that refreshes an indeterminate spinner."""
    if not enabled:
        yield lambda: None
        return
    bar = alive_bar(None, title=title, spinner="dots", theme="smooth")
    bar.__enter__()
    try:
        yield bar
    finally:
        bar.__exit__(None, None, None)
