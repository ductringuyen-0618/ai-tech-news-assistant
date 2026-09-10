"""Keyword filter for the Learning feed (proposal 003).

The Learning tab surfaces items about AI *agent tooling* -- skills,
techniques, and setups a developer could add to their own agent
workflow this week -- as distinct from general AI/tech news. Two of the
three default sources in ``settings.learning_rss_sources`` are hnrss.org
query feeds that already filter by keyword server-side; this module adds
a second, content-level pass so a broader feed (e.g. the GitHub Blog's
AI & ML category, which also covers non-agent ML posts) doesn't flood
the tab with off-topic items.

Pure and dependency-free by design: no network/DB access, so it's cheap
to unit test in isolation and safe to call from any ingestion path.
"""

from __future__ import annotations

import re

# Each pattern matches a whole word/phrase, case-insensitively, against
# the combined title + content of a candidate item. Deliberately narrow:
# generic "AI" or "machine learning" mentions should NOT qualify on their
# own -- only content that is plausibly about agent tooling/technique.
_LEARNING_PATTERNS = [
    r"\bagents?\b",
    r"\bsub-?agents?\b",
    r"\bagentic\b",
    r"\bskill\s?(pack|s)?\b",
    r"\bmcp\b",
    r"\bmodel context protocol\b",
    r"\bclaude code\b",
    r"\bcursor\b",
    r"\bcopilot\b",
    r"\bautonomous cod(e|ing)\b",
    r"\bagent (setup|workflow|framework|harness)\b",
    r"\bprompt engineering\b",
    r"\btool[- ]use\b",
    r"\bworkflow automation\b",
]

LEARNING_KEYWORDS_RE = re.compile("|".join(_LEARNING_PATTERNS), re.IGNORECASE)


def is_learning_content(title: str, content: str = "") -> bool:
    """Return True if ``title``/``content`` look like agent-tooling content.

    Empty/whitespace-only input never matches (nothing to judge).
    """
    text = f"{title or ''} {content or ''}".strip()
    if not text:
        return False
    return bool(LEARNING_KEYWORDS_RE.search(text))
