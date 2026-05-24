from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from anthropic import Anthropic

from watcher.sources.brave import SearchResult

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class NewsPick:
    chosen_url: str
    one_line_summary: str


@dataclass(frozen=True)
class SeedCandidate:
    id: str
    category: str
    key: str
    display_name: str
    seed_notes: str


@dataclass(frozen=True)
class SeedPick:
    chosen_id: str
    rationale: str


_FORMAT_EXAMPLES = """\
Examples of the voice we want:

- "Liang Wenfeng — DeepSeek founder, ex-quant-fund manager. Their R1 model matched OpenAI's o1 reasoning at a fraction of the training cost, jolting markets in early 2025."

- "Mira Murati was OpenAI's CTO during the GPT-4 era. After the 2023 board crisis she eventually left and founded Thinking Machines Lab, which raised at a multi-billion valuation pre-product."

- "MCP (Model Context Protocol): Anthropic's open standard for connecting LLMs to tools and data — think 'USB for AI agents.' Adopted across OpenAI, Google, and most major IDEs."

- "Mixture of Experts (MoE): an architecture where each token routes to a few specialist sub-networks instead of activating the whole model. It's why DeepSeek and Mixtral train and serve cheaply at large parameter counts."

Voice rules:
- 2-3 short sentences, hard cap ~280 chars.
- Lead with the subject. No greeting.
- One identity sentence + one current/non-obvious detail.
- Plain text. No emoji.
"""


def _client(api_key: str) -> Anthropic:
    return Anthropic(api_key=api_key)


def _extract_json(text: str) -> dict | None:
    """Pull the first JSON object out of model output, tolerant of code fences."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def is_takeover_worthy(
    candidates: list[SearchResult],
    *,
    api_key: str,
    model: str,
    threshold_notes: str,
) -> NewsPick | None:
    """Return a NewsPick if any candidate is genuinely big news today, else None."""
    if not candidates:
        return None

    listed = "\n".join(
        f"- url: {c.url}\n  title: {c.title}\n  desc: {c.description}" for c in candidates
    )
    prompt = f"""You are deciding whether any of today's AI news items is big enough to be the single thing Andrew should hear about today, in lieu of a curated daily fact.

Threshold guidance:
{threshold_notes}

Candidates (last 24h):
{listed}

Return JSON:
- If nothing meets the bar: {{"takeover": false}}
- If one item meets the bar: {{"takeover": true, "chosen_url": "...", "one_line_summary": "<one short sentence>"}}

Be strict. Most days nothing should meet the bar. Reply with JSON only, no prose.
"""

    resp = _client(api_key).messages.create(
        model=model,
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text if resp.content else ""
    data = _extract_json(text) or {}
    if not data.get("takeover"):
        return None
    url = data.get("chosen_url")
    summary = data.get("one_line_summary", "").strip()
    if not url or not summary:
        return None
    return NewsPick(chosen_url=url, one_line_summary=summary)


def pick_seed(
    slate: list[SeedCandidate],
    *,
    api_key: str,
    model: str,
    recent_categories: list[str],
    news_context: str = "",
) -> SeedPick | None:
    """Choose the most-interesting unsent seed for today from the slate."""
    if not slate:
        return None

    listed = "\n".join(
        f"- id: {s.id}\n  category: {s.category}\n  display_name: {s.display_name}\n  notes: {s.seed_notes}"
        for s in slate
    )
    recent = ", ".join(recent_categories) or "(none)"
    news_block = f"\nRecent news scan context (may or may not be relevant):\n{news_context}\n" if news_context else ""

    prompt = f"""You are picking the single most interesting daily fact for Andrew today, from this slate of unsent seed items.

Criteria:
- Pick whichever entry would make the most interesting daily SMS today.
- Prefer current relevance — if recent news touches one of these entries, that pairs well.
- Avoid clustering categories day-over-day. Recent sent categories were: {recent}.

