# AI News Watcher

Sends one well-chosen SMS per day to keep me current on the AI industry — leaders, labs, tools, concepts. If something genuinely big breaks, that takes over the daily text instead.

Architecture mirrors `release-watcher`: Railway cron → Python module → Postgres → Brave + Anthropic → Twilio. See `.claude/plans/i-want-to-brainstorm-delegated-thacker.md` for the full design.

## Quick start (local)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in secrets
alembic upgrade head
python -m watcher.jobs.sync_seed
python -m watcher.jobs.daily_fact --dry-run
```

## Jobs

- `python -m watcher.jobs.daily_fact` — the one daily cron entrypoint.
- `python -m watcher.jobs.sync_seed` — load `config.yaml` seed list into the DB.
- `python -m watcher.jobs.generate_seeds --count 25` — ask Claude for new seed entries, append to `config.yaml` for review.

## Schedule (Arizona, MST year-round)

- Weekdays 6:45 PM MST
- Weekends 1:00 PM MST

Configured in `railway.toml` (two cron services).
