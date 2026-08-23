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

It watches the estate's live state and the failure shapes it has seen before. Its main eye is the
estate audit, `~/.claude/state/estate-audit.json`, which another job rewrites and which currently
holds 57 rows: 8 critical, 21 warn, 16 unknown, 12 passing. maestro reads every row, drops the ones
that passed, and grades the rest into P0, P1 and P2. A severity word it has never seen is raised as
a P1 rather than ignored, because a check nobody taught it about is exactly the one you would want
raised. If that file is missing, corrupt, older than six hours, or has changed shape, maestro
reports that as a fault in its own right instead of reporting a healthy estate.

It changes things only through skills it holds, and there is exactly one today: restarting a local
bridge that has stopped listening. That narrowness is the safety property. maestro cannot take an
action it has not learned, so the worst case is that it notices something and cannot fix it, which
is the same position you would be in without it. Audit rows in particular are marked not
auto-fixable, so maestro will never report one of them as resolved without something having
actually repaired it.

It also keeps a small file of its own, `~/.maestro/alert_fence.json`, recording what it has already
told you and when. That is what stops eight standing problems becoming twenty messages an hour.

## Where it lives

The code is at `~/dev/code/maestro`, and the process is `maestro.py`. It runs under launchd as
`com.chidionyema.maestro`. It writes two logs and they are not equivalent:
`~/.maestro/maestro.log` is flushed line by line and is the one to read, while
`logs/maestro.out.log` next to the code is launchd's capture of stdout, is block-buffered, and can
lag several minutes behind. Its memory, the
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

The third is the one it was caught doing on 2026-08-23, and it is the reason to distrust a quiet
maestro over a loud one. It was reading the estate audit through a key that file does not contain,
so it saw an empty list and printed `All clear` once a minute for hours while eight criticals stood
there. A sensor wired to nothing looks exactly like good news. The fix reads the file's real shape
and shouts if that shape ever changes again, but the general lesson stands: the page in the demo
that shows maestro's last cycle age is a better health check than the absence of messages.

If maestro ever does start repeating itself, the fence is the thing to look at. Deleting
`~/.maestro/alert_fence.json` makes it forget everything it has told you and it will say it all
again on the next loop; setting `MAESTRO_REPEAT_COOLDOWN_S` in the plist changes how long it stays
quiet about a standing problem, and the default is six hours.