Slate:
{listed}
{news_block}
Return JSON: {{"chosen_id": "<id from slate>", "rationale": "<one short sentence on why this one today>"}}.
Reply with JSON only, no prose.
"""

    resp = _client(api_key).messages.create(
        model=model,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text if resp.content else ""
    data = _extract_json(text) or {}
    chosen = data.get("chosen_id")
    if not chosen:
        return None
    return SeedPick(chosen_id=chosen, rationale=data.get("rationale", ""))


def format_seed_fact(
    item: SeedCandidate,
    context_results: list[SearchResult],
    *,
    api_key: str,
    model: str,
) -> tuple[str, str | None]:
    """Compose the SMS body for a seed pick. Returns (body, optional_link)."""
    context_block = "\n".join(
        f"- {r.title} ({r.url}): {r.description}" for r in context_results[:5]
    ) or "(no fresh search results found)"

    prompt = f"""Write today's daily AI fact SMS for Andrew.

Subject: {item.display_name}
Category: {item.category}
Notes about why this matters: {item.seed_notes}

Recent web context (may help with current/non-obvious detail):
{context_block}

{_FORMAT_EXAMPLES}

Output JSON: {{"body": "<the SMS text>", "link": "<url or null if no strong link>"}}.
Reply with JSON only.
"""

    resp = _client(api_key).messages.create(
        model=model,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text if resp.content else ""
    data = _extract_json(text) or {}
    body = (data.get("body") or "").strip()
    link = data.get("link") or None
    if not body:
        body = f"{item.display_name}: {item.seed_notes}"
    return body, link


def format_news_fact(
    pick: NewsPick,
    candidates: list[SearchResult],
    *,
    api_key: str,
    model: str,
) -> tuple[str, str]:
    """Compose the SMS body for a breaking-news takeover. Returns (body, link)."""
    chosen = next((c for c in candidates if c.url == pick.chosen_url), None)
    title = chosen.title if chosen else ""
    desc = chosen.description if chosen else ""

    prompt = f"""Write today's breaking-news SMS for Andrew. Prefix with "Breaking News:" exactly.

Chosen story:
- title: {title}
- url: {pick.chosen_url}
- description: {desc}
- one-line summary (already drafted by upstream judge): {pick.one_line_summary}

{_FORMAT_EXAMPLES}

Additional rule: this is a news takeover, so always include the URL at the end of the body.
Output JSON: {{"body": "<the SMS text including 'Breaking News:' prefix and the URL>"}}.
Reply with JSON only.
"""

    resp = _client(api_key).messages.create(
        model=model,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text if resp.content else ""
    data = _extract_json(text) or {}
    body = (data.get("body") or "").strip()
    if not body:
        body = f"Breaking News: {pick.one_line_summary} {pick.chosen_url}"
    return body, pick.chosen_url


def generate_seeds(
    existing_keys: list[tuple[str, str]],
    *,
    api_key: str,
    model: str,
    count: int,
    category: str | None = None,
) -> list[dict]:
    """Ask Claude for N new seed entries that don't duplicate existing ones."""
    existing_listed = "\n".join(f"- {cat}/{key}" for cat, key in existing_keys) or "(none yet)"
    cat_filter = (
        f"All entries must be category={category}."
        if category
        else "Mix across all categories: person, company, tool, concept, lab."
    )

    prompt = f"""Propose {count} new AI-industry seed entries that an intelligent person tracking the field should know about.

{cat_filter}

Do NOT duplicate any of these existing entries:
{existing_listed}

Aim for breadth. Include researchers (not just CEOs), non-US labs (French, Chinese, Israeli, UK), specific technical concepts (training tricks, eval benchmarks, inference optimizations), niche-but-influential tools, and recently-founded companies. Famous names are fine but don't only suggest household names.

For each entry, `seed_notes` should be one short line explaining in plain English why this matters to someone tracking the AI industry.

Output JSON: {{"entries": [{{"category": "...", "key": "kebab-case-slug", "display_name": "...", "seed_notes": "..."}}, ...]}}.
Reply with JSON only.
"""

    resp = _client(api_key).messages.create(
        model=model,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text if resp.content else ""
    data = _extract_json(text) or {}
    entries = data.get("entries", [])
    return [e for e in entries if all(k in e for k in ("category", "key", "display_name"))]
