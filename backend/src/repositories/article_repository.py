"""
Article Repository
================

Repository for managing article data in SQLite database.
"""

import sqlite3
import json

from ..models.article import Article, ArticleUpdate
from ..core.exceptions import DatabaseError, NotFoundError
from ..services.front_page_precompute import _credibility_score


class ArticleRepository:
    """Repository for article data access operations."""
    
    def __init__(self, db_path: str):
        """Initialize repository with database path."""
        # Handle both SQLAlchemy URL format and direct file paths
        if db_path.startswith('sqlite:///'):
            # Convert SQLAlchemy format to file path
            # sqlite:///:memory: -> :memory:
            # sqlite:///./path/to/db.db -> ./path/to/db.db
            self.db_path = db_path.replace('sqlite:///', '')
        else:
            self.db_path = db_path
        self._ensure_tables_exist()
    
    def _ensure_tables_exist(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    url TEXT UNIQUE NOT NULL,
                    content TEXT,
                    summary TEXT,
                    author TEXT,
                    published_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    source TEXT,
                    categories TEXT,
                    metadata TEXT,
                    is_archived BOOLEAN DEFAULT FALSE,
                    view_count INTEGER DEFAULT 0,
                    embedding_generated BOOLEAN DEFAULT FALSE,
                    summary_generated BOOLEAN DEFAULT FALSE
                )
            """)
            # Lightweight migration: older DBs may be missing summary_generated.
            existing_cols = {
                row[1]
                for row in conn.execute("PRAGMA table_info(articles)").fetchall()
            }
            if "summary_generated" not in existing_cols:
                conn.execute(
                    "ALTER TABLE articles ADD COLUMN summary_generated "
                    "BOOLEAN DEFAULT FALSE"
                )
            if "summary" not in existing_cols:
                conn.execute("ALTER TABLE articles ADD COLUMN summary TEXT")
            if "image_url" not in existing_cols:
                # Hero/thumbnail URL extracted from RSS feed media tags.
                # Frontend NewsCard falls back to a placeholder when null.
                conn.execute("ALTER TABLE articles ADD COLUMN image_url TEXT")
            # The legacy SQLAlchemy ORM models (still used by
            # `src/services/ingestion_service.py`) expect these extra columns
            # to exist on the `articles` table. We additively bring them in
            # here so both code paths (raw-sqlite3 news API + SQLAlchemy
            # ingestion) can talk to one schema. None of them are required
            # by ArticleRepository itself -- they just stop ingestion from
            # blowing up with "no such column: articles.language".
            if "language" not in existing_cols:
                conn.execute("ALTER TABLE articles ADD COLUMN language TEXT DEFAULT 'en'")
            if "word_count" not in existing_cols:
                conn.execute("ALTER TABLE articles ADD COLUMN word_count INTEGER")
            if "reading_time" not in existing_cols:
                conn.execute("ALTER TABLE articles ADD COLUMN reading_time INTEGER")
            if "is_featured" not in existing_cols:
                conn.execute(
                    "ALTER TABLE articles ADD COLUMN is_featured BOOLEAN DEFAULT FALSE"
                )
            if "sentiment_score" not in existing_cols:
                conn.execute("ALTER TABLE articles ADD COLUMN sentiment_score REAL")
            if "source_id" not in existing_cols:
                conn.execute("ALTER TABLE articles ADD COLUMN source_id INTEGER")
    
    def _row_to_article(self, row):
        if not row:
            return None

        # Tolerate two on-disk schemas:
        #   A) raw-sqlite3 schema (this file's CREATE TABLE):
        #        source TEXT, categories TEXT (JSON), no language, no source_id
        #   B) SQLAlchemy ORM schema (src/database/models.py):
        #        source_id INTEGER FK, language TEXT, no source TEXT,
        #        categories live in a separate M2M table
        # When ingestion_service runs first on a fresh Fly volume it creates
        # schema B. The news API has historically expected schema A. Rather
        # than fight the schema war we just read defensively here so the
        # endpoint never 500s on a column-doesn't-exist error.
        def _safe(col, default=None):
            try:
                return row[col]
            except (IndexError, KeyError):
                return default

        # Categories may be a JSON string (schema A) or absent (schema B --
        # would need a JOIN to recover, which we skip for now).
        raw_categories = _safe("categories")
        categories = None
        if raw_categories:
            try:
                categories = json.loads(raw_categories)
            except (json.JSONDecodeError, TypeError):
                categories = None

        raw_metadata = _safe("metadata")
        metadata = None
        if raw_metadata:
            try:
                metadata = json.loads(raw_metadata)
            except (json.JSONDecodeError, TypeError):
                metadata = None

        # schema A has 'source' TEXT; schema B has 'source_id' INTEGER FK.
        # If only source_id is present we surface it as a string so the
        # frontend has SOMETHING to render in the "source" chip.
        source_value = _safe("source") or (
            f"source#{row['source_id']}" if _safe("source_id") is not None else None
        )

        return Article(
            id=row["id"],
            title=row["title"],
            url=row["url"],
            content=_safe("content"),
            summary=_safe("summary"),
            source=source_value,
            # Reuses the same per-source credibility tiering as the front
            # page precompute pipeline (front_page_precompute._credibility_score)
            # so the "credibility badge" is a real, consistent-across-the-app
            # number instead of the old hardcoded 85% shown on every card.
            credibility_score=_credibility_score(source_value or ""),
            author=_safe("author"),
            published_at=_safe("published_at"),
            categories=categories,
            metadata=metadata,
            image_url=_safe("image_url"),
            created_at=_safe("created_at"),
            updated_at=_safe("updated_at"),
            is_archived=bool(_safe("is_archived") or False),
            view_count=_safe("view_count") or 0,
            embedding_generated=bool(_safe("embedding_generated") or False),
            summary_generated=bool(_safe("summary_generated") or False),
            published_date=_safe("published_at"),
        )
    
    async def create(self, article):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            existing = conn.execute("SELECT id FROM articles WHERE url = ?", (article.url,)).fetchone()
            if existing:
                raise DatabaseError(f"Article with URL already exists: {article.url}")
            cursor = conn.execute("""
                INSERT INTO articles (title, url, content, author, published_at, source, categories, metadata) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (article.title, article.url, article.content, 
                  getattr(article, "author", None), 
                  getattr(article, "published_at", None) or getattr(article, "published_date", None), 
                  article.source, 
                  json.dumps(getattr(article, "categories", None)) if getattr(article, "categories", None) else None, 
                  json.dumps(getattr(article, "metadata", None)) if getattr(article, "metadata", None) else None))
            article_id = cursor.lastrowid
            row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
            return self._row_to_article(row)
    
    async def get_by_id(self, article_id: int):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            # Only get non-archived articles and increment view count
            conn.execute("UPDATE articles SET view_count = view_count + 1 WHERE id = ? AND is_archived = FALSE", (article_id,))
            row = conn.execute("SELECT * FROM articles WHERE id = ? AND is_archived = FALSE", (article_id,)).fetchone()
            if not row:
                raise NotFoundError(f"Article with id {article_id} not found")
            return self._row_to_article(row)
    
    async def get_summary_only(self, article_id: int):
        """Fast cache-lookup helper: returns ``articles.summary`` for the
        given id, or ``None`` if no row matches or the column is empty.

        This is the read-side primitive used by the ``summarize_article``
        agent skill (Mission 2, M2) before deciding whether to call the
        LLM. It is deliberately cheap: a single ``SELECT summary`` with no
        view-count side-effect, so it's safe to call from inside a tight
        agent loop.
        """
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT summary FROM articles WHERE id = ?",
                (article_id,),
            ).fetchone()
        if not row:
            return None
        summary = row[0]
        if summary is None:
            return None
        if isinstance(summary, str) and not summary.strip():
            return None
        return summary

    async def get_content_only(self, article_id: int):
        """Read the article body for summarization.

        Mirrors :meth:`get_summary_only` but returns the ``content`` field
        (full body), or ``None`` when the article has no usable body.
        Used by ``summarize_article`` on cache miss to feed the LLM.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT title, content FROM articles WHERE id = ?",
                (article_id,),
            ).fetchone()
        if not row:
            return None
        body = (row["content"] or "").strip()
        if not body:
            # Fall back to title alone -- better than nothing for short feed items.
            title = (row["title"] or "").strip()
            return title or None
        return body
    
    async def get_by_url(self, url: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM articles WHERE url = ?", (url,)).fetchone()
            return self._row_to_article(row)
    
    async def update(self, article_id: int, update_data: ArticleUpdate):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # Check if article exists
            existing = conn.execute("SELECT id FROM articles WHERE id = ?", (article_id,)).fetchone()
            if not existing:
                raise NotFoundError(f"Article with id {article_id} not found")
            
            # Build update query dynamically
            update_fields = []
            update_values = []
            
            update_dict = update_data.model_dump(exclude_unset=True)
            for field, value in update_dict.items():
                update_fields.append(f"{field} = ?")
                update_values.append(value)
            
            if update_fields:
                update_fields.append("updated_at = CURRENT_TIMESTAMP")
                query = f"UPDATE articles SET {', '.join(update_fields)} WHERE id = ?"
                update_values.append(article_id)
                conn.execute(query, update_values)
            
            # Return updated article
            row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
            return self._row_to_article(row)
    
    async def delete(self, article_id: int):
        with sqlite3.connect(self.db_path) as conn:
            # Check if article exists
            existing = conn.execute("SELECT id FROM articles WHERE id = ?", (article_id,)).fetchone()
            if not existing:
                raise NotFoundError(f"Article with id {article_id} not found")
            
            # Soft delete by setting is_archived = True
            cursor = conn.execute("UPDATE articles SET is_archived = TRUE WHERE id = ?", (article_id,))
            return cursor.rowcount > 0
    
    async def list_articles(
        self,
        limit=50,
        offset=0,
        source=None,
        categories=None,
        has_image=None,
        cursor=None,
        entity_ids=None,
        query_text=None,
    ):
        """List non-archived articles, optionally filtered by source and/or
        category tags.

        ``query_text`` is a free-text substring match against title OR
        content (case-insensitive). This is what the News Feed's search box
        actually filters on -- previously the route accepted a query param
        named ``author`` here but never passed it through to this method at
        all, so typing in the search box silently did nothing. Results are
        ranked so title matches sort ahead of content-only matches (a
        passing mention buried in the body no longer ranks the same as an
        article that's actually about the query term), and each
        content-only match gets a ``matched_snippet`` excerpt on the
        returned ``Article`` so the caller can show why it matched.

        ``categories`` is an iterable of category names to match against the
        article's stored ``categories`` JSON-array column. Matching is OR-ed
        across the supplied values (an article needs to have ANY of the
        listed categories to match) and is implemented with a JSON LIKE
        pattern that anchors on the quoted token so substring collisions
        (e.g. "AI" matching "AI/ML") don't false-positive.

        ``has_image`` when True restricts to articles with a non-empty
        ``image_url`` (used by the News Feed infinite-scroll, which only
        ever renders cards that have art).

        ``entity_ids`` restricts to articles that have at least one row in
        ``entity_mentions`` for any of the given knowledge-graph entity ids
        (OR-ed, same convention as ``categories``). This is the real,
        DB-backed version of "show me articles about Company X" -- unlike
        the old client-side title/summary substring match, it reflects
        whatever the entity-extraction pass actually found, including
        mentions buried in the article body. If the ``entity_mentions``
        table doesn't exist yet (extraction has never run), the filter is
        silently skipped rather than erroring.

        ``cursor`` enables keyset pagination for infinite scroll: pass the
        opaque string from a previous call's ``next_cursor`` to fetch the
        next batch after it, ordered by (created_at, id) DESC so ties on an
        identical ``created_at`` (common for articles ingested in the same
        batch) still page deterministically instead of skipping/repeating
        rows the way OFFSET would as new rows are inserted between requests.
        When ``cursor`` is given, ``offset`` is ignored and the total count
        query is skipped (unnecessary work for a scroll feed that never
        needs "page N of M").
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            # Detect which schema is in play so the filter clauses don't
            # blow up on a column-doesn't-exist error.
            cols = {r[1] for r in conn.execute("PRAGMA table_info(articles)").fetchall()}
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }

            # Build query with optional source + category filters
            base_query = "FROM articles WHERE is_archived = 0"
            params: list = []

            if source and "source" in cols:
                base_query += " AND source = ?"
                params.append(source)

            # Categories are stored as a JSON array string (e.g.
            # '["AI/ML"]'). We match on the exact quoted token so "AI"
            # doesn't accidentally match "AI/ML" via substring.
            cat_list = [c for c in (categories or []) if c]
            if cat_list and "categories" in cols:
                clauses = []
                for c in cat_list:
                    clauses.append("categories LIKE ?")
                    params.append(f'%"{c}"%')
                base_query += " AND (" + " OR ".join(clauses) + ")"

            eid_list = [e for e in (entity_ids or []) if e is not None]
            if eid_list and "entity_mentions" in tables:
                placeholders = ",".join("?" * len(eid_list))
                base_query += (
                    " AND id IN (SELECT article_id FROM entity_mentions "
                    f"WHERE entity_id IN ({placeholders}))"
                )
                params.extend(eid_list)

            q = (query_text or "").strip()
            needle = None
            if q and "content" in cols:
                # Escape existing LIKE wildcards so a search for e.g. "50%"
                # matches literally instead of acting as a wildcard.
                escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                base_query += (
                    " AND (title LIKE ? ESCAPE '\\' OR content LIKE ? ESCAPE '\\')"
                )
                needle = f"%{escaped}%"
                params.extend([needle, needle])

            if has_image and "image_url" in cols:
                base_query += " AND image_url IS NOT NULL AND image_url != ''"

            # When searching, rank title matches ahead of content-only
            # matches so a passing body mention doesn't rank identically to
            # an article that's actually about the query term. Falls back
            # to the normal recency order otherwise (and as the tiebreaker
            # within each rank tier).
            order_clause = "created_at DESC, id DESC"
            order_params: list = []
            if needle is not None:
                order_clause = (
                    "CASE WHEN title LIKE ? ESCAPE '\\' THEN 0 ELSE 1 END, "
                    + order_clause
                )
                order_params = [needle]

            if needle is not None:
                # The keyset cursor below only orders on (created_at, id),
                # but a search query's real ORDER BY prepends a title/content
                # rank tier -- keyset paging against the wrong ordering
                # silently drops rows (any content-only match newer than the
                # last title match shown on a page never gets returned on
                # any page, no error, nothing to notice). So when a search
                # is active, page by a plain offset instead -- offset +
                # ranking was verified correct, unlike keyset + ranking.
                # The offset rides in the same opaque `cursor` string
                # (prefixed so it's never confused with a real keyset
                # cursor) so this stays a drop-in replacement for the
                # frontend's existing infinite-scroll contract.
                search_offset = 0
                if cursor and cursor.startswith("search-offset::"):
                    try:
                        search_offset = max(0, int(cursor.split("::", 1)[1]))
                    except (ValueError, IndexError):
                        search_offset = 0

                # Unlike the plain keyset-cursor path (which skips the count
                # query since a scroll feed never needs "page N of M"), a
                # search's first page is also how the News Feed's result
                # count badge gets its number -- keep computing it here so
                # switching search to offset-mode paging doesn't also break
                # that badge.
                count_query = f"SELECT COUNT(*) as count {base_query}"
                total_count = conn.execute(count_query, params).fetchone()["count"]

                query = f"SELECT * {base_query} ORDER BY {order_clause} LIMIT ? OFFSET ?"
                rows = conn.execute(
                    query, [*params, *order_params, limit, search_offset]
                ).fetchall()
                articles = [self._row_to_article(row) for row in rows]
                self._attach_match_snippets(articles, rows, q)
                next_cursor = (
                    f"search-offset::{search_offset + limit}"
                    if len(rows) == limit
                    else None
                )
                return articles, total_count, next_cursor

            cursor_created_at = None
            cursor_id = None
            if cursor:
                try:
                    cursor_created_at, cursor_id_str = cursor.split("::", 1)
                    cursor_id = int(cursor_id_str)
                except (ValueError, AttributeError):
                    cursor_created_at = None
                    cursor_id = None

            if cursor_created_at is not None and cursor_id is not None:
                # Keyset predicate: strictly "older" than the cursor row
                # under the same (created_at DESC, id DESC) ordering used
                # below, so no row is skipped or repeated across pages.
                base_query += (
                    " AND (created_at < ? OR (created_at = ? AND id < ?))"
                )
                params.extend([cursor_created_at, cursor_created_at, cursor_id])

                query = f"SELECT * {base_query} ORDER BY {order_clause} LIMIT ?"
                rows = conn.execute(query, [*params, *order_params, limit]).fetchall()
                articles = [self._row_to_article(row) for row in rows]
                self._attach_match_snippets(articles, rows, q)
                next_cursor = self._next_cursor(rows, limit)
                return articles, None, next_cursor

            # Get total count
            count_query = f"SELECT COUNT(*) as count {base_query}"
            total_count = conn.execute(count_query, params).fetchone()["count"]

            # Get articles with pagination
            query = f"SELECT * {base_query} ORDER BY {order_clause} LIMIT ? OFFSET ?"
            rows = conn.execute(query, [*params, *order_params, limit, offset]).fetchall()
            articles = [self._row_to_article(row) for row in rows]
            self._attach_match_snippets(articles, rows, q)
            next_cursor = self._next_cursor(rows, limit)

            return articles, total_count, next_cursor

    @staticmethod
    def _attach_match_snippets(articles, rows, query_text):
        """Populate ``matched_snippet`` on each article for a content-only
        search match (title didn't match the query, but content did).

        No-op when ``query_text`` is empty. Title matches are left with
        ``matched_snippet=None`` since the title itself already shows why
        the article matched.
        """
        if not query_text:
            return
        q_lower = query_text.lower()
        for article, row in zip(articles, rows):
            title = (article.title or "")
            if q_lower in title.lower():
                continue
            content = row["content"] or ""
            idx = content.lower().find(q_lower)
            if idx == -1:
                continue
            start = max(0, idx - 60)
            end = min(len(content), idx + len(query_text) + 60)
            snippet = content[start:end].strip()
            prefix = "…" if start > 0 else ""
            suffix = "…" if end < len(content) else ""
            article.matched_snippet = f"{prefix}{snippet}{suffix}"

    @staticmethod
    def _next_cursor(rows, limit):
        """Build the opaque keyset cursor for the row after ``rows``.

        Returns None once a page comes back short (fewer rows than asked
        for), which means the query has run out of matching articles.
        """
        if len(rows) < limit or not rows:
            return None
        last = rows[-1]
        return f"{last['created_at']}::{last['id']}"
    
    async def search_articles(self, query, limit=50, offset=0):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            search_query = "SELECT * FROM articles WHERE title LIKE ? OR content LIKE ? ORDER BY created_at DESC LIMIT ? OFFSET ?"
            search_term = f"%{query}%"
            rows = conn.execute(search_query, (search_term, search_term, limit, offset)).fetchall()
            return [self._row_to_article(row) for row in rows]
    
    async def get_articles_without_embeddings(self, limit=100):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM articles WHERE embedding_generated = FALSE ORDER BY created_at ASC LIMIT ?", (limit,)).fetchall()
            return [self._row_to_article(row) for row in rows]

    async def mark_embedding_generated(self, article_id):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("UPDATE articles SET embedding_generated = TRUE WHERE id = ?", (article_id,))
            return cursor.rowcount > 0

    async def get_articles_without_summary(self, limit: int = 100):
        """
        Return articles still needing an AI summary (excludes archived).

        We trust `summary_generated` as the source of truth: articles whose
        content was too short to summarize are still marked TRUE so we don't
        re-process them on every run.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM articles "
                "WHERE is_archived = FALSE "
                "  AND summary_generated = FALSE "
                "ORDER BY created_at ASC LIMIT ?",
                (limit,),
            ).fetchall()
            return [self._row_to_article(row) for row in rows]

    async def mark_summary_generated(self, article_id, summary=None):
        """Flip summary_generated to TRUE; optionally write the summary text."""
        with sqlite3.connect(self.db_path) as conn:
            if summary is not None:
                cursor = conn.execute(
                    "UPDATE articles SET summary = ?, summary_generated = TRUE, "
                    "    updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (summary, article_id),
                )
            else:
                cursor = conn.execute(
                    "UPDATE articles SET summary_generated = TRUE, "
                    "    updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (article_id,),
                )
            return cursor.rowcount > 0

    async def get_stats(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            total = conn.execute("SELECT COUNT(*) as count FROM articles").fetchone()["count"]
            # Count from the article_embeddings side-table (populated by
            # `scripts/backfill_embeddings.py`). The legacy `articles
            # .embedding_generated` flag is also accepted as a fallback for
            # rows that were embedded before the backfill script started
            # writing to the side-table. Either source counting non-zero
            # is enough to flip the "embeddings available" indicator on.
            try:
                with_embeddings_table = conn.execute(
                    "SELECT COUNT(*) as count FROM article_embeddings"
                ).fetchone()["count"]
            except sqlite3.OperationalError:
                # article_embeddings table doesn't exist yet — fall back
                # to the column flag.
                with_embeddings_table = 0
            with_embeddings_flag = conn.execute(
                "SELECT COUNT(*) as count FROM articles WHERE embedding_generated = TRUE"
            ).fetchone()["count"]
            with_embeddings = max(with_embeddings_table, with_embeddings_flag)
            with_summaries = conn.execute("SELECT COUNT(*) as count FROM articles WHERE summary IS NOT NULL AND TRIM(summary) != ''").fetchone()["count"]

            top_sources_rows = conn.execute("SELECT source, COUNT(*) as count FROM articles GROUP BY source ORDER BY count DESC LIMIT 5").fetchall()
            top_sources = {row["source"]: row["count"] for row in top_sources_rows}

            return {
                "total_articles": total,
                "articles_with_embeddings": with_embeddings,
                "articles_without_embeddings": total - with_embeddings,
                "articles_with_summaries": with_summaries,
                "articles_without_summaries": total - with_summaries,
                "top_sources": top_sources,
            }

    async def health_check(self):
        """Lightweight DB connectivity probe used by /health/detailed.

        Returns a dict shaped to match what the health route expects
        (`status`, `database_accessible`). Any sqlite-level failure is
        caught and surfaced as `status: "unhealthy"` with the exception
        message — the health endpoint then renders that as a degraded
        component without taking the app offline.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute("SELECT COUNT(*) FROM articles").fetchone()
                total = int(row[0]) if row else 0
            return {
                "status": "healthy",
                "database_accessible": True,
                "total_articles": total,
                "db_path": self.db_path,
            }
        except Exception as exc:  # pragma: no cover — defensive
            return {
                "status": "unhealthy",
                "database_accessible": False,
                "error": f"{type(exc).__name__}: {exc}",
                "db_path": self.db_path,
            }
