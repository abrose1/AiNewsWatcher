from __future__ import annotations

import argparse
import logging
import random
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from watcher.config import load_config
from watcher.db import session_scope
from watcher.judge import (
    NewsPick,
    SeedCandidate,
    format_news_fact,
    format_seed_fact,
    is_takeover_worthy,
    pick_seed,
)
from watcher.models import SeedItem, SendLog, SentFact
from watcher.notify import send_sms
from watcher.sources.brave import SearchResult, normalize_url, search, search_many

log = logging.getLogger(__name__)

SLATE_SIZE = 20


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _scan_news(cfg, session) -> list[SearchResult]:
    candidates = search_many(
        cfg.news.standing_queries,
        api_key=cfg.secrets.brave_api_key,
        per_query=5,
    )
    cutoff = datetime.now(timezone.utc) - timedelta(hours=cfg.news.lookback_hours)
    fresh: list[SearchResult] = []
    for c in candidates:
        if c.published_at is None or c.published_at >= cutoff:
            fresh.append(c)

    sent_keys: set[str] = {
        row[0]
        for row in session.execute(
            select(SentFact.news_dedupe_key).where(SentFact.news_dedupe_key.is_not(None))
        ).all()
    }
    unsent = [c for c in fresh if normalize_url(c.url) not in sent_keys]
    return unsent[: cfg.news.max_candidates]


def _pull_slate(session) -> list[SeedCandidate]:
    used_ids = {row[0] for row in session.execute(
        select(SentFact.seed_item_id).where(SentFact.seed_item_id.is_not(None))
    ).all()}

    stmt = select(SeedItem)
    if used_ids:
        stmt = stmt.where(SeedItem.id.notin_(used_ids))
    stmt = stmt.order_by(func.random()).limit(SLATE_SIZE)
    items = session.execute(stmt).scalars().all()

    return [
        SeedCandidate(
            id=str(item.id),
            category=item.category,
            key=item.key,
            display_name=item.display_name,
            seed_notes=item.seed_notes,
        )
        for item in items
    ]


def _recent_categories(session, limit: int = 3) -> list[str]:
    rows = session.execute(
        select(SeedItem.category)
        .join(SentFact, SentFact.seed_item_id == SeedItem.id)
        .order_by(SentFact.sent_at.desc())
        .limit(limit)
    ).all()
    return [r[0] for r in rows]


def _augment_seed(item: SeedCandidate, cfg) -> list[SearchResult]:
    query = f"{item.display_name} {datetime.now().year}"
    return search(query, api_key=cfg.secrets.brave_api_key, count=5, freshness="pm")


def run(dry_run: bool = False, force_news: bool = False) -> int:
    cfg = load_config()

    with session_scope() as session:
        news_candidates = _scan_news(cfg, session)
        log.info("Found %s unsent news candidates", len(news_candidates))

        news_pick = None
        if news_candidates:
            news_pick = is_takeover_worthy(
                news_candidates,
                api_key=cfg.secrets.anthropic_api_key,
                model=cfg.llm.model,
                threshold_notes=cfg.llm.takeover_threshold_notes,
            )

        if force_news and news_candidates and not news_pick:
            top = news_candidates[0]
            news_pick = NewsPick(chosen_url=top.url, one_line_summary=top.title)

        if news_pick:
            log.info("Breaking news takeover: %s", news_pick.chosen_url)
            body, link = format_news_fact(
                news_pick,
                news_candidates,
                api_key=cfg.secrets.anthropic_api_key,
                model=cfg.llm.model,
            )
            fact_kind = "news"
            dedupe_key = normalize_url(news_pick.chosen_url)
            seed_id = None
        else:
            slate = _pull_slate(session)
            if not slate:
                msg = "Seed list exhausted — run generate_seeds"
                log.warning(msg)
                session.add(SendLog(status="skipped", detail=msg))
                return 0

            recent = _recent_categories(session)
            news_context = "\n".join(f"- {c.title}: {c.description}" for c in news_candidates[:5])
            pick = pick_seed(
                slate,
                api_key=cfg.secrets.anthropic_api_key,
                model=cfg.llm.model,
                recent_categories=recent,
                news_context=news_context,
            )
            if pick is None:
                chosen = random.choice(slate)
                log.warning("pick_seed returned None — falling back to random slate choice")
            else:
                chosen = next((s for s in slate if s.id == pick.chosen_id), random.choice(slate))
                log.info("Seed pick: %s (%s)", chosen.display_name, pick.rationale)

            context_results = _augment_seed(chosen, cfg)
            body, link = format_seed_fact(
                chosen,
                context_results,
                api_key=cfg.secrets.anthropic_api_key,
                model=cfg.llm.model,
            )
            fact_kind = "seed"
            dedupe_key = None
            seed_id = chosen.id

        log.info("Composed SMS (%s chars):\n%s", len(body), body)

        if dry_run:
            log.info("--dry-run: skipping Twilio send and DB writes")
            return 0

        sid = send_sms(
            body,
            to=cfg.sms.to_number,
            from_=cfg.sms.from_number,
            account_sid=cfg.secrets.twilio_account_sid,
            auth_token=cfg.secrets.twilio_auth_token,
        )

        session.add(
            SentFact(
                fact_kind=fact_kind,
                seed_item_id=seed_id,
                news_dedupe_key=dedupe_key,
                sms_body=body,
                link=link,
            )
        )
        session.add(SendLog(status="sent", fact_kind=fact_kind, twilio_sid=sid))

    return 0


def main() -> int:
    _setup_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Do everything except send SMS and write to DB")
    parser.add_argument("--force-news", action="store_true", help="Force a news takeover from the top candidate (test path)")
    args = parser.parse_args()
    try:
        return run(dry_run=args.dry_run, force_news=args.force_news)
    except Exception:
        log.exception("daily_fact failed")
        try:
            with session_scope() as session:
                session.add(SendLog(status="error", detail="see logs"))
        except Exception:
            log.exception("Failed to write error to send_log")
        return 1


if __name__ == "__main__":
    sys.exit(main())
