# AI News Watcher

A small agent that sends one well-chosen WhatsApp message per day to keep me current on the AI industry — leaders, labs, tools, concepts. If something genuinely big breaks, that takes over the daily message instead. Replies are threaded: ask follow-up questions and Claude answers, with optional web search.

Architecture mirrors `release-watcher`: Railway cron → Python module → Postgres → Brave + Anthropic → Twilio. See `.claude/plans/i-want-to-brainstorm-delegated-thacker.md` for the full design rationale.

## Status

Live in production on Railway.

- **Inbound webhook**: https://ainewswatcher-production.up.railway.app/sms/inbound (Twilio "When a message comes in" URL for the WhatsApp Sender)
- **Daily fact crons**: `daily-fact-weekday` (Mon–Fri 6:45 PM MST), `daily-fact-weekend` (Sat–Sun 1:00 PM MST). Arizona = UTC−7 year-round.
- **Seeds in DB**: ~80; refill via `generate_seeds` when low.

## Tech stack

| Concern | Choice |
|---|---|
| Language | Python 3.11+ |
| HTTP | `httpx` |
| DB | Postgres (Railway in prod, local brew in dev), SQLAlchemy 2 + Alembic |
| Web search | Brave Search API |
| LLM | Anthropic SDK, Sonnet 4.6 |
| Messaging | Twilio WhatsApp (`whatsapp:` prefix on FROM/TO) |
| Web service | FastAPI + uvicorn (inbound webhook only) |
| Hosting | Railway (3 services: 2 crons + 1 always-on webhook) |

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

- `python -m watcher.jobs.daily_fact` — the one daily entrypoint. Flags: `--dry-run`, `--force-news`.
- `python -m watcher.jobs.sync_seed` — load `config.yaml` seed list into the DB.
- `python -m watcher.jobs.generate_seeds --count 25` — ask Claude for new seed entries, append to `config.yaml` for review, then re-run `sync_seed` to persist.

## Operational tips

**Trigger a one-off run against the Railway DB from your laptop:**

```bash
AI_NEWS_DATABASE_URL='postgresql+psycopg2://...kodama.proxy.rlwy.net.../railway' \
  python -m watcher.jobs.daily_fact
```

(Public Postgres URL is in Railway: Postgres service → Variables → `DATABASE_PUBLIC_URL`.)

**Inspect recent activity (Postgres):**

```sql
-- Last 5 sends + their text
SELECT sent_at, fact_kind, left(sms_body, 100) FROM sent_facts ORDER BY sent_at DESC LIMIT 5;

-- Cron run history (success / error)
SELECT run_at, status, fact_kind, left(detail, 100) FROM send_log ORDER BY run_at DESC LIMIT 10;

-- Current reply threads
SELECT root_sent_fact_id, jsonb_array_length(transcript) AS turns, last_message_at
FROM sms_threads ORDER BY last_message_at DESC LIMIT 5;
```

**Add more seeds when running low:**

```bash
python -m watcher.jobs.generate_seeds --count 25  # writes to config.yaml
# review the diff, then:
AI_NEWS_DATABASE_URL='...railway-public-url...' python -m watcher.jobs.sync_seed
```

## Inbound replies (stretch goal)

Replies on WhatsApp are threaded onto your most recent `sent_fact`. Claude has access to a `brave_search` tool (max 2 calls per reply) and answers in SMS-length form. The webhook (`watcher/web.py`) verifies Twilio signatures and dispatches the LLM work as a `BackgroundTasks` so the HTTP response returns immediately.

Whitelist: only the configured `SMS_TO_NUMBER` is allowed to trigger replies. Everything else is silently dropped.

## Schedule

Configured per-service in `railway.toml` / `railway.weekday.toml` / `railway.weekend.toml`. Arizona = MST year-round; cron expressions in UTC.

- Weekday cron: `45 1 * * 2-6` (Tue–Sat 01:45 UTC = Mon–Fri 6:45 PM MST)
- Weekend cron: `0 20 * * 0,6` (Sat–Sun 20:00 UTC = Sat–Sun 1:00 PM MST)
