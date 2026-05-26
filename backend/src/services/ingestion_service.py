"""
Ingestion Service
================

Orchestrates the complete news ingestion pipeline:
1. Fetch RSS feeds from multiple sources
2. Parse and extract article content
3. Store in database with metadata
4. Handle duplicates and errors gracefully

Features:
- Batch processing
- Error recovery and retry logic
- Duplicate detection
- Content quality validation
- Progress tracking and status reporting
"""

import html
import json
import re
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum

import feedparser
import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.database.models import Article, Source, Category
import logging

logger = logging.getLogger(__name__)


class IngestionStatus(str, Enum):
    """Ingestion status values."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class IngestionResult:
    """Result of an ingestion operation."""
    
    def __init__(self):
        self.status = IngestionStatus.PENDING
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.total_feeds = 0
        self.total_articles_found = 0
        self.total_articles_saved = 0
        self.duplicates_skipped = 0
        self.errors_encountered = 0
        self.error_details: List[Dict[str, Any]] = []
        self.sources_processed: Dict[str, int] = {}
    
    @property
    def duration_seconds(self) -> float:
        """Get duration in seconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0
    
    @property
    def success_rate(self) -> float:
        """Get success rate as percentage."""
        if self.total_articles_found == 0:
            return 0.0
        return (self.total_articles_saved / self.total_articles_found) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "status": self.status.value,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": self.duration_seconds,
            "total_feeds": self.total_feeds,
            "total_articles_found": self.total_articles_found,
            "total_articles_saved": self.total_articles_saved,
            "duplicates_skipped": self.duplicates_skipped,
            "errors_encountered": self.errors_encountered,
            "success_rate": f"{self.success_rate:.1f}%",
            "sources_processed": self.sources_processed,
            "error_details": self.error_details[:10]  # Limit to 10 errors
        }


