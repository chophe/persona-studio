from __future__ import annotations

from persona_studio.ui import interactive_mode
from persona_studio.ui.progress import live_progress, live_spinner


class TestLiveProgress:
    def test_disabled_yields_noop(self):
        with live_progress(3, "x", enabled=False) as advance:
            advance()
            advance()

    def test_zero_total_yields_noop(self):
        with live_progress(0, "x") as advance:
            advance()


class TestLiveSpinner:
    def test_disabled_yields_noop(self):
        with live_spinner("x", enabled=False) as refresh:
            refresh()


class TestInteractiveMode:
    def test_false_in_non_tty(self):
        assert interactive_mode() is False
