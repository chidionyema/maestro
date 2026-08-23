"""322 episodes of history and the graph had learned from none of them.

Measured 2026-08-24 on the live ledger: every one of the graph's 322 episodes
was an escalation (320 crisis, 2 queued) and zero were successful fixes —
auto_fix had been dead code behind the LAW_MECHANISM gate since it existed, so
the graph never once watched a fix work. The founder's words: "why dont we lok
at historic data, we have a wealth of data to train thn, this should be
autonatd and repeatable".

The rule: the historic escalations become a frozen replay set — the graph's
own worst history, held still — and every weekly receipt re-sits that exam and
reports how many of those past pages would now be fixed from memory. Frozen
means the questions never change, so a rising score is learning and not an
easier test. Automated means it rides the receipt clock; nobody runs a script
(LAW 31). Repeatable means the same replay, every week, recorded as an
episode so the trend is queryable (LAW 30).

Rung 4, incident tests, named for the behaviour.
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import maestro  # noqa: E402
from maestro import Episode  # noqa: E402

from test_incident_0003_the_same_alert_every_three_minutes import _bridge  # noqa: E402


def _maestro(tmp_path, monkeypatch):
    monkeypatch.setattr(maestro.Config, "DB_PATH", str(tmp_path / "graph.db"))
    monkeypatch.setattr(maestro.Config, "INTENT_LOG_DIR", str(tmp_path / "intents"))
    m = maestro.Maestro()
    m.bridge = _bridge(tmp_path, monkeypatch)
    return m


def _escalation(trigger, suffix, lane="estate", days_ago=3.0):
    ts = datetime.utcnow() - timedelta(days=days_ago)
    return Episode(
        id=f"EP-esc-{suffix}", timestamp=ts.isoformat(), lane=lane,
        trigger=trigger, action="crisis_escalation", outcome="needs_human",
    )


def _success(trigger, skill_id, suffix, lane="estate"):
    return Episode(
        id=f"EP-fix-{suffix}", timestamp=datetime.utcnow().isoformat(),
        lane=lane, trigger=trigger, action="auto_fix", outcome="success",
        evidence={"skill_id": skill_id},
    )


def test_the_frozen_set_does_not_move_when_history_grows(tmp_path, monkeypatch):
    m = _maestro(tmp_path, monkeypatch)
    m.db.log_episode(_escalation("Disk at 96%", "a"))
    assert m.db.freeze_replay_set() == 1
    m.db.log_episode(_escalation("Something new broke", "b"))
    assert m.db.freeze_replay_set() == 1, \
        "a reseeded exam grades nothing — frozen means frozen"


def test_a_past_page_the_graph_can_now_fix_counts_as_solved(tmp_path, monkeypatch):
    m = _maestro(tmp_path, monkeypatch)
    m.db.log_episode(_escalation("Disk at 96%", "a"))
    m.db.log_episode(_escalation("Consumer process dead", "b"))
    m.db.log_episode(_success("Disk at 97%", "disk_cleanup", "c"))
    replay = m._replay_frozen_incidents()
    assert replay["total"] == 2
    assert replay["solved"] == 1


def test_the_replay_is_a_dry_run_that_pages_nobody(tmp_path, monkeypatch):
    m = _maestro(tmp_path, monkeypatch)
    m.db.log_episode(_escalation("Disk at 96%", "a"))
    m.db.log_episode(_success("Disk at 96%", "disk_cleanup", "b"))
    m._replay_frozen_incidents()
    assert m.bridge.delivered == [], "a benchmark that alerts is an alert"
    with m.db._connect() as conn:
        fixes = conn.execute(
            "SELECT COUNT(*) FROM episodes WHERE action = 'auto_fix'"
        ).fetchone()[0]
    assert fixes == 1, "replay must consult memory, never execute a skill"


def test_a_lane_that_forbids_auto_fix_never_scores(tmp_path, monkeypatch):
    m = _maestro(tmp_path, monkeypatch)
    m.db.log_episode(_escalation("Model drift detected", "a", lane="research"))
    m.db.log_episode(_success("Model drift detected", "retrain", "b", lane="research"))
    replay = m._replay_frozen_incidents()
    assert replay["total"] == 1
    assert replay["solved"] == 0, \
        "a lane a human must own cannot be scored as solved without one"


def test_the_receipt_carries_the_replay_score(tmp_path, monkeypatch):
    m = _maestro(tmp_path, monkeypatch)
    m.db.log_episode(_escalation("Disk at 96%", "a"))
    m.db.log_episode(_success("Disk at 96%", "disk_cleanup", "b"))
    text = m._learning_receipt_text()
    assert "Frozen replay: 1 of 1" in text
    assert "first sitting" in text


def test_the_score_is_recorded_once_per_delivered_receipt(tmp_path, monkeypatch):
    m = _maestro(tmp_path, monkeypatch)
    m.db.log_episode(_escalation("Disk at 96%", "a"))
    m._maybe_send_learning_receipt()
    m._maybe_send_learning_receipt()
    with m.db._connect() as conn:
        rows = conn.execute(
            "SELECT COUNT(*) FROM episodes WHERE action = 'replay'"
        ).fetchone()[0]
    assert rows == 1, "one trend point per week, not one per tick"


def test_an_undelivered_receipt_records_no_score(tmp_path, monkeypatch):
    m = _maestro(tmp_path, monkeypatch)
    m.db.log_episode(_escalation("Disk at 96%", "a"))
    monkeypatch.setattr(m.bridge, "send", lambda *a, **k: False)
    m._maybe_send_learning_receipt()
    with m.db._connect() as conn:
        rows = conn.execute(
            "SELECT COUNT(*) FROM episodes WHERE action = 'replay'"
        ).fetchone()[0]
    assert rows == 0, \
        "a score with no delivered receipt is a trend nobody read (LAW 28)"


def test_the_next_receipt_states_the_previous_score(tmp_path, monkeypatch):
    m = _maestro(tmp_path, monkeypatch)
    m.db.log_episode(_escalation("Disk at 96%", "a"))
    m._maybe_send_learning_receipt()  # first sitting, score 0, recorded
    m.db.log_episode(_success("Disk at 96%", "disk_cleanup", "b"))
    text = m._learning_receipt_text()
    assert "Frozen replay: 1 of 1" in text
    assert "last receipt: 0" in text, \
        "a trend needs the previous point stated, or it is a number, not a trend"
