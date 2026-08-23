"""Teaching maestro to see would have turned it into a pager loop.

Found 2026-08-23, before it could bite, while fixing incident 0002. The state machine
advances one state per 60-second tick, so IDLE -> SENSE -> CRISIS is about three minutes,
and `_do_crisis` clears `daily_findings` and returns to IDLE without recording that it
said anything. Eight standing criticals in the estate audit would therefore have sent the
founder the same crisis message roughly twenty times an hour, indefinitely.

That is the failure the estate has already paid for once: the old coordinator fired
`escalate` 18 times, delivered 0 notifications, and nobody read a word of it. An alert
that repeats is an alert that gets muted, and a muted channel is worse than no channel
because the next real one arrives on it.

Rung 4, incident tests. They assert the rule -- one message per situation until it
changes or the cooldown lapses, and never at the cost of losing an alert.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import maestro  # noqa: E402


class Sent(maestro.TelegramBridge):
    """A bridge that reaches a list instead of Telegram, and counts the tries."""

    def __init__(self, fence_path):
        super().__init__("token", "chat", None)
        self.FENCE_PATH = fence_path
        self.delivered = []

    def _post(self, message, key):
        self.delivered.append(message)
        self._record_said(key)
        return True


def _bridge(tmp_path, monkeypatch):
    bridge = Sent(str(tmp_path / "fence.json"))

    def fake_send(message, priority=maestro.Priority.P2, dedup_key=None):
        key = dedup_key or "text:" + maestro.hashlib.sha256(message.encode()).hexdigest()[:16]
        if bridge._already_said(key):
            return True
        return bridge._post(message, key)

    monkeypatch.setattr(bridge, "send", fake_send)
    return bridge


def test_the_same_crisis_is_told_once_not_every_tick(tmp_path, monkeypatch):
    bridge = _bridge(tmp_path, monkeypatch)
    for _ in range(20):
        bridge.send("CRISIS: 8 P0 findings", maestro.Priority.P0, dedup_key="crisis:same")
    assert len(bridge.delivered) == 1, bridge.delivered


def test_a_changed_situation_is_a_new_alert(tmp_path, monkeypatch):
    """The fence must not silence news. A different set of findings gets through."""
    bridge = _bridge(tmp_path, monkeypatch)
    bridge.send("CRISIS: 8 P0", maestro.Priority.P0, dedup_key="crisis:eight")
    bridge.send("CRISIS: 9 P0", maestro.Priority.P0, dedup_key="crisis:nine")
    assert len(bridge.delivered) == 2


def test_the_cooldown_lets_a_standing_problem_speak_again(tmp_path, monkeypatch):
    """Silence forever is not the goal. A problem still there tomorrow says so again."""
    bridge = _bridge(tmp_path, monkeypatch)
    bridge.send("CRISIS", maestro.Priority.P0, dedup_key="crisis:standing")
    monkeypatch.setattr(bridge, "REPEAT_COOLDOWN_SECONDS", 0.0)
    bridge.send("CRISIS", maestro.Priority.P0, dedup_key="crisis:standing")
    assert len(bridge.delivered) == 2


def test_a_digest_whose_counters_moved_is_still_the_same_digest(tmp_path, monkeypatch):
    """The stats line carries episode and spend counters that tick every minute.

    Keying on rendered text would defeat the fence entirely, because the text of an
    unchanged estate is never twice the same.
    """
    bridge = _bridge(tmp_path, monkeypatch)
    needs = [{"id": "estate-audit-aaa", "description": "one"},
             {"id": "estate-audit-bbb", "description": "two"}]
    for episodes in (10, 11, 12):
        stats = {"total_episodes": episodes, "total_shapes": 3,
                 "total_skills": 4, "today_spend_usd": 0.0}
        maestro.TelegramBridge.send_digest(bridge, stats, [], needs)
    assert len(bridge.delivered) == 1, bridge.delivered


def test_a_message_that_never_arrived_is_not_recorded_as_said(tmp_path):
    """The fence is written on delivery only.

    Recording an attempt would let one Telegram outage swallow a crisis for six hours,
    which trades a duplicate message for a lost one -- the wrong way round.
    """
    bridge = Sent(str(tmp_path / "fence.json"))
    bridge._consecutive_failures = bridge.BREAKER_THRESHOLD
    bridge._circuit_opened_at = maestro.time.time()
    assert bridge._circuit_is_open()
    assert bridge.send("CRISIS", maestro.Priority.P0, dedup_key="crisis:dropped") is False
    assert not os.path.exists(bridge.FENCE_PATH), \
        "a dropped message must be retried, so it must not be fenced"


def test_a_corrupt_fence_never_swallows_an_alert(tmp_path, monkeypatch):
    """Fail open. A broken fence costs a duplicate; a closed one costs the alert."""
    fence = tmp_path / "fence.json"
    fence.write_text("{ not json")
    bridge = _bridge(tmp_path, monkeypatch)
    bridge.FENCE_PATH = str(fence)
    bridge.send("CRISIS", maestro.Priority.P0, dedup_key="crisis:anything")
    assert len(bridge.delivered) == 1
