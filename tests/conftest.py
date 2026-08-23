"""Keep the suite out of the founder's real state.

`TelegramBridge.FENCE_PATH` defaults to ~/.maestro/alert_fence.json, which is live: it is
what stops the running daemon telling him the same thing every three minutes. A test that
writes to it silences a real alert, and a test that reads it passes or fails depending on
what the daemon said this morning. Measured 2026-08-23: the suite passed once, wrote two
entries there, and failed on the second run against its own leftovers.

One autouse fixture, so no test has to remember.
"""
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import maestro  # noqa: E402


@pytest.fixture(autouse=True)
def fence_in_a_tmpdir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        maestro.TelegramBridge, "FENCE_PATH", str(tmp_path / "alert_fence.json")
    )


def pytest_configure(config):
    """Stop the suite writing into the daemon's own log.

    `logging.basicConfig` at import time attaches a FileHandler to
    ~/.maestro/maestro.log, which is the running daemon's log. A test run put 14
    lines in it about temporary pytest paths, and the next person reading that
    file to find out what maestro did is reading test fixtures.
    """
    for handler in list(maestro.logger.handlers) + list(logging.root.handlers):
        if isinstance(handler, logging.FileHandler):
            logging.root.removeHandler(handler)
            maestro.logger.removeHandler(handler)
