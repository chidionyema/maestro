"""Maestro consulted nothing before paging, so a solved problem paged him again.

Measured 2026-08-23 on the live ledger: one Stripe finding escalated 46 times in 29
hours with zero learning between passes, and the graph's own history of successful
repairs was never read on the decide path. The founder's words: "they need to lern
fast and we eed proof" and "i need rucrsinve learing and inprovenent really".

The rule, in two halves. First: before a non-crisis finding costs a person attention,
the graph is asked whether it has already watched a skill fix that class of problem,
and a remembered fix is retried instead of queued (evidence carries source=memory so
the claim is queryable). Second: once a week a learning receipt reaches Telegram
stating what last week's pages cost this week — fixed without him, paged again, or
gone — because learning without proof is an assertion (LAW 35, LAW 28).

Rung 4, incident tests, named for the behaviour.
Research feeding this design: ReasoningBank (arXiv 2509.25140), crew
science/RESEARCH-LEDGER.jsonl entry 2026-08-23.
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import maestro  # noqa: E402
from maestro import Episode, problem_fingerprint  # noqa: E402

from test_incident_0003_the_same_alert_every_three_minutes import _bridge  # noqa: E402


def _maestro(tmp_path, monkeypatch):
    monkeypatch.setattr(maestro.Config, "DB_PATH", str(tmp_path / "graph.db"))
    monkeypatch.setattr(maestro.Config, "INTENT_LOG_DIR", str(tmp_path / "intents"))
    m = maestro.Maestro()
    m.bridge = _bridge(tmp_path, monkeypatch)
    return m


def _intent():
    return maestro.Intent(
        id="INT-test", timestamp=datetime.utcnow().isoformat(), trigger="test"
    )


def _success_episode(trigger, skill_id, lane="estate", days_ago=1.0, suffix="a"):
    ts = datetime.utcnow() - timedelta(days=days_ago)
    return Episode(
        id=f"EP-test-{suffix}",
        timestamp=ts.isoformat(),
        lane=lane,
        trigger=trigger,
        action="auto_fix",
        outcome="success",
        evidence={"skill_id": skill_id} if skill_id else {},
    )


def _decide(m, finding):
    m.daily_findings = [finding]
    m.current_intent = _intent()
    m._do_decide()
    return m.current_intent.decision


def test_the_same_numbers_change_but_the_problem_is_one_class():
    a = problem_fingerprint("Disk at 96%", "estate")
    b = problem_fingerprint("disk  at 97%", "estate")
    c = problem_fingerprint("Disk at 96%", "security")
    assert a == b, "a varying number must not split one problem into many"
    assert a != c, "the same words in two lanes are two problems"


def test_the_law_gate_no_longer_rejects_every_plan(tmp_path, monkeypatch):
    """Found 2026-08-24: the plan's one-line mechanism failed _law_mechanism's
    two-step floor on every finding, so auto_fix and queue were dead branches —
    all 183 live intents confirm nothing was ever routed anywhere but escalate."""
    m = _maestro(tmp_path, monkeypatch)
    decision = _decide(m, {"id": "disk", "description": "Disk at 96%",
                           "severity": "P2", "lane": "estate",
                           "auto_fix": True, "skill": "disk_cleanup"})
    assert decision["escalate"] == [], m.current_intent.laws_violated
    assert len(decision["auto_fix"]) == 1


def test_a_problem_the_graph_solved_before_is_retried_not_queued(tmp_path, monkeypatch):
    m = _maestro(tmp_path, monkeypatch)
    m.db.log_episode(_success_episode("Disk at 96%", "disk_cleanup"))
    decision = _decide(m, {"id": "disk", "description": "Disk at 97%",
                           "severity": "P2", "lane": "estate"})
    assert decision["queue"] == []
    assert len(decision["auto_fix"]) == 1
    routed = decision["auto_fix"][0]
    assert routed["skill"] == "disk_cleanup"
    assert routed["context"]["source"] == "memory", \
        "a memory-sourced retry must say so, or the learning is unqueryable"


def test_a_problem_never_solved_still_goes_to_a_person(tmp_path, monkeypatch):
    m = _maestro(tmp_path, monkeypatch)
    decision = _decide(m, {"id": "novel", "description": "Something new broke",
                           "severity": "P2", "lane": "estate"})
    assert decision["auto_fix"] == []
    assert len(decision["queue"]) == 1


def test_an_old_success_without_a_skill_id_is_history_not_memory(tmp_path, monkeypatch):
    m = _maestro(tmp_path, monkeypatch)
    m.db.log_episode(_success_episode("Disk at 96%", skill_id=None))
    decision = _decide(m, {"id": "disk", "description": "Disk at 96%",
                           "severity": "P2", "lane": "estate"})
    assert decision["auto_fix"] == []
    assert len(decision["queue"]) == 1


def test_a_lane_that_forbids_auto_fix_is_not_overridden_by_memory(tmp_path, monkeypatch):
    m = _maestro(tmp_path, monkeypatch)
    m.db.log_episode(_success_episode("Model drift detected", "retrain", lane="research"))
    decision = _decide(m, {"id": "drift", "description": "Model drift detected",
                           "severity": "P2", "lane": "research"})
    assert decision["auto_fix"] == []
    assert len(decision["queue"]) == 1


def test_the_receipt_states_what_last_weeks_pages_cost_this_week(tmp_path, monkeypatch):
    m = _maestro(tmp_path, monkeypatch)
    now = datetime.utcnow()

    def escalation(trigger, days_ago, suffix):
        return Episode(
            id=f"EP-esc-{suffix}",
            timestamp=(now - timedelta(days=days_ago)).isoformat(),
            lane="estate", trigger=trigger,
            action="escalated", outcome="needs_human",
        )

    # Last week: three problem classes paged him.
    m.db.log_episode(escalation("Disk at 96%", 8, "disk"))
    m.db.log_episode(escalation("Consumer process dead", 8, "consumer"))
    m.db.log_episode(escalation("Cert expires in 3 days", 8, "cert"))
    # This week: disk got fixed from memory, the consumer paged him again,
    # the cert problem was not seen at all.
    ep = _success_episode("Disk at 97%", "disk_cleanup", days_ago=1.0, suffix="fixed")
    ep.evidence["source"] = "memory"
    m.db.log_episode(ep)
    m.db.log_episode(escalation("Consumer process dead", 1, "again"))

    text = m._learning_receipt_text()
    assert "paged you last week: 3" in text
    assert "1 fixed without you" in text
    assert "1 paged you again" in text
    assert "1 not seen" in text
    assert "memory this week: 1" in text


def test_the_receipt_arrives_once_a_week_not_once_a_tick(tmp_path, monkeypatch):
    m = _maestro(tmp_path, monkeypatch)
    m._maybe_send_learning_receipt()
    m._maybe_send_learning_receipt()
    m._maybe_send_learning_receipt()
    receipts = [d for d in m.bridge.delivered if "Learning receipt" in d]
    assert len(receipts) == 1, m.bridge.delivered
    assert m.db.kv_get(m.LEARNING_RECEIPT_KEY) is not None, \
        "a delivered receipt must advance the clock, or it repeats forever"


def test_an_undelivered_receipt_is_retried_not_marked_done(tmp_path, monkeypatch):
    m = _maestro(tmp_path, monkeypatch)
    monkeypatch.setattr(m.bridge, "send", lambda *a, **k: False)
    m._maybe_send_learning_receipt()
    assert m.db.kv_get(m.LEARNING_RECEIPT_KEY) is None, \
        "a send that never arrived must not count as the weekly receipt (LAW 28)"
