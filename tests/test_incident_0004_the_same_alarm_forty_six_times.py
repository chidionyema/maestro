"""One Stripe finding wrote 46 needs_human episodes in 29 hours and never closed.

Measured 2026-08-23 on the live ledger: the same credential-leak finding produced 46
crisis_escalation/needs_human episodes between 2026-08-22 18:04 and 2026-08-23 23:00,
one per pass, because `_do_crisis` and `_do_report` logged every sighting as if it were
news. The message fence (incident 0003) spaced the Telegram repeats, but the ledger
still filled with copies, and when the founder scrubbed the key nothing ever said the
problem had ended. His words, 2026-08-23: "i need a nechanin to reduce alarns".

The rule: a problem alarms when it appears, is counted while it stands, speaks again
after a day, and closes out loud the moment it stops being sensed. The mechanism is
the `open_alarms` ledger; the fence stays what it was, a spacing device for messages.

Rung 4, incident tests, named for the count.
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import maestro  # noqa: E402

from test_incident_0003_the_same_alert_every_three_minutes import _bridge  # noqa: E402

STRIPE = {
    "id": "credential-leak-stripe-live-key",
    "description": "Stripe LIVE key readable in ~/.zsh_history",
    "severity": "P0",
    "lane": "security",
}


def _maestro(tmp_path, monkeypatch):
    monkeypatch.setattr(maestro.Config, "DB_PATH", str(tmp_path / "graph.db"))
    monkeypatch.setattr(maestro.Config, "INTENT_LOG_DIR", str(tmp_path / "intents"))
    m = maestro.Maestro()
    m.bridge = _bridge(tmp_path, monkeypatch)
    return m


def _episodes(m, action):
    with m.db._connect() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM episodes WHERE action = ?", (action,)
        ).fetchone()[0]


def _alarm_row(m):
    with m.db._connect() as conn:
        return conn.execute(
            "SELECT finding_id, times_seen FROM open_alarms"
        ).fetchall()


def test_incident_0004_a_standing_p0_is_one_episode_not_forty_six(tmp_path, monkeypatch):
    m = _maestro(tmp_path, monkeypatch)
    for _ in range(46):
        m.daily_findings = [dict(STRIPE)]
        m._do_crisis()
    assert _episodes(m, "crisis_escalation") == 1
    assert _alarm_row(m) == [("credential-leak-stripe-live-key", 46)]


def test_incident_0004_a_new_problem_is_not_silenced_by_a_standing_one(tmp_path, monkeypatch):
    """Suppression is per problem. A second P0 arriving later still pages."""
    m = _maestro(tmp_path, monkeypatch)
    m.daily_findings = [dict(STRIPE)]
    m._do_crisis()
    disk = {"id": "disk-critical", "description": "Disk at 96%",
            "severity": "P0", "lane": "estate"}
    m.daily_findings = [dict(STRIPE), disk]
    m._do_crisis()
    assert _episodes(m, "crisis_escalation") == 2
    latest = m.bridge.delivered[-1]
    assert "Disk at 96%" in latest
    assert "Stripe" not in latest, "the standing problem must not ride along as news"


def test_incident_0004_a_cleared_problem_closes_its_alarm_out_loud(tmp_path, monkeypatch):
    """The founder scrubbed the key; the next sense pass must say so, once."""
    m = _maestro(tmp_path, monkeypatch)
    m.daily_findings = [dict(STRIPE)]
    m._do_crisis()
    monkeypatch.setattr(m.sensors, "sense", lambda: [])
    m._do_sense()
    assert _alarm_row(m) == []
    assert _episodes(m, "alarm_cleared") == 1
    assert any("Cleared" in msg for msg in m.bridge.delivered)
    m._do_sense()
    assert _episodes(m, "alarm_cleared") == 1, "a close is said once, not per pass"


def test_incident_0004_a_standing_problem_speaks_again_after_a_day(tmp_path, monkeypatch):
    """Suppression must not become silence. 24 hours later it is news again."""
    m = _maestro(tmp_path, monkeypatch)
    m.daily_findings = [dict(STRIPE)]
    m._do_crisis()
    yesterday = (datetime.utcnow() - timedelta(hours=25)).isoformat()
    with m.db._connect() as conn:
        conn.execute("UPDATE open_alarms SET last_alerted = ?", (yesterday,))
    m.daily_findings = [dict(STRIPE)]
    m._do_crisis()
    assert _episodes(m, "crisis_escalation") == 2


def test_incident_0004_needs_human_repeats_are_counted_not_reescalated(tmp_path, monkeypatch):
    m = _maestro(tmp_path, monkeypatch)
    finding = {"id": "estate-audit-abc123", "description": "9 criticals standing",
               "severity": "P1", "lane": "estate"}
    for _ in range(5):
        m.daily_needs_human = [dict(finding)]
        m.daily_resolved = []
        m._do_report()
    assert _episodes(m, "escalated") == 1
    assert _alarm_row(m) == [("estate-audit-abc123", 5)]
