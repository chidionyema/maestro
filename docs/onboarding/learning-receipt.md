# Onboarding: consult-before-escalate, and the weekly learning receipt

## What is this for

Two things, one goal: maestro stops paging you about problems it has already
solved, and once a week it proves — with numbers, not claims — whether it is
actually getting better. Before this, one Stripe finding escalated 46 times in
29 hours and maestro never once consulted its own history between passes.

## What does it cost

Nothing recurring. One SQLite read per finding on the decide path (bounded to
the last 500 success episodes), and one Telegram message per week. No new
process, no new scheduled job — the receipt rides the existing 60-second tick
loop and remembers its last send inside the same database maestro already owns.

## What does it watch or change

It reads and writes `~/.maestro/experience_graph.db` (the episodes and kv
tables). It changes routing: a non-crisis finding whose problem class was fixed
before is retried with the remembered skill instead of being queued for you.
P0 crisis findings are untouched — a crisis still pages you first and learns
second. Lanes with auto_fix disabled (research, meta) are never overridden.

## Where does it live

`~/dev/code/maestro/maestro.py` — `remembered_fix`, `_learning_receipt_text`,
`_maybe_send_learning_receipt`. Runs inside the existing launchd job
`com.chidionyema.maestro`.

## How do I turn it off

```
launchctl bootout gui/501/com.chidionyema.maestro
```

That stops all of maestro (the receipt has no separate process to kill). To
keep maestro but silence just the weekly receipt, an agent can set the kv key
`last_learning_receipt` far into the future — ask any session.

## How do I turn it back on

```
launchctl kickstart -k gui/501/com.chidionyema.maestro
```

## What goes wrong

If Telegram is down the receipt is retried on the next pass, not marked sent —
a receipt that never arrived never counts as delivered. If the database is
rebuilt from empty, the first receipt reports zeros; that is honest, not
broken. If a remembered skill has rotted, its failure escalates to you exactly
as an unfixable finding always did.
