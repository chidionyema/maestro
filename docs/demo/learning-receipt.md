# Demo: maestro remembers its fixes, and proves it weekly

## What you see on your phone, once a week

This arrives in the Telegram home channel without anyone running anything.
Real output from a real run (a scratch database seeded with one week of history —
three problems paged you, then a week passed):

```
📚 Learning receipt
Problem classes that paged you last week: 3.
Since then: 1 fixed without you, 1 paged you again, 1 not seen.
Fixes replayed from memory this week: 1.
```

Reading it: the disk problem that paged you last week got fixed this week by a
skill maestro remembered, without paging you. The consumer problem paged you
again — maestro has not learned that one yet. The cert problem did not come back.

## What changed underneath

Before a non-crisis finding pages you, maestro now asks its own episode ledger:
"have I watched a skill fix this class of problem before?" If yes, it retries
that skill instead of paging. "Class of problem" means "Disk at 96%" and
"Disk at 97%" are the same problem — varying numbers do not fool it.

The proof it ran, straight from the test suite:

```
$ python3 -m pytest tests/ -q
28 passed, 261 warnings in 0.70s
```

Query the live database at any time for how many fixes came from memory:

```
$ sqlite3 ~/.maestro/experience_graph.db \
    "SELECT COUNT(*) FROM episodes WHERE json_extract(evidence,'$.source')='memory'"
```
