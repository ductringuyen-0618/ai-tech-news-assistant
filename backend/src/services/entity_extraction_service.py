"""
Entity Extraction Service
=========================

Pulls named entities (companies, people, products, technologies) out of
article text using a local Ollama model and persists them to two tables:

* ``entities`` — one row per unique entity name, with a ``mention_count``
  rolled up across all articles.
* ``entity_mentions`` — one row per ``(article_id, entity_id)``, used to
  compute co-mention edges in the Knowledge Graph.

The service intentionally mirrors the project's existing raw-sqlite3 style
(see ``ArticleRepository`` and ``SettingsRepository``) rather than going
through SQLAlchemy sessions: the running backend never calls
``Base.metadata.create_all()`` and bootstraps tables lazily via
``CREATE TABLE IF NOT EXISTS``. The SQLAlchemy ``Entity`` and
``EntityMention`` models in :mod:`src.database.models` describe the same
shape for typing / future Alembic migrations.

Sanity rules
------------
1B-class models hallucinate aggressively. Every candidate entity must
survive these checks before being persisted:

* length >= 3 chars
* not in a small English stopword set
* not a single common-news token (``news``, ``tech``, ``new``, ...)
* not all-caps unless it's on a small acronym whitelist
* type is one of ``company | person | product | technology | other``

Failures are logged and dropped; the article is still marked done.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx

from ..core.config import get_settings


logger = logging.getLogger(__name__)


# Allowed entity types. Anything else is coerced to "other".
VALID_TYPES = {"company", "person", "product", "technology", "other"}

# Small English stopword set — short, hand-picked. We don't need full NLTK
# coverage; the 1B model rarely returns these but when it does they're
# obvious garbage.
COMMON_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "have", "has",
    "but", "not", "are", "was", "were", "you", "your", "they", "them",
    "his", "her", "him", "she", "all", "any", "can", "had", "his", "its",
    "may", "our", "out", "she", "use", "who", "why", "how", "now", "one",
    "two", "get", "got", "let", "see", "say", "said", "into", "more",
    "than", "then", "when", "what", "will", "would", "about", "after",
    "their", "there", "these", "those", "which", "while",
}

# Single-token "we know it's news fluff" reject set. Keep it tight — this
# is the difference between "AI" the topic getting filtered out (good)
# and "Apple" the company getting filtered out (bad).
SINGLE_NOISE_WORDS = {
    "news", "tech", "company", "new", "update", "today", "yesterday",
    "tomorrow", "report", "article", "story", "post", "blog", "video",
    "podcast", "newsletter", "trend", "trending", "feature", "service",
    "platform", "industry", "market", "users", "user", "data", "team",
    "world", "year", "week", "month", "day", "time", "people", "way",
    "thing", "things", "year", "years",
}

# All-caps tokens we're willing to keep as-is (acronyms with real meaning).
# Anything else that's all-caps and >= 5 chars is rejected as "probably
# the model SHOUTED at us".
COMMON_ACRONYMS = {
    "AI", "ML", "API", "CEO", "CTO", "CFO", "COO", "NASA", "FBI", "CIA",
    "IBM", "AWS", "GCP", "GPT", "GPU", "CPU", "TPU", "LLM", "NLP", "OCR",
    "RAG", "OS", "iOS", "EU", "UK", "US", "USA", "USSR", "UN", "WTO",
    "SaaS", "PaaS", "IaaS", "FAANG", "MAANG", "BERT", "LSTM", "CNN",
    "RNN", "GAN", "DEX", "CEX", "NFT", "DeFi", "DAO", "ICO",
}


def _is_likely_acronym(name: str) -> bool:
    """Cheap heuristic: short all-caps strings (<=4 chars) often are real
    acronyms even when not in our whitelist (DOJ, SEC, etc.)."""
    return len(name) <= 4 and name.isupper() and name.isalpha()


# ---------------------------------------------------------------------- #
#  Regex / dictionary fallback NER (design-review #3).
#  Used when Ollama is unreachable in production (e.g. Fly.io has no
#  local Ollama server). Quality is intentionally modest -- this is a
#  belt-and-braces path so the Knowledge tab on the portfolio site is
#  never an empty state. The model path remains primary.
# ---------------------------------------------------------------------- #

# Hand-curated dictionary mapping known names to their entity type.
# Order: companies > people > products > technologies (matters for the
# tie-breaker when a phrase could fit multiple buckets).
_KNOWN_COMPANIES = {
    "openai", "anthropic", "google", "alphabet", "microsoft", "apple",
    "meta", "facebook", "amazon", "nvidia", "intel", "amd", "tesla",
    "spacex", "netflix", "adobe", "ibm", "oracle", "salesforce",
    "stripe", "shopify", "twilio", "snowflake", "databricks", "github",
    "gitlab", "cloudflare", "vercel", "supabase", "atlassian", "asana",
    "notion", "figma", "canva", "linkedin", "twitter", "x corp",
    "tiktok", "bytedance", "uber", "lyft", "airbnb", "doordash",
    "instacart", "robinhood", "coinbase", "binance", "kraken",
    "palantir", "snowflake", "datadog", "mongodb", "elastic", "hashicorp",
    "redhat", "vmware", "broadcom", "qualcomm", "arm", "tsmc", "samsung",
    "huawei", "xiaomi", "sony", "lg", "panasonic", "dell", "hp",
    "lenovo", "asus", "acer", "razer", "logitech", "nintendo", "ea",
    "activision", "ubisoft", "epic games", "unity", "valve", "discord",
    "slack", "zoom", "dropbox", "box", "okta", "auth0", "twilio",
    "cisco", "juniper", "fortinet", "crowdstrike", "sentinelone",
    "mistral", "perplexity", "cohere", "hugging face", "huggingface",
    "stability ai", "midjourney", "runway", "scale ai", "character ai",
    "deepmind", "boston dynamics", "waymo", "cruise", "rivian", "lucid",
    "ford", "general motors", "toyota", "honda", "bmw", "mercedes",
    "porsche", "ferrari", "intel labs", "y combinator", "sequoia",
    "andreessen horowitz", "a16z", "lightspeed", "founders fund",
    "kleiner perkins", "accel", "benchmark", "general catalyst",
    "tiger global", "softbank", "vision fund", "berkshire hathaway",
    "blackrock", "vanguard", "jpmorgan", "goldman sachs", "morgan stanley",
    "bank of america", "wells fargo", "citi", "deutsche bank", "ubs",
    "credit suisse", "barclays", "hsbc", "santander", "bbva",
    "reddit", "pinterest", "snap", "snapchat", "spotify", "twitch",
    "youtube", "wikipedia", "wikimedia", "mozilla", "linux foundation",
    "apache foundation", "cncf", "kubernetes", "docker inc",
    "neuralink", "openai dev", "claude code", "amazon web services",
}

_KNOWN_PRODUCTS = {
    "gpt-3", "gpt-3.5", "gpt-4", "gpt-4o", "gpt-5", "chatgpt", "dall-e",
    "dall-e 2", "dall-e 3", "sora", "claude", "claude 3", "claude 3.5",
    "claude 3 opus", "claude 3 sonnet", "claude 3 haiku", "claude code",
    "gemini", "gemini 1.5", "gemini 2.0", "gemini pro", "gemini ultra",
    "bard", "llama", "llama 2", "llama 3", "llama 3.1", "llama 3.2",
    "mistral", "mistral 7b", "mixtral", "mixtral 8x7b", "phi",
    "phi-3", "iphone", "iphone 15", "iphone 16", "ipad", "macbook",
    "macbook pro", "apple watch", "vision pro", "airpods", "homepod",
    "android", "pixel", "pixel 8", "pixel 9", "galaxy", "galaxy s24",
    "windows", "windows 11", "office 365", "microsoft 365", "azure",
    "azure openai", "copilot", "github copilot", "microsoft copilot",
    "bing chat", "cursor", "tabnine", "codeium", "v0", "perplexity",
    "you.com", "kagi", "duckduckgo", "firefox", "chrome", "safari",
    "edge", "brave", "tor", "vivaldi", "vs code", "visual studio",
    "intellij", "pycharm", "rustrover", "webstorm", "android studio",
    "xcode", "playground", "tinygrad", "model context protocol", "mcp",
}

_KNOWN_TECHNOLOGIES = {
    "ai", "machine learning", "deep learning", "neural network",
    "transformer", "transformers", "rag", "retrieval augmented generation",
    "fine-tuning", "rlhf", "llm", "large language model", "embedding",
    "embeddings", "vector database", "computer vision", "nlp",
    "natural language processing", "reinforcement learning", "agi",
    "robotics", "autonomous driving", "self-driving", "blockchain",
    "cryptocurrency", "bitcoin", "ethereum", "solana", "web3",
    "nft", "defi", "smart contracts", "quantum computing", "5g", "6g",
    "edge computing", "iot", "internet of things", "ar", "vr",
    "augmented reality", "virtual reality", "mixed reality", "xr",
    "metaverse", "saas", "paas", "iaas", "kubernetes", "docker",
    "serverless", "microservices", "graphql", "rest api", "webhook",
    "oauth", "passkeys", "biometrics", "fido2", "zero trust",
    "ransomware", "phishing", "ddos", "sql injection", "xss",
    "cuda", "rocm", "pytorch", "tensorflow", "jax", "keras", "scikit-learn",
    "rust", "go", "python", "typescript", "javascript", "wasm",
    "webassembly", "react", "vue", "svelte", "next.js", "remix",
    "nuxt", "fastapi", "flask", "django", "spring boot", "node.js",
    "deno", "bun", "postgresql", "mongodb", "redis", "elasticsearch",
    "kafka", "rabbitmq", "apache spark", "hadoop", "airflow", "dbt",
}


def _regex_extract_entities(text: str, max_entities: int = 12) -> List[Tuple[str, str]]:
    """Cheap fallback NER used when Ollama is unreachable.

    Strategy:
      1. Pull all title-cased phrases (one to four consecutive Capitalised
         tokens). This catches "OpenAI", "Sam Altman", "GPT-4", "Vision Pro".
      2. Lower-case the phrase and look it up in our four dictionaries.
         Order: company > person > product > technology > other. People
         are inferred via the "two title-cased tokens not in any dict"
         heuristic so the corpus's frequent founder/CEO names land in
         the graph even if we don't pre-list them.
      3. Apply the existing sanity rules (stopwords, single-noise words,
         all-caps non-acronym filter) before returning.

    The returned list is deduped (case-insensitive) and capped at
    ``max_entities`` to keep the per-article output comparable to what
    the Ollama prompt produces.
    """
    if not text:
        return []

    # Title-cased phrase matcher. Tokens may include digits / hyphens
    # (so "GPT-4" and "Llama 3" survive). The look-ahead caps the run
    # at four tokens so we don't grab a whole sentence.
    pattern = re.compile(
        r"\b([A-Z][A-Za-z0-9\-]+(?:\s+[A-Z][A-Za-z0-9\-]+){0,3})\b"
    )

    candidates: List[str] = []
    seen_lower: set = set()
    for match in pattern.finditer(text):
        phrase = match.group(1).strip()
        if not phrase or len(phrase) < 3:
            continue
        key = phrase.lower()
        if key in seen_lower:
            continue
        seen_lower.add(key)
        candidates.append(phrase)

    out: List[Tuple[str, str]] = []
    for phrase in candidates:
        lo = phrase.lower()
        # Dictionary lookups, ordered by priority.
        if lo in _KNOWN_COMPANIES:
            ent_type = "company"
        elif lo in _KNOWN_PRODUCTS:
            ent_type = "product"
        elif lo in _KNOWN_TECHNOLOGIES:
            ent_type = "technology"
        else:
            tokens = phrase.split()
            # Two- or three-token phrase, both/all title-cased, not a
            # single common noun -- almost always a person's name in
            # tech-news copy (e.g. "Sam Altman", "Sundar Pichai").
            looks_like_person = (
                2 <= len(tokens) <= 3
                and all(t[0:1].isupper() for t in tokens)
                and not any(t.lower() in COMMON_STOPWORDS for t in tokens)
                and not any(t.lower() in SINGLE_NOISE_WORDS for t in tokens)
            )
            if looks_like_person:
                ent_type = "person"
            else:
                # Skip lone capitalised nouns that aren't in any dict.
                # Returning them as "other" floods the graph with sentence
                # heads ("The", "Today", lone "AI"). Better to drop.
                continue

        # Apply the sanity rules (re-use the existing filters by
        # constructing a {"name", "type"} shaped dict and round-tripping
        # through ``_sanitize_candidate`` -- the caller wires this up).
        if lo in COMMON_STOPWORDS or lo in SINGLE_NOISE_WORDS:
            continue
        if (
            phrase.isalpha()
            and phrase.isupper()
            and len(phrase) >= 5
            and phrase not in COMMON_ACRONYMS
            and not _is_likely_acronym(phrase)
        ):
            continue

        out.append((phrase, ent_type))
        if len(out) >= max_entities:
            break

    return out


class EntityExtractionService:
    """
    Extract named entities from article text via Ollama and persist them.

    Construction is cheap (no I/O). All work happens inside
    ``process_article`` / ``extract_entities``. Failures during a single
    article are logged and swallowed so the orchestrator's
    summarization loop doesn't blow up because the NER call timed out.
    """

    # We send at most this many chars to Ollama. 1B models lose the plot
    # past a few thousand tokens and the prompt is mostly the lede anyway.
    MAX_PROMPT_CHARS = 4_000

    # Process-wide latch. When the first ``_call_ollama`` raises a
    # connect-refused / DNS-failure error (e.g. Fly.io with no local
    # Ollama), every subsequent ``extract_entities`` call short-circuits
    # to the regex fallback. Saves us 80 * <timeout-seconds> of cold
    # connect waits on a per-machine cold start.
    _ollama_unreachable: bool = False

    # NOTE: Prompt is built via simple string concatenation (not str.format)
    # because the JSON example contains literal '{' and '}' characters that
    # would otherwise be interpreted as format placeholders.
    PROMPT_PREFIX = (
        "Extract named entities (companies, people, products, technologies) "
        "from the text below. Return ONLY a JSON array, with no preamble, "
        "no markdown fences, no commentary. Each item must have exactly two "
        "string fields: \"name\" and \"type\", where type is one of "
        "\"company\", \"person\", \"product\", \"technology\". Skip generic "
        "words like \"AI\", \"news\", \"company\". Limit to at most 12 entities.\n"
        "\n"
        "Example output:\n"
        "[{\"name\": \"OpenAI\", \"type\": \"company\"}, "
        "{\"name\": \"Sam Altman\", \"type\": \"person\"}, "
        "{\"name\": \"GPT-4\", \"type\": \"product\"}]\n"
        "\n"
        "Text:\n"
    )
    PROMPT_SUFFIX = "\n\nJSON array:"

    def __init__(
        self,
        db_path: Optional[str] = None,
        ollama_host: Optional[str] = None,
        ollama_model: Optional[str] = None,
        ollama_timeout: Optional[int] = None,
    ):
        settings = get_settings()
        raw_path = db_path or getattr(
            settings, "sqlite_database_path", "./news.db"
        )
        # Accept either bare path or "sqlite:///..." URL form.
        if raw_path.startswith("sqlite:///"):
            raw_path = raw_path.replace("sqlite:///", "")
        self.db_path: str = raw_path

        self.base_url: str = (
            ollama_host or getattr(settings, "ollama_host", "http://localhost:11434")
        ).rstrip("/")
        self.model: str = ollama_model or getattr(
            settings, "ollama_model", "llama3.2:1b"
        )
        self.timeout: int = ollama_timeout or getattr(
            settings, "ollama_timeout", 60
        )

        self._ensure_tables_exist()

    # ------------------------------------------------------------------ #
    #  Schema bootstrap
    # ------------------------------------------------------------------ #

    def _ensure_tables_exist(self) -> None:
        """Create the entity tables if they're missing.

        Mirrors the bootstrap pattern in ``ArticleRepository`` and
        ``SettingsRepository``.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS entities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    type TEXT NOT NULL,
                    mention_count INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS entity_mentions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_id INTEGER NOT NULL,
                    entity_id INTEGER NOT NULL,
                    position INTEGER,
                    UNIQUE(article_id, entity_id),
                    FOREIGN KEY(article_id) REFERENCES articles(id) ON DELETE CASCADE,
                    FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_entities_mention_count "
                "ON entities(mention_count)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_entity_mentions_article "
                "ON entity_mentions(article_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_entity_mentions_entity "
                "ON entity_mentions(entity_id)"
            )

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    async def extract_entities(
        self, article_id: int, content: str
    ) -> List[Tuple[str, str]]:
        """
        Call Ollama to extract entities from ``content``.

        Returns a list of ``(name, type)`` tuples that have already passed
        the sanity filter. Returns an empty list (not None) on any error
        — the caller doesn't need to know whether the model timed out
        or just returned junk.
        """
        if not content or not content.strip():
            return []

        snippet = content[: self.MAX_PROMPT_CHARS]
        prompt = self.PROMPT_PREFIX + snippet + self.PROMPT_SUFFIX

        # Fast path: if a previous call already proved Ollama is
        # unreachable for this process, skip the network round-trip
        # and go straight to regex extraction.
        if EntityExtractionService._ollama_unreachable:
            return _regex_extract_entities(snippet)

        # Try Ollama first. If the call fails (connection refused,
        # timeout, model not pulled, ...) OR returns junk, fall through
        # to the regex/dictionary path so the Knowledge graph isn't an
        # empty state on deployments without a local Ollama (design-
        # review #3 -- Fly.io has no Ollama; see
        # _regex_extract_entities for the fallback shape).
        try:
            raw = await self._call_ollama(prompt)
        except Exception as exc:  # noqa: BLE001 - last-resort
            EntityExtractionService._ollama_unreachable = True
            logger.warning(
                "Ollama NER call failed for article %s: %s -- "
                "switching to regex fallback for the remainder of this "
                "process",
                article_id,
                exc,
            )
            return _regex_extract_entities(snippet)

        parsed = self._parse_ollama_response(raw)
        if parsed is None:
            logger.info(
                "Article %s: Ollama returned non-JSON, falling back to regex. "
                "Response head=%r",
                article_id,
                (raw or "")[:120],
            )
            return _regex_extract_entities(snippet)

        cleaned: List[Tuple[str, str]] = []
        seen: set = set()
        for item in parsed:
            pair = self._sanitize_candidate(item)
            if pair is None:
                continue
            key = pair[0].lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(pair)

        logger.debug(
            "Article %s: kept %d/%d candidate entities",
            article_id,
            len(cleaned),
            len(parsed),
        )
        return cleaned

    async def process_article(self, article_id: int) -> int:
        """
        End-to-end: read the article, run extraction, persist results.

        Idempotent: existing mentions for this article are deleted first,
        then re-inserted. Entity-level ``mention_count`` is decremented
        for the deleted mentions and re-incremented for the new ones, so
        re-running on the same article doesn't inflate counts.

        Returns the number of entities persisted for this article.
        """
        try:
            content = self._fetch_article_text(article_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Could not load article %s for entity extraction: %s",
                article_id,
                exc,
            )
            return 0

        if not content:
            return 0

        entities = await self.extract_entities(article_id, content)
        if not entities:
            # Still clear any stale mentions so re-extraction is clean.
            self._reset_article_mentions(article_id)
            return 0

        return self._persist_entities(article_id, entities)

    # ------------------------------------------------------------------ #
    #  Ollama call + parsing
    # ------------------------------------------------------------------ #

    async def _call_ollama(self, prompt: str) -> str:
        payload: Dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,  # NER wants determinism, not creativity
                "top_p": 0.9,
                "num_predict": 512,
            },
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/api/generate", json=payload
            )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Ollama returned {resp.status_code}: {resp.text[:200]}"
            )
        data = resp.json()
        return (data.get("response") or "").strip()

    def _parse_ollama_response(
        self, text: str
    ) -> Optional[List[Dict[str, Any]]]:
        """Return a list of dicts, or None on any parse failure.

        Accepts three shapes (1B-class models drift between them):

        1. A clean JSON array: ``[{...}, {...}]``
        2. NDJSON: one ``{...}`` per line
        3. A messy mix wrapped in markdown fences

        We try each in turn. ``None`` only on total failure.
        """
        if not text:
            return None

        # Strip common code-fence wrappings.
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[a-zA-Z0-9]*\n?", "", cleaned)
            cleaned = re.sub(r"\n?```\s*$", "", cleaned)

        # Shape 1: full JSON array.
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                parsed = json.loads(cleaned[start : end + 1])
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass

        # Shape 2 / 3: harvest every top-level JSON object we can find.
        # Greedy regex over balanced single-level braces — good enough for
        # ``{"name": "...", "type": "..."}`` style objects, which is all
        # we ask the model for.
        items: List[Dict[str, Any]] = []
        for match in re.finditer(r"\{[^{}]*\}", cleaned):
            try:
                obj = json.loads(match.group(0))
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                items.append(obj)

        if items:
            return items
        return None

    def _sanitize_candidate(
        self, item: Any
    ) -> Optional[Tuple[str, str]]:
        """Apply the sanity rules. Returns ``(name, type)`` or ``None``."""
        if not isinstance(item, dict):
            return None
        raw_name = item.get("name")
        raw_type = item.get("type")
        if not isinstance(raw_name, str) or not isinstance(raw_type, str):
            return None

        name = raw_name.strip()
        if not name:
            return None
        # Strip common quote/punctuation noise the model adds.
        name = name.strip("\"'`.,;:()[]{}")
        if not name:
            return None

        # Length rule.
        if len(name) < 3:
            return None

        # Stopwords / common single-word noise.
        lowered = name.lower()
        if lowered in COMMON_STOPWORDS:
            return None
        if lowered in SINGLE_NOISE_WORDS:
            return None

        # All-caps non-acronym filter. We only reject when the string is
        # all-caps AND >= 5 chars AND not on the whitelist; short all-caps
        # tokens (DOJ, GPU) are preserved.
        if (
            name.isalpha()
            and name.isupper()
            and len(name) >= 5
            and name not in COMMON_ACRONYMS
            and not _is_likely_acronym(name)
        ):
            return None

        # Type normalisation. Anything outside the whitelist becomes "other".
        type_clean = raw_type.strip().lower()
        if type_clean not in VALID_TYPES:
            type_clean = "other"

        return name, type_clean

    # ------------------------------------------------------------------ #
    #  DB I/O
    # ------------------------------------------------------------------ #

    def _fetch_article_text(self, article_id: int) -> str:
        """Pull article body for extraction. Falls back to summary then title."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT title, content, summary FROM articles WHERE id = ?",
                (article_id,),
            ).fetchone()
        if not row:
            return ""
        # Prefer summary (already distilled, less noise) then content then
        # title alone. Including the title gives the model a strong hint
        # about the lead actors of the story.
        title = (row["title"] or "").strip()
        body = (row["summary"] or "").strip() or (row["content"] or "").strip()
        if title and body:
            return f"{title}\n\n{body}"
        return body or title

    def _reset_article_mentions(self, article_id: int) -> None:
        """Remove existing mentions for this article and decrement entity counts."""
        with sqlite3.connect(self.db_path) as conn:
            existing = conn.execute(
                "SELECT entity_id FROM entity_mentions WHERE article_id = ?",
                (article_id,),
            ).fetchall()
            if not existing:
                return
            entity_ids = [r[0] for r in existing]
            conn.execute(
                "DELETE FROM entity_mentions WHERE article_id = ?",
                (article_id,),
            )
            for eid in entity_ids:
                conn.execute(
                    "UPDATE entities SET mention_count = "
                    "MAX(mention_count - 1, 0) WHERE id = ?",
                    (eid,),
                )

    def _persist_entities(
        self, article_id: int, entities: Iterable[Tuple[str, str]]
    ) -> int:
        """Upsert entities + mentions for one article. Returns count persisted."""
        # Reset first so the run is idempotent.
        self._reset_article_mentions(article_id)

        persisted = 0
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            for position, (name, type_) in enumerate(entities):
                # Look up existing entity by case-insensitive name match,
                # but persist with the casing we received (good enough for v1).
                row = conn.execute(
                    "SELECT id, mention_count FROM entities "
                    "WHERE LOWER(name) = LOWER(?)",
                    (name,),
                ).fetchone()
                if row is not None:
                    entity_id = row["id"]
                    conn.execute(
                        "UPDATE entities SET mention_count = mention_count + 1 "
                        "WHERE id = ?",
                        (entity_id,),
                    )
                else:
                    cur = conn.execute(
                        "INSERT INTO entities (name, type, mention_count) "
                        "VALUES (?, ?, 1)",
                        (name, type_),
                    )
                    entity_id = cur.lastrowid

                # Insert the mention. If the (article, entity) pair already
                # exists (shouldn't, since we just reset), the unique
                # constraint kicks in and we silently skip.
                try:
                    conn.execute(
                        "INSERT INTO entity_mentions "
                        "(article_id, entity_id, position) VALUES (?, ?, ?)",
                        (article_id, entity_id, position),
                    )
                    persisted += 1
                except sqlite3.IntegrityError:
                    # Reverse the bump we did above so counts stay honest.
                    conn.execute(
                        "UPDATE entities SET mention_count = "
                        "MAX(mention_count - 1, 0) WHERE id = ?",
                        (entity_id,),
                    )
        return persisted
