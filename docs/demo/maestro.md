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
anything needs saying, and goes back to sleep. One loop takes three minutes, and the log shows six
of them back to back:

```
tail -25 ~/dev/code/maestro/logs/maestro.out.log
```

```
2026-08-23 21:15:25,433 | INFO | maestro | State: SENSE
2026-08-23 21:16:25,470 | INFO | maestro | State: REPORT
2026-08-23 21:17:25,543 | INFO | maestro | All clear — no digest sent (P3)
2026-08-23 21:17:25,552 | INFO | maestro | State: IDLE
2026-08-23 21:18:25,626 | INFO | maestro | State: SENSE
2026-08-23 21:19:25,715 | INFO | maestro | State: REPORT
2026-08-23 21:20:25,789 | INFO | maestro | All clear — no digest sent (P3)
2026-08-23 21:20:25,791 | INFO | maestro | State: IDLE
2026-08-23 21:21:25,866 | INFO | maestro | State: SENSE
2026-08-23 21:22:25,962 | INFO | maestro | State: REPORT
2026-08-23 21:23:26,037 | INFO | maestro | All clear — no digest sent (P3)
2026-08-23 21:23:26,039 | INFO | maestro | State: IDLE
2026-08-23 21:24:26,151 | INFO | maestro | State: SENSE
2026-08-23 21:25:26,393 | INFO | maestro | State: REPORT
2026-08-23 21:26:26,468 | INFO | maestro | All clear — no digest sent (P3)
2026-08-23 21:26:26,472 | INFO | maestro | State: IDLE
2026-08-23 21:27:26,547 | INFO | maestro | State: SENSE
```

`All clear` is the line to understand. maestro found nothing worth waking you for, so it sent you
nothing. That is deliberate, and it is also the reason the next section exists.

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
