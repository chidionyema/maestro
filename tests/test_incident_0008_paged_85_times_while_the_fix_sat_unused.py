"""A P0 with a tested skill paged the founder 85 times and never tried the fix.

Measured 2026-08-24 on the live graph: replay_incidents held a Stripe-key
fingerprint at times_paged=85 and a full-disk fingerprint at 33, while the
skills table held credential-leak-surface (success_rate 1.0) and
resource-exhaustion-monotonic (success_rate 1.0) — and all 232 live intents
recorded exactly 0 auto_fix decisions. The cause was one branch: _do_decide
escalated every P0 unconditionally, before the auto_fix branch could run, so
the sensors' own auto_fix=True flag on credential-leak and disk findings was
dead on arrival. "Pages first and learns second" had no second.

The rule: a P0 whose sensor names a skill, in a lane that allows auto-fix, is
routed to that repair — the page has already happened via CRISIS and the alarm
ledger, so the attempt costs the founder nothing, and ACT/VERIFY still hand a
failed or unverified fix to a person. A P0 with no skill still escalates, and
a lane that forbids auto-fix is not overridden by severity.

Rung 4, incident tests, named for the behaviour.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import maestro  # noqa: E402

from test_incident_0005_paged_twice_for_a_solved_problem import (  # noqa: E402
    _decide,
    _maestro,
)

STRIPE_FINDING = {
    "id": "credential-leak-stripe-live-key",
    "severity": "P0",
    "lane": "estate",
    "description": "Stripe live key found in /Users/x/.zsh_history",
    "auto_fix": True,
    "skill": "credential-leak-surface",
    "context": {"file": "/Users/x/.zsh_history", "key_type": "Stripe live key"},
}


def test_a_p0_with_a_named_skill_is_repaired_not_only_paged(tmp_path, monkeypatch):
    m = _maestro(tmp_path, monkeypatch)
    decision = _decide(m, dict(STRIPE_FINDING))
    assert decision["escalate"] == [], m.current_intent.laws_violated
    assert len(decision["auto_fix"]) == 1
    routed = decision["auto_fix"][0]
    assert routed["skill"] == "credential-leak-surface"
    assert routed["context"]["p0_paged_first"] is True, \
        "the claim that the page preceded the repair must be queryable"


def test_a_p0_with_no_skill_still_goes_to_a_person(tmp_path, monkeypatch):
    m = _maestro(tmp_path, monkeypatch)
    decision = _decide(m, {"id": "load-critical", "severity": "P0",
                           "lane": "estate",
                           "description": "Load average 255 on 12 cores"})
    assert decision["auto_fix"] == []
    assert len(decision["escalate"]) == 1


def test_a_lane_that_forbids_auto_fix_beats_a_p0_sensor_flag(tmp_path, monkeypatch):
    m = _maestro(tmp_path, monkeypatch)
    finding = dict(STRIPE_FINDING, lane="research")
    decision = _decide(m, finding)
    assert decision["auto_fix"] == []
    assert len(decision["escalate"]) == 1
