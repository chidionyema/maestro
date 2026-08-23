# maestro

## What it is for

maestro watches the estate on a three minute loop so that you do not have to. It senses what is
running, decides whether anything has gone wrong, and either fixes it from a skill it already has
or tells you. The point of it is the difference between a problem that is found in three minutes
and a problem that is found when you next happen to look. It is not the thing that talks to you on
Telegram, which is The Architect. maestro is the thing that notices, and The Architect is the thing
that carries the message.

## What it costs

Almost nothing while the estate is healthy, which is most of the time. A sense pass is local
inspection, not model calls, so the six hours of cycling shown in the demo cost nothing. Model
spend happens only when maestro decides something needs thinking about, and the running total is
tracked in a `daily_spend` table in its own database so the number is answerable rather than
estimated. Memory is about 54 MB resident.

## What it watches and changes

It watches the estate's live state and the failure shapes it has seen before. It changes things
only through skills it holds, and there is exactly one today: restarting a local bridge that has
stopped listening. That narrowness is the safety property. maestro cannot take an action it has not
learned, so the worst case is that it notices something and cannot fix it, which is the same
position you would be in without it.

## Where it lives

The code is at `~/dev/code/maestro`, and the process is `maestro.py`. It runs under launchd as
`com.chidionyema.maestro`. Its log is `logs/maestro.out.log` next to the code. Its memory, the
skills and failure shapes it has accumulated, lives separately in `~/.maestro/experience_graph.db`,
so deleting the checkout does not delete what it has learned. There is a second copy of maestro
elsewhere on this machine that shares the same database and must never be started; only
`~/dev/code/maestro` is live.

## How to turn it off

```
launchctl bootout gui/$(id -u)/com.chidionyema.maestro
```

It stops immediately and stays stopped across a reboot. Nothing breaks when you do this. You simply
stop being told about problems, and the estate goes back to being watched only when someone looks.

## How to turn it back on

```
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.chidionyema.maestro.plist
```

Confirm it came back by watching one cycle land: `tail -f ~/dev/code/maestro/logs/maestro.out.log`
should print `State: SENSE` within three minutes.

## What goes wrong

The failure worth knowing about is that maestro dies and nothing says so. It reports by exception,
so a healthy maestro and a dead maestro both send you nothing. That is why its liveness is
published to the estate page instead of being left to silence: a dead one shows there as a stale
timestamp rather than as an absence. If you ever want to check it yourself in one glance, the
maestro row on that page carries the age of its last cycle.

The second is the shared database. Two copies of maestro running against one experience graph will
each believe they are the only one, and their skills will fight. Only ever run the copy in
`~/dev/code/maestro`, and never start `maestro.py` directly when launchd is already running it.
