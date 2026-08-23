# Onboarding: the frozen replay set

## What is this for

You asked why the wealth of historic data was not being used to train the
system, and for that use to be automated and repeatable. This is it. Every
problem that ever paged you was frozen into a fixed exam of 13 problem
classes. Once a week, inside the learning receipt you already get, maestro
re-sits that exam and reports how many of those past pages it could now fix
without you. The questions never change, so a rising score is proof of
learning, not an easier test.

## What does it cost

Nothing recurring beyond what the receipt already cost: one weekly dry run of
13 memory lookups against the local SQLite database, and one extra line in
the existing Telegram message. No new process, no new scheduled job, nothing
for you to run — it rides the same weekly clock as the receipt.

## What does it watch or change

It reads the episodes table and writes two things: the frozen set itself
(`replay_incidents`, written once, never reseeded) and one `replay` episode
per delivered receipt, which is the trend. It changes no routing, executes no
skills, and sends no alerts of its own. Lanes where auto-fixing is forbidden
(research, meta) can never score as solved.

## Where does it live

`~/dev/code/maestro/maestro.py` — `freeze_replay_set`,
`_replay_frozen_incidents`, and the last line of `_learning_receipt_text`.
Data in `~/.maestro/experience_graph.db`. Runs inside the existing launchd
job `com.chidionyema.maestro`.

## How do I turn it off

```
launchctl bootout gui/501/com.chidionyema.maestro
```

That stops all of maestro. To keep maestro and silence only the weekly
receipt (the replay rides inside it), ask any session to push the kv key
`last_learning_receipt` into the future.

## How do I turn it back on

```
launchctl kickstart -k gui/501/com.chidionyema.maestro
```

## What goes wrong

If Telegram is down, the receipt retries and no score is recorded until one
actually reaches you — the trend only holds points you saw. If the database
is rebuilt from empty, the exam reseeds from whatever history remains and
says so with a smaller total. A score stuck at 0 for weeks is itself the
finding: it means the fix path is not learning, and that is exactly what the
number exists to catch.
