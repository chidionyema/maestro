# maestro, running

maestro is the thing that watches the estate on a loop and fixes what it knows how to fix. This
page shows it doing that. Every block below is pasted from a real run on 2026-08-23; none of it is
written by hand.

## It is running

```
ps -o pid,etime,rss -p $(pgrep -f maestro.py)
```

```
  PID  ELAPSED    RSS
56356 06:12:54    54444
```

Six hours and twelve minutes without a restart.

## It cycles

maestro is a state machine, not a script that runs and exits. It senses the estate, decides whether
anything needs saying, and goes back to sleep. One loop takes about three minutes.

Here is what those loops used to print, earlier the same day:

```
2026-08-23 21:23:26,037 | INFO | maestro | All clear — no digest sent (P3)
2026-08-23 21:26:26,468 | INFO | maestro | All clear — no digest sent (P3)
2026-08-23 21:34:32,524 | INFO | maestro | All clear — no digest sent (P3)
```

That was wrong, and it is worth showing rather than deleting. The estate audit was reporting eight
criticals at the time. maestro read the audit file through a key that file does not use, got an
empty list, and reported a clean estate once a minute through a billing incident. `All clear` was
not a judgement. It was a sensor with nothing plugged into it.

This is the same loop after the fix:

```
tail -6 ~/.maestro/maestro.log
```

```
2026-08-23 22:39:17,672 | INFO     | maestro | State: SENSE
2026-08-23 22:40:17,673 | INFO     | maestro | Estate audit: 57 row(s) read, 45 finding(s) after dropping ok
2026-08-23 22:40:17,696 | INFO     | maestro | State: CRISIS
2026-08-23 22:41:17,844 | INFO     | maestro | Already told him about crisis:04f3ac2bdccc8bf5 inside the cooldown; not repeating
2026-08-23 22:41:17,851 | INFO     | maestro | State: IDLE
2026-08-23 22:42:17,851 | INFO     | maestro | State: SENSE
```

Three lines matter there. `57 row(s) read` is the sensor working — the audit file holds 57 rows and
maestro now sees all of them. `45 finding(s) after dropping ok` is it discarding the twelve checks
that passed and keeping the rest. `State: CRISIS` is it deciding that eight criticals are worth
your phone buzzing.

The fourth line is the one that keeps the channel usable. Those eight criticals are still there on
the next loop, and the loop after that, and maestro is not going to tell you about them twenty
times an hour. It sent the message once and it remembers having sent it:

```
cat ~/.maestro/alert_fence.json
```

```
{"crisis:04f3ac2bdccc8bf5": 1787521097.520619}
```

The key is a hash of which findings the message was about, not of the message text, because the
text carries counters that move every minute. A different set of problems is a different key and
gets through immediately. The same set stays quiet for six hours, then says so again. The entry is
written only when Telegram answers 200, so an outage costs you a duplicate later rather than the
alert itself.

## The two bugs have tests

```
python3 -m pytest tests -q
```

```
..............                                                           [100%]
14 passed in 0.13s
```

Nine of those fourteen are named for the two bugs above —
`test_incident_0002_audit_read_as_zero_findings.py` and
`test_incident_0003_the_same_alert_every_three_minutes.py`. They assert the rule rather than the
code: a sensor reports what the estate reports, a sensor that cannot see says so instead of
reporting health, and one situation is one message.

## Silence is not proof, so the state is published

A watcher that only speaks when something is wrong teaches you that silence means healthy, when
silence is equally what a dead watcher sounds like. So maestro's liveness is written to a page that
says so out loud, rebuilt every hour:

```
grep -A3 'maestro' ~/dev/code/crew/STATE.md
```

```
| maestro | GREEN | last cycle 2 min ago (INTENT-20260823-201225-0d20f3e7.json) |
| &nbsp;&nbsp;skills | GREEN | 1 skill(s) it can heal with |
```

`last cycle 2 min ago` is the useful half. A stopped maestro does not go quiet on that page, it
goes stale, and stale is visible in a way that quiet is not.

## It can act

Sensing without acting is a dashboard. maestro carries skills it has learned, kept in an experience
graph so they survive a restart:

```
sqlite3 ~/.maestro/experience_graph.db 'select name from skills;'
```

```
restart a local bridge that stopped listening
```

One skill today. It was not written into the code by hand; it is a row in a database that grows as
maestro meets problems it works out how to fix.
