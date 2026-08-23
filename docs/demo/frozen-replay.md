# Demo: the frozen replay set

The graph's own worst history, held still, re-sat weekly. Run against a copy
of the live database on 2026-08-24:

```
$ python3 -c "... m._replay_frozen_incidents(); m._learning_receipt_text() ..."

frozen set size: 13 | solved today: 0

📚 Learning receipt
Problem classes that paged you last week: 0.
Since then: 0 fixed without you, 0 paged you again, 0 not seen.
Fixes replayed from memory this week: 0.
Frozen replay: 0 of 13 past incidents would now be fixed without you (first sitting).
```

What just happened: the 322 historic escalations in the episodes table were
collapsed by fingerprint into 13 distinct problem classes and frozen as the
exam. The top of the set, with how often each paged you before the set froze:

```
$ sqlite3 graph.db "SELECT times_paged, trigger FROM replay_incidents ORDER BY times_paged DESC LIMIT 5"

  85x  Stripe live key found in /Users/chidionyema/.zsh_history
  33x  Disk has 3.7 GiB free (99.2% used)
  28x  [pipeline] Control on main is detective, not preventive: com...
  28x  [platform] Components with nowhere left to run: 1
  28x  [sched] launchd jobs whose last run exited non-zero: 9
```

0 of 13 is the honest baseline: until 2026-08-24 the auto_fix path was dead
code, so the graph has never yet watched a fix succeed. Every week the same
13 questions are re-sat inside the learning receipt; the score rises only
when the graph has actually learned a fix for one of them, because the
questions never change.

The trend, once two receipts exist:

```
$ sqlite3 ~/.maestro/experience_graph.db \
    "SELECT timestamp, json_extract(evidence,'$.solved') FROM episodes WHERE action='replay' ORDER BY timestamp"
```
