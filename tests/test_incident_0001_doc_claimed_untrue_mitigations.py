"""MAESTRO-DEPUTY.md marked two failure modes "well-mitigated" and neither was in the code.

Found 2026-08-23 by auditing the document against maestro.py. The document said SQLite
WAL mode was on and that the Telegram bridge had a three-try circuit breaker. Grep found
neither. A document that claims a mitigation is worse than one that admits the gap: the
gap gets planned around, the claim gets believed.

Rung 4, incident tests. These assert the rule the document states, not the shape of the
code that satisfies it, so a rewrite of either mechanism keeps them honest.
"""
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import maestro  # noqa: E402


def test_experience_graph_is_in_wal_mode():
    """Every connection the code opens is WAL, and WAL sticks to the file.

    Two angles on purpose. The first says the helper sets it; the second opens the same
    file with a connection that knows nothing about maestro, which is what a restore,
    a backup or `sqlite3` on the command line will do.
    """
    with tempfile.TemporaryDirectory() as d:
        graph = maestro.ExperienceGraph(os.path.join(d, "sub", "graph.db"))

        with graph._connect() as conn:
            assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
            # The half that actually bites: busy_timeout is per-connection, defaults to
            # 0, and a zero timeout turns any overlap into `database is locked`.
            assert conn.execute("PRAGMA busy_timeout").fetchone()[0] >= 30000

        outside = sqlite3.connect(graph.db_path)
        assert outside.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        outside.close()


def test_telegram_bridge_tries_three_times_then_opens_the_circuit(monkeypatch):
    """Three tries per message. One exhausted message stops the dialling."""
    calls = {"n": 0}

    def refuse(*args, **kwargs):
        calls["n"] += 1
        raise OSError("connection refused")

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    monkeypatch.setattr(maestro.time, "sleep", lambda _: None)

    with tempfile.TemporaryDirectory() as d:
        graph = maestro.ExperienceGraph(os.path.join(d, "graph.db"))
        bridge = maestro.TelegramBridge("token", "chat", graph)

        assert bridge.send("first") is False
        assert calls["n"] == maestro.TelegramBridge.SEND_TRIES

        # Circuit open: the second message must not reach the network at all.
        assert bridge.send("second") is False
        assert calls["n"] == maestro.TelegramBridge.SEND_TRIES


def test_telegram_circuit_closes_on_the_clock_and_success_resets_it(monkeypatch):
    """An open circuit that never closes is an outage the estate inflicts on itself."""
    import urllib.request

    def refuse(*args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    monkeypatch.setattr(maestro.time, "sleep", lambda _: None)

    with tempfile.TemporaryDirectory() as d:
        graph = maestro.ExperienceGraph(os.path.join(d, "graph.db"))
        bridge = maestro.TelegramBridge("token", "chat", graph)
        bridge.send("first")
        assert bridge._circuit_is_open()

        bridge._circuit_opened_at -= bridge.BREAKER_COOLDOWN_SECONDS + 1
        assert not bridge._circuit_is_open()

        class Answered:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: Answered())
        assert bridge.send("after cooldown") is True
        assert bridge._consecutive_failures == 0
