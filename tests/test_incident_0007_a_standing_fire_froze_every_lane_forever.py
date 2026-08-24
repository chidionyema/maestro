"""maestro ran for days, alerted nobody new, and did no work at all.

Measured on the live loop 2026-08-24: the estate audit stood at 5 critical rows and
41 findings. `_do_sense` set crisis_mode on ANY P0 and jumped to CRISIS; `_do_crisis`
alerted, then handed back to IDLE; `_do_idle` saw crisis_mode and went straight back
to CRISIS. So every pass was SENSE -> CRISIS -> IDLE and ORIENT, DECIDE, ACT, VERIFY
and REPORT were never once reached. The alarm ledger (incident 0004) suppressed the
paging, so the founder saw silence while 36 non-critical findings got no work whatever.

Two of the five P0s cannot be cleared by maestro or by any agent: this machine's load
average, which is the founder's own eight sessions, and a detached HEAD in another
session's working tree. An estate that always holds one standing problem therefore
froze the loop permanently, by construction. His words: "its not until it is providing
value, a hernes aget icant use is not operattional".

The rule: only NEWS freezes the estate. A P0 whose alarm is already open has already
reached him, so it stays open in the ledger and gets counted, and the loop carries on
working everything else. A guard that refuses correct work is an outage (LAW 38), and
a permanent freeze is a siren with no fire drill behind it.

Rung 4, incident tests, named for the failure.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import maestro  # noqa: E402

from test_incident_0003_the_same_alert_every_three_minutes import _bridge  # noqa: E402

LOAD = {
    "id": "machine-load-average",
    "description": "Load average (1 / 5 / 15 min): 67.12 / 129.66 / 111.18",
    "severity": "P0",
    "lane": "estate",
}
DETACHED = {
    "id": "access-detached-head",
    "description": "Shared checkout is in detached HEAD: 17 modified files",
    "severity": "P0",
    "lane": "estate",
}
ROUTINE = {
    "id": "sched-jobs-never-loaded",
    "description": "launchd jobs installed but never loaded: 3",
    "severity": "P2",
    "lane": "estate",
}


def _maestro(tmp_path, monkeypatch):
    monkeypatch.setattr(maestro.Config, "DB_PATH", str(tmp_path / "graph.db"))
    monkeypatch.setattr(maestro.Config, "INTENT_LOG_DIR", str(tmp_path / "intents"))
    m = maestro.Maestro()
    m.bridge = _bridge(tmp_path, monkeypatch)
    return m


def _sensing(m, monkeypatch, findings):
    monkeypatch.setattr(m.sensors, "sense", lambda: [dict(f) for f in findings])


def test_incident_0007_a_new_p0_still_freezes_the_estate(tmp_path, monkeypatch):
    """The refusal half. First sighting is news and must stop everything."""
    m = _maestro(tmp_path, monkeypatch)
    _sensing(m, monkeypatch, [LOAD, ROUTINE])
    m._do_sense()
    assert m.state == maestro.State.CRISIS
    assert m.crisis_mode is True


def test_incident_0007_a_standing_p0_does_not_freeze_the_next_pass(tmp_path, monkeypatch):
    """The pass half, and the one that was missing. Same fire, second pass, work resumes."""
    m = _maestro(tmp_path, monkeypatch)
    _sensing(m, monkeypatch, [LOAD, ROUTINE])
    m._do_sense()
    m._do_crisis()
    assert m.crisis_mode is False

    m.daily_findings = []
    _sensing(m, monkeypatch, [LOAD, ROUTINE])
    m._do_sense()
    assert m.state == maestro.State.ORIENT, "a standing fire must not freeze the loop again"
    assert m.crisis_mode is False


def test_incident_0007_a_fresh_p0_arriving_beside_a_standing_one_still_freezes(tmp_path, monkeypatch):
    """Suppression is per problem, so a second fire is still news."""
    m = _maestro(tmp_path, monkeypatch)
    _sensing(m, monkeypatch, [LOAD])
    m._do_sense()
    m._do_crisis()

    m.daily_findings = []
    _sensing(m, monkeypatch, [LOAD, DETACHED])
    m._do_sense()
    assert m.state == maestro.State.CRISIS
    assert m.crisis_mode is True


def test_incident_0007_the_sighting_is_counted_once_per_pass(tmp_path, monkeypatch):
    """SENSE asks the ledger and CRISIS reads the answer. Asking twice double-counts.

    times_seen is what the eventual cleared episode uses to say how long a problem
    stood and how often it was seen, so an inflated count is a false receipt.
    """
    m = _maestro(tmp_path, monkeypatch)
    for _ in range(3):
        m.daily_findings = []
        _sensing(m, monkeypatch, [LOAD])
        m._do_sense()
        if m.state == maestro.State.CRISIS:
            m._do_crisis()
    with m.db._connect() as conn:
        rows = conn.execute(
            "SELECT finding_id, times_seen FROM open_alarms"
        ).fetchall()
    assert rows == [("machine-load-average", 3)]
