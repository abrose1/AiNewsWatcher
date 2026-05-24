from __future__ import annotations

import logging
import sys

from sqlalchemy import select

from watcher.config import load_config
from watcher.db import session_scope
from watcher.models import SeedItem

log = logging.getLogger(__name__)


def run() -> int:
    cfg = load_config()
    added = 0
    updated = 0

    with session_scope() as session:
        existing = {
            (s.category, s.key): s
            for s in session.execute(select(SeedItem)).scalars().all()
        }

        for spec in cfg.seed_items:
            row = existing.get((spec.category, spec.key))
            if row is None:
                session.add(
                    SeedItem(
                        category=spec.category,
                        key=spec.key,
                        display_name=spec.display_name,
                        seed_notes=spec.seed_notes,
                    )
                )
                added += 1
            else:
                changed = False
                if row.display_name != spec.display_name:
                    row.display_name = spec.display_name
                    changed = True
                if row.seed_notes != spec.seed_notes:
                    row.seed_notes = spec.seed_notes
                    changed = True
                if changed:
                    updated += 1

    log.info("sync_seed: %s added, %s updated", added, updated)
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        return run()
    except Exception:
        log.exception("sync_seed failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
