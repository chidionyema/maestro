# Maestro fixes things now, instead of telling you about them

## What this is for

Maestro watches the estate on a one minute loop. Until today, every single thing it
found, it sent to you. Its own ledger says so: 137 incidents recorded, 137 marked
`needs_human`, none fixed. That is a pager, not a deputy, and it is the reason you
could not disappear for a day.

This is the part that closes the loop. Maestro now recognises an incident as an
instance of a pattern it has seen before, looks up the fix that pattern already has,
runs it, and only writes to you when there is no fix or the fix failed.

## What it can fix without you

Three patterns, learned from its own 121 recorded incidents.

| Pattern | Seen | What it runs |
|---|---|---|
| A live credential written into a history, log or config file | 86 | `~/.claude/scripts/secret-scrub.py` |
| Disk filling up | 33 | `skills/reclaim-disk.sh` |
| A local service stopped listening on its port | 2 | restarts the bridge or Ollama |

Anything that is not one of those three still comes to you, and says which shape it
did not match. It never invents a fix.

## What it costs

Nothing per incident. All three fixes are local shell commands on your Mac. No model
call, no API spend. The scrubber and the port restart take a few seconds; the disk
reclaim takes about a minute because it measures the caches before removing them.

## What it will change on disk

Only these, and only under your home directory:

- Secret values, redacted in place in `.zsh_history`, `.claude/history.jsonl` and
  checkpoint files. The line count never changes. It refuses to touch
  `~/.config/*/secrets.sh`, whose job is to hold secrets.
- Package manager caches: pip, Homebrew downloads, npm, Cargo, Go build, Xcode
  DerivedData. All of these rebuild themselves the next time you use the tool.
- Its own log files older than thirty days.

It will not touch source, documents, databases, virtualenvs, model weights or
anything in iCloud Drive. Right now the caches hold about 136 MB, so this handles an
ordinary creep and not a real crisis. When clearing every cache still leaves the disk
below five gigabytes free, the skill deliberately fails and sends the incident to
you, because at that point the thing eating the disk is not a cache.

## Where it lives

`maestro.py` in `~/dev/code/maestro`, in the `ShapeExtractor` and `_do_act` sections.
The patterns and their fixes are rows in `~/.maestro/experience_graph.db`, tables
`shapes` and `skills`. The disk fix is a readable shell script at
`skills/reclaim-disk.sh` in the same repository.

## How to turn it off

One command, and it takes effect on the next tick, within a minute:

```
sqlite3 ~/.maestro/experience_graph.db "UPDATE shapes SET confidence = 0"
```

Maestro keeps running and keeps watching. It simply stops matching anything to a
fix, so every incident comes to you exactly as it did before. Nothing is deleted, so
this is not a decision you have to be sure about.

## How to turn it back on

```
sqlite3 ~/.maestro/experience_graph.db "UPDATE shapes SET confidence = 0.7"
```

To disable one fix and keep the others, name it:

```
sqlite3 ~/.maestro/experience_graph.db \
  "UPDATE shapes SET confidence = 0 WHERE pattern_name = 'resource-exhaustion-monotonic'"
```

## What goes wrong

**A fix runs and does not work.** The skill exits non zero, maestro marks the
incident `needs_human` and sends it to you with the failure attached. The skill's
success rate in the `skills` table drops. Below 0.5 it stops being offered
automatically, so a fix that keeps failing takes itself out of service.

**A fix runs when it should not have.** Every run is recorded: which skill, which
incident, exit code, output and duration. Read the last twenty:

```
sqlite3 ~/.maestro/experience_graph.db \
  "SELECT timestamp, trigger, shape_id, outcome FROM episodes ORDER BY timestamp DESC LIMIT 20"
```

**A new kind of failure appears.** It will not match any of the three shapes, so it
comes to you and is logged as novel. Maestro does not write new fixes for itself.
Adding a fourth pattern is a code change a person reviews.

**Two maestros.** There is a second copy at `~/.claude/scripts/maestro/maestro.py`
sharing the same database. Only `~/dev/code/maestro` is scheduled and live. If you
ever see behaviour that does not match this page, check which one ran.