class IngestionService:
    """
    Service for ingesting news articles from RSS feeds and other sources.
    
    Handles:
    - RSS feed fetching and parsing
    - Content extraction and cleaning
    - Database storage
    - Duplicate detection
    - Error handling and recovery
    """
    
    # Default RSS feeds to scrape.
    #
    # Each ``category`` value MUST match one of the chip labels rendered by
    # the frontend Topic Filter (see ``frontend/src/App.tsx``):
    #   "AI/ML", "AI Agents", "Robotics", "Biotech", "Military Tech",
    #   "Hardware", "Cloud", "Security", "Quantum Computing", "Healthcare"
    # If they don't match, ``categories`` JSON written to the row will never
    # intersect with the user's selected chips and the filter will return
    # zero articles. Honesty over precision: each feed gets a single best-
    # fit chip; downstream NLP can refine per-article tagging later.
    DEFAULT_FEEDS = [
        {
            # Hacker News' real front-page feed (the old feedburner URL is dead).
            "name": "Hacker News",
            "url": "https://hnrss.org/frontpage",
            "category": "AI/ML",
        },
        {
            "name": "TechCrunch",
            "url": "https://techcrunch.com/feed/",
            "category": "Cloud",
        },
        {
            "name": "Ars Technica",
            "url": "https://feeds.arstechnica.com/arstechnica/index",
            "category": "Hardware",
        },
        {
            "name": "The Verge",
            "url": "https://www.theverge.com/rss/index.xml",
            "category": "AI/ML",
        },
        {
            "name": "MIT Technology Review",
            "url": "https://www.technologyreview.com/feed/",
            "category": "AI/ML",
        },
    ]
    
    def __init__(self, db: Session, batch_size: int = 5, timeout: int = 30):
        """
        Initialize ingestion service.
        
        Args:
            db: SQLAlchemy Session for database operations
            batch_size: Number of feeds to process concurrently
            timeout: HTTP timeout in seconds
        """
        self.db = db
        self.batch_size = batch_size
        self.timeout = timeout
        self.http_client = httpx.Client(
            timeout=timeout,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; TechNewsBot/1.0)"
            }
        )
        self.result = IngestionResult()
    
    def ingest_all(self, sources: Optional[List[Dict[str, str]]] = None) -> IngestionResult:
        """
        Run complete ingestion pipeline from all sources.
        
        Args:
            sources: Custom sources to ingest (uses defaults if None)
            
        Returns:
            IngestionResult with detailed statistics
        """
        self.result = IngestionResult()
        self.result.status = IngestionStatus.RUNNING
        self.result.start_time = datetime.utcnow()
        
        try:
            feeds = sources or self.DEFAULT_FEEDS
            self.result.total_feeds = len(feeds)
            
            logger.info(f"Starting ingestion of {len(feeds)} feeds")
            
            # Process feeds sequentially
            for feed in feeds:
                try:
                    self._ingest_feed(feed)
                except Exception as e:
                    logger.error(f"Error processing feed {feed.get('name')}: {e}")
                    self.result.errors_encountered += 1
            
            # Commit all changes
            self.db.commit()
            
            self.result.end_time = datetime.utcnow()
            self.result.status = IngestionStatus.COMPLETED if self.result.errors_encountered == 0 else IngestionStatus.PARTIAL
            
            logger.info(f"Ingestion completed: {self.result.total_articles_saved} articles saved, "
                       f"{self.result.duplicates_skipped} duplicates skipped, "
                       f"{self.result.errors_encountered} errors")
            
            return self.result
            
        except Exception as e:
            self.db.rollback()
            self.result.end_time = datetime.utcnow()
            self.result.status = IngestionStatus.FAILED
            self.result.errors_encountered += 1
            self.result.error_details.append({
                "source": "ingestion_pipeline",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            })
            logger.error(f"Ingestion pipeline failed: {e}", exc_info=True)
            return self.result
    
    def _ingest_feed(self, feed_config: Dict[str, str]) -> None:
        """
        Ingest a single RSS feed.
        
        Args:
            feed_config: Feed configuration with name, url, category
        """
        source_name = feed_config.get("name", "Unknown")
        feed_url = feed_config.get("url", "")
        category_name = feed_config.get("category", "technology")
        
        try:
            logger.info(f"Ingesting feed: {source_name}")
            
            # Fetch RSS feed
            response = self.http_client.get(feed_url)
            response.raise_for_status()
            
            # Parse feed
            feed = feedparser.parse(response.content)
            
            if not feed.entries:
                logger.warning(f"No entries found in feed: {source_name}")
                return
            
            logger.info(f"Found {len(feed.entries)} entries in {source_name}")
            self.result.sources_processed[source_name] = len(feed.entries)
            self.result.total_articles_found += len(feed.entries)
            
            # Get or create category
            category = self._get_or_create_category(category_name)
            
            # Process each entry
            for entry in feed.entries:
                try:
                    self._process_entry(entry, source_name, category)
                except Exception as e:
                    logger.warning(f"Error processing entry from {source_name}: {e}")
                    self.result.errors_encountered += 1
                    self.result.error_details.append({
                        "source": source_name,
                        "error": str(e),
                        "entry_title": entry.get("title", "Unknown"),
                        "timestamp": datetime.utcnow().isoformat()
                    })
            
            # Update source last_scraped timestamp
            self._update_source_timestamp(source_name)
            
        except Exception as e:
            logger.error(f"Failed to ingest feed {source_name}: {e}", exc_info=True)
            self.result.errors_encountered += 1
            self.result.error_details.append({
                "source": source_name,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            })
    
    @staticmethod
    def _clean_text(value: Optional[str]) -> str:
        """
        Decode HTML entities and strip HTML tags from a feed text field.

        RSS feeds routinely embed entities like ``&#8217;`` (right single
        quote), ``&#8230;`` (ellipsis), and ``&#160;`` (nbsp), plus inline
        ``<p>`` / ``<a>`` markup in summary blocks. Storing those raw caused
        the frontend cards to literally render ``It&#8217;s`` instead of
        ``It's``. We unescape entities first, then strip remaining tags, then
        collapse whitespace.
        """
        if not value:
            return ""
        # Decode HTML entities (&#8217; -> right single quote, &amp; -> &, ...)
        decoded = html.unescape(value)
        # Strip HTML tags that survived feed parsing.
        decoded = re.sub(r"<[^>]+>", "", decoded)
        # Collapse runs of whitespace (incl. newlines) into single spaces.
        return re.sub(r"\s+", " ", decoded).strip()

    @staticmethod
    def _extract_image_url(entry: Any, description: Optional[str]) -> Optional[str]:
        """
        Find the best representative image URL for an RSS entry.

        feedparser exposes images in several places depending on the feed:
        ``media_thumbnail`` (Media RSS), ``media_content`` (Media RSS), and
        sometimes only as an ``<img src="...">`` inside the summary HTML.
        We try each in turn and return the first hit, or ``None`` if no image
        can be found.
        """
        # 1. Media RSS thumbnail
        thumbs = getattr(entry, "media_thumbnail", None) or entry.get("media_thumbnail") if isinstance(entry, dict) else getattr(entry, "media_thumbnail", None)
        if thumbs:
            try:
                first = thumbs[0]
                url = first.get("url") if isinstance(first, dict) else getattr(first, "url", None)
                if url:
                    return url
            except (IndexError, AttributeError, TypeError):
                pass

        # 2. Media RSS content
        media_content = (
            entry.get("media_content") if isinstance(entry, dict) else getattr(entry, "media_content", None)
        )
        if media_content:
            try:
                for m in media_content:
                    mime = (m.get("type") or "") if isinstance(m, dict) else (getattr(m, "type", "") or "")
                    url = (m.get("url") or "") if isinstance(m, dict) else (getattr(m, "url", "") or "")
                    if mime.startswith("image/") or url.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
                        if url:
                            return url
            except (TypeError, AttributeError):
                pass

        # 3. Enclosures (some feeds put images here)
        enclosures = (
            entry.get("enclosures") if isinstance(entry, dict) else getattr(entry, "enclosures", None)
        )
        if enclosures:
            try:
                for enc in enclosures:
                    mime = (enc.get("type") or "") if isinstance(enc, dict) else (getattr(enc, "type", "") or "")
                    url = (enc.get("href") or enc.get("url") or "") if isinstance(enc, dict) else (getattr(enc, "href", "") or getattr(enc, "url", "") or "")
                    if mime.startswith("image/") or url.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
                        if url:
                            return url
            except (TypeError, AttributeError):
                pass

        # 4. Atom-style ``content`` block (a list of {value: html, type: ...}).
        #    Many WordPress / Atom feeds (MIT Tech Review, The Verge, ...)
        #    embed the hero image inside the first ``content[0].value`` block
        #    rather than in summary or media tags.
        atom_content = (
            entry.get("content") if isinstance(entry, dict) else getattr(entry, "content", None)
        )
        if atom_content and isinstance(atom_content, list):
            try:
                first = atom_content[0]
                value = first.get("value") if isinstance(first, dict) else getattr(first, "value", "")
                if value:
                    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', value)
                    if m:
                        return m.group(1)
            except (IndexError, AttributeError, TypeError):
                pass

        # 5. First <img> in description HTML (note: must run BEFORE we strip tags)
        if description:
            m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', description)
            if m:
                return m.group(1)

        return None

    def _process_entry(self, entry: Dict[str, Any], source_name: str, category) -> None:
        """
        Process a single RSS entry and save to database.

        Args:
            entry: RSS entry from feedparser
            source_name: Name of the source
            category: Category object
        """
        # Extract article data. Capture the raw description first so we can
        # mine it for an <img src> before tag-stripping clobbers the markup.
        raw_description = (entry.get("summary") or "").strip()
        image_url = self._extract_image_url(entry, raw_description)

        # Decode HTML entities + strip tags up-front so what we store is what
        # the user will see in the UI — no more ``&#8217;`` showing up as
        # literal text in cards/digest.
        title = self._clean_text(entry.get("title") or "")
        url = (entry.get("link") or "").strip()
        description = self._clean_text(raw_description)
        author = (entry.get("author") or "").strip() or None
        
        if not title or not url:
            logger.debug("Skipping entry with missing title or URL")
            return
        
        # Check for duplicates
        existing = self.db.query(Article).filter(Article.url == url).first()
        if existing:
            logger.debug(f"Duplicate article found: {title}")
            self.result.duplicates_skipped += 1
            return
        
        # Parse published date
        published_at = None
        if "published_parsed" in entry and entry.published_parsed:
            try:
                published_at = datetime(*entry.published_parsed[:6])
            except Exception as e:
                logger.debug(f"Failed to parse date: {e}")
        
        # Create article.
        #
        # NOTE: ``Article.source`` is a *relationship* to the ``Source`` ORM
        # model (see ``src/database/models.py``), not a plain string column,
        # so passing ``source=source_name`` (a ``str``) caused SQLAlchemy to
        # raise ``'str' object has no attribute '_sa_instance_state'`` during
        # flush, which is why every entry crashed and zero articles were
        # saved. The proper foreign key is set via ``source_id`` below; the
        # human-readable name is recovered through ``article.source.name``.
        article = Article(
            title=title[:500],  # Truncate to max length
            url=url[:1000],
            content=description,
            summary=description[:500] if description else None,
            author=author[:200] if author else None,
            published_at=published_at,
            source_id=self._get_source_id(source_name),
        )

        # Add category. Must be a ``Category`` ORM instance — never a string —
        # for the same ``_sa_instance_state`` reason as above.
        if category is not None and isinstance(category, Category):
            article.categories.append(category)

        # Add to session (will be committed after all entries)
        self.db.add(article)

        # Also write the JSON-encoded ``categories`` TEXT column on the
        # ``articles`` row. Reason: the live read path used by the frontend
        # is ``ArticleRepository._row_to_article`` (raw sqlite3 in
        # ``src/repositories/article_repository.py``), which ``json.loads``-es
        # the ``categories`` column directly. The M2M ``article_categories``
        # association table is invisible to that path. Without this write,
        # every API response has ``categories=null`` and the frontend's Topic
        # Filter chips never match anything.
        #
        # We can't expose this column via ``Article.categories`` on the ORM
        # because that name is already the M2M relationship; assigning a
        # string list there would silently target the relationship. We
        # therefore flush to obtain ``article.id`` and UPDATE the column with
        # raw SQL through the session's connection.
        category_name = (
            category.name if category is not None and hasattr(category, "name") else None
        )
        try:
            self.db.flush()
            # Always write source + image_url; conditionally write categories.
            # We use a single UPDATE because the ``image_url`` column was added
            # via lightweight migration and isn't on the SQLAlchemy ``Article``
            # model here. Wrapped in try/except so a missing column on a stale
            # DB schema (or any other transient failure) never aborts the
            # ingestion of a whole entry.
            params: Dict[str, Any] = {
                "src": source_name,
                "img": image_url,
                "id": article.id,
            }
            if category_name:
                params["cats"] = json.dumps([category_name])
                self.db.execute(
                    text(
                        "UPDATE articles SET categories = :cats, source = :src, "
                        "image_url = :img WHERE id = :id"
                    ),
                    params,
                )
            else:
                self.db.execute(
                    text(
                        "UPDATE articles SET source = :src, image_url = :img "
                        "WHERE id = :id"
                    ),
                    params,
                )
        except Exception as e:
            # Don't let an UPDATE failure abort the whole entry — the row will
            # just be returned with categories=NULL / image_url=NULL, which is
            # the pre-fix behaviour, not a regression.
            logger.warning(
                f"Failed to update categories/image for article id={article.id}: {e}"
            )

        self.result.total_articles_saved += 1
        logger.debug(f"Saved article: {title[:80]}...")
    
    def _get_or_create_category(self, category_name: str) -> Optional[Category]:
        """Get or create a category."""
        try:
            category = self.db.query(Category).filter(Category.name == category_name).first()
            
            if not category:
                category = Category(
                    name=category_name,
                    slug=category_name.lower().replace(" ", "-"),
                    is_active=True
                )
                self.db.add(category)
                self.db.flush()
            
            return category
        except Exception as e:
            logger.warning(f"Failed to get/create category {category_name}: {e}")
            return None
    
    def _get_source_id(self, source_name: str) -> Optional[int]:
        """Get source ID, creating if necessary."""
        try:
            source = self.db.query(Source).filter(Source.name == source_name).first()
            
            if not source:
                source = Source(
                    name=source_name,
                    url=f"https://{source_name.lower().replace(' ', '-')}.local",
                    is_active=True,
                    scrape_frequency=3600
                )
                self.db.add(source)
                self.db.flush()
            
            return source.id
        except Exception as e:
            logger.warning(f"Failed to get/create source {source_name}: {e}")
            return None
    
    def _update_source_timestamp(self, source_name: str) -> None:
        """Update source last_scraped timestamp."""
        try:
            source = self.db.query(Source).filter(Source.name == source_name).first()
            
            if source:
                source.last_scraped = datetime.utcnow()
                self.db.flush()
        except Exception as e:
            logger.warning(f"Failed to update source timestamp: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics.

        Each counter is queried in its own try/except so that a missing
        SQLAlchemy-managed table (e.g. ``sources``, ``categories``) on
        a Fly volume that was bootstrapped from the raw-sqlite3 schema
        only doesn't zero out the other counters. We log the underlying
        error once and return whatever we could pull.
        """
        stats: Dict[str, Any] = {
            "total_articles": 0,
            "total_sources": 0,
            "total_categories": 0,
            "last_result": self.result.to_dict() if self.result.start_time else None,
        }
        partial_errors = []

        try:
            stats["total_articles"] = self.db.query(Article).count()
        except Exception as e:  # noqa: BLE001
            partial_errors.append(f"articles: {e}")
            logger.warning("Failed to count articles in get_stats: %s", e)
            # SQLAlchemy session may be in a failed transaction state
            # after a missing-table error; roll it back so subsequent
            # queries in this same call can still execute.
            try:
                self.db.rollback()
            except Exception:  # noqa: BLE001
                pass

        try:
            stats["total_sources"] = self.db.query(Source).count()
        except Exception as e:  # noqa: BLE001
            partial_errors.append(f"sources: {e}")
            logger.warning("Failed to count sources in get_stats: %s", e)
            try:
                self.db.rollback()
            except Exception:  # noqa: BLE001
                pass

        try:
            stats["total_categories"] = self.db.query(Category).count()
        except Exception as e:  # noqa: BLE001
            partial_errors.append(f"categories: {e}")
            logger.warning("Failed to count categories in get_stats: %s", e)
            try:
                self.db.rollback()
            except Exception:  # noqa: BLE001
                pass

        if partial_errors:
            stats["partial_errors"] = partial_errors
        return stats
    
    def close(self) -> None:
        """Close HTTP client."""
        self.http_client.close()
