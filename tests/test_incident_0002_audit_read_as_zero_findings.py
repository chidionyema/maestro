"""Maestro read the estate audit through a key that does not exist and saw nothing.

Found 2026-08-23. `estate_audit.py:474` writes {"generated_at", "counts", "rows"} with
severities critical/warn/ok/unknown. `EstateSensors.read_audit` asked for
`data["findings"]` and got the default, `[]`, every sixty seconds against a 24,311-byte
file holding 57 rows and 8 criticals. The log line was "All clear -- no digest sent (P3)"
and it ran through a billing incident and five nights of unrestorable backups.

The founder's words, 2026-08-23: "we had the billing incident earlier, we have a survival
plan, which should have been pro[active]".

Rung 4, incident tests. They assert the rule -- a sensor reports what the estate reports,
and a sensor that cannot see says so -- not the shape of the reader, so rewriting the
mapping keeps them honest.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import maestro  # noqa: E402


def _audit(tmp_path, **overrides):
    """A file in the exact shape the estate audit writes."""
    data = {
        "generated_at": time.time(),
        "counts": {"critical": 2, "warn": 1, "unknown": 1, "ok": 1},
        "rows": [
            {"domain": "backup", "title": "Copies that survive losing Fly",
             "value": "13/14", "severity": "critical", "proof": "stack.sh recover",
             "detail": "one prefix has no copy"},
            {"domain": "platform", "title": "Components with nowhere left to run",
             "value": "1", "severity": "critical", "proof": "stack.sh status",
             "detail": "not serving"},
            {"domain": "sched", "title": "launchd jobs that exited non-zero",
             "value": "9", "severity": "warn", "proof": "launchctl list", "detail": ""},
            {"domain": "money", "title": "Stripe balance", "value": "?",
             "severity": "unknown", "proof": "stripe balance", "detail": ""},
            {"domain": "machine", "title": "Disk free", "value": "40 GiB",
             "severity": "ok", "proof": "df -h /", "detail": ""},
        ],
    }
    data.update(overrides)
    path = tmp_path / "estate-audit.json"
    path.write_text(json.dumps(data))
    return str(path)


def _sensors(path):
    sensors = maestro.EstateSensors()
    sensors.audit_path = path
    return sensors


def test_a_real_audit_file_does_not_read_as_an_empty_estate(tmp_path):
    """The whole incident in one assertion: rows in, findings out.

    Two angles. The count is one -- it must not be zero against a file with rows.
    The severities are the other: a critical row has to arrive as something that
    reaches the founder, not as a lower grade that stops at a log file.
    """
    findings = _sensors(_audit(tmp_path)).read_audit()

    assert findings, "an audit holding 4 non-ok rows must not read as a clean estate"
    by_severity = {}
    for f in findings:
        by_severity[f["severity"]] = by_severity.get(f["severity"], 0) + 1
    assert by_severity.get("P0") == 2, by_severity
    assert by_severity.get("P1") == 1, by_severity
    assert by_severity.get("P2") == 1, by_severity


def test_passing_checks_are_not_reported_as_problems(tmp_path):
    """`ok` is the audit saying a check passed. A clean estate still reads clean."""
    findings = _sensors(_audit(tmp_path)).read_audit()
    assert not any("Disk free" in f["description"] for f in findings)

    clean = _audit(tmp_path, rows=[
        {"domain": "machine", "title": "Disk free", "value": "40 GiB",
         "severity": "ok", "proof": "df -h /", "detail": ""},
    ])
    assert _sensors(clean).read_audit() == []


def test_a_severity_nobody_taught_the_reader_is_raised_not_dropped(tmp_path):
    """The silent miss case is the defect, so an unknown word must still alarm."""
    path = _audit(tmp_path, rows=[
        {"domain": "money", "title": "Card declined", "value": "yes",
         "severity": "catastrophic", "proof": "stripe events", "detail": ""},
    ])
    findings = _sensors(path).read_audit()
    assert len(findings) == 1
    assert findings[0]["severity"] in ("P0", "P1")


def test_a_sensor_that_cannot_see_says_so_rather_than_reporting_health(tmp_path):
    """Missing, unreadable, stale and wrong-shaped all have to be loud.

    Silence is the failure mode being fixed: an absent file and a healthy estate
    produced identical output, and the founder reads identical output as good news.
    """
    missing = _sensors(str(tmp_path / "not-there.json")).read_audit()
    assert len(missing) == 1 and missing[0]["id"] == "estate-audit-missing"

    broken = tmp_path / "broken.json"
    broken.write_text("{not json")
    unreadable = _sensors(str(broken)).read_audit()
    assert len(unreadable) == 1 and unreadable[0]["id"] == "estate-audit-unreadable"

    wrong_shape = tmp_path / "shape.json"
    wrong_shape.write_text(json.dumps({"generated_at": time.time(), "results": []}))
    shaped = _sensors(str(wrong_shape)).read_audit()
    assert any(f["id"] == "estate-audit-schema-unknown" for f in shaped)

    stale_at = time.time() - 48 * 3600
    stale = _sensors(_audit(tmp_path, generated_at=stale_at)).read_audit()
    assert any(f["id"] == "estate-audit-stale" for f in stale), \
        "a day-old audit read as current state is how a dead checker looks green"


def test_an_audit_row_is_never_marked_auto_fixable(tmp_path):
    """`_do_act` invents an `echo` skill for anything auto-fixable and records success.

    An audit row states a condition and carries no repair, so marking one auto-fixable
    turns a standing critical into "auto-resolved" in the founder's digest -- a fix that
    never happened, reported as one.
    """
    for f in _sensors(_audit(tmp_path)).read_audit():
        assert f["auto_fix"] is False, f
