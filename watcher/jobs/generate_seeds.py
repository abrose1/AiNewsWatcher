from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import select

from watcher.config import load_config
from watcher.db import session_scope
from watcher.judge import generate_seeds as judge_generate_seeds
from watcher.models import SeedItem

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_PATH = _REPO_ROOT / "config.yaml"


def _fetch_existing_keys() -> list[tuple[str, str]]:
    with session_scope() as session:
        rows = session.execute(select(SeedItem.category, SeedItem.key)).all()
        return [(r[0], r[1]) for r in rows]


def _format_entry(e: dict) -> str:
    cat = e["category"]
    key = e["key"]
    name = e["display_name"].replace('"', '\\"')
    notes = e.get("seed_notes", "").replace('"', '\\"')
    return f'  - {{ category: {cat}, key: {key}, display_name: "{name}", seed_notes: "{notes}" }}'


def _append_to_config(entries: list[dict]) -> None:
    block = [f"\n  # --- generated {date.today().isoformat()} ---"]
    block.extend(_format_entry(e) for e in entries)
    block.append("")
    with _CONFIG_PATH.open("a") as f:
        f.write("\n".join(block))


def run(count: int, category: str | None, dry_run: bool) -> int:
    cfg = load_config()
    existing = _fetch_existing_keys()
    log.info("Asking Claude for %s new seeds (existing: %s, category filter: %s)",
             count, len(existing), category or "any")

    entries = judge_generate_seeds(
        existing,
        api_key=cfg.secrets.anthropic_api_key,
        model=cfg.llm.model,
        count=count,
        category=category,
    )
    log.info("Claude returned %s candidate entries", len(entries))

    existing_set = set(existing)
    filtered: list[dict] = []
    for e in entries:
        if (e["category"], e["key"]) in existing_set:
            continue
        filtered.append(e)
    log.info("After dedupe: %s new entries", len(filtered))

    if not filtered:
        log.warning("No new entries to add.")
        return 0

    if dry_run:
        print("\n".join(_format_entry(e) for e in filtered))
        return 0

    _append_to_config(filtered)
    log.info("Appended %s entries to %s. Review, edit, then run: python -m watcher.jobs.sync_seed",
             len(filtered), _CONFIG_PATH)
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=25)
    parser.add_argument("--category", choices=["person", "company", "tool", "concept", "lab"], default=None)
    parser.add_argument("--dry-run", action="store_true", help="Print to stdout instead of appending to config.yaml")
    args = parser.parse_args()
    try:
        return run(count=args.count, category=args.category, dry_run=args.dry_run)
    except Exception:
        log.exception("generate_seeds failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
