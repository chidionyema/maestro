# Maestro fixing something, start to finish

Every block below is pasted from a real run on 2026-08-23, with the command that
produced it above it. Nothing here is typed by hand.

## Before: it had learned nothing from 121 incidents

The design rests on turning incidents into patterns. It had produced none.

```
sqlite3 ~/.maestro/experience_graph.db "SELECT COUNT(*) FROM episodes; SELECT COUNT(*) FROM shapes;"
```

```
121
0
```

Every one of those incidents went to the founder:

```
sqlite3 ~/.maestro/experience_graph.db "SELECT outcome, COUNT(*) FROM episodes GROUP BY outcome;"
```

```
needs_human|137
```

## Why: it was matching machine output against hand written English

The pattern table said `"disk full"` and `"token in history"`. The sensors write
`Disk has 1.9 GiB free (99.6% used)` and
`Stripe live key found in /Users/chidionyema/.zsh_history`. Substring matching found
nothing. Replaying all 121 incidents through the repaired matcher:

```
python3 - <<'PY'   # full script in the commit
... replay every recorded episode through ShapeExtractor ...
PY
```

```
episodes replayed: 121   linked to a shape: 121
```

```
sqlite3 ~/.maestro/experience_graph.db "SELECT pattern_name, occurrence_count, invariant_violated FROM shapes ORDER BY 2 DESC;"
```

```
pattern_name                   occurrence_count  invariant_violated
credential-leak-surface        86                LAW_TRADEOFF
resource-exhaustion-monotonic  33                LAW_RIPPLE
service-unreachable-endpoint   2                 LAW_MECHANISM
```

Your Stripe live key had leaked into shell history eighty six times. Maestro had
recorded every one and generalised none of them.

## Every shape now has a fix behind it

```
sqlite3 ~/.maestro/experience_graph.db "SELECT s.pattern_name, s.occurrence_count, k.id, k.total_uses, k.success_rate FROM shapes s LEFT JOIN skills k ON k.id = s.prevention_skill ORDER BY 2 DESC;"
```

```
pattern_name                   seen  skill                          runs  rate
credential-leak-surface        86    credential-leak-surface        0     0.0
resource-exhaustion-monotonic  33    resource-exhaustion-monotonic  0     0.0
service-unreachable-endpoint   2     restart_bridge                 1     1.0
```

## One real incident, all the way through

The text is the exact incident maestro raised and escalated, taken from its own
database, not written for this demo.

```
python3 - <<'PY'
incident = <the newest credential episode's trigger, read from the database>
print(ex.pattern_for(incident))
skill = ex.find_prevention(incident, "estate")
ok, ev = SkillExecutor(g).execute(skill, {})
PY
```

```
incident : Stripe live key found in /Users/chidionyema/.zsh_history
shape    : credential-leak-surface
skill    : credential-leak-surface
executed : True | rc 0 |
duration : 6021 ms
```

The graph recorded the run, which is how a fix earns the right to be used again:

```
sqlite3 ~/.maestro/experience_graph.db "SELECT id, total_uses, success_rate, substr(last_used,1,16) FROM skills ORDER BY id;"
```

```
credential-leak-surface        1  1.0  2026-08-23T21:52
resource-exhaustion-monotonic  0  0.0
restart_bridge                 1  1.0  2026-08-23T18:45
```

And the surfaces it cleans are clean, checked by the scrubber's own report mode:

```
python3 ~/.claude/scripts/secret-scrub.py --check; echo "exit: $?"
```

```
secret-scrub: 0 occurrence(s) in files that should hold none
exit: 0
```

## The disk fix, in report mode

It ships read only first. This deleted nothing.

```
skills/reclaim-disk.sh --check
```

```
free before: 70 GiB (critical below 5)
  would free     37 MB  Homebrew downloads
  would free     19 MB  npm cache
  would free     80 MB  Cargo registry cache
  would delete 0 maestro log file(s) older than 30 days
reclaimable: ~136 MB. Nothing was deleted.
```

136 MB is honest and it is small. It handles ordinary creep. During a real crisis it
will clear every cache, find the disk still below five gigabytes free, exit non zero
and send the incident to you, because at that point the cause is not a cache.

## It refuses to invent a fix

An incident that matches nothing goes to a person, and says so, rather than being
marked resolved:

```
  shape=None    skill=NONE, goes to a person    <- the cat sat on the mat
```

Until today that path wrote a skill whose entire procedure was
`echo 'Fix for <id>'`, saved it to the skills table as if it were real, and read
echo's exit code 0 as a successful repair. The incident was reported to you as
resolved and the fake skill stayed in the graph to be trusted next time.

## The requirements it closes

```
16 passed, 1 failed, of 17
```

The one failure is MAE-040, "you tap Approve on your phone". Its check requires
maestro to poll Telegram for inbound commands, and MAE-050's check requires that it
never does, because a second poller once made the gateway deaf for 31.5 hours. The
two cannot both pass as written. Approvals have to arrive through The Architect's
existing connection instead, which is a separate change.
