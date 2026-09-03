"""
News Routes
==========

API routes for news article operations including ingestion,
retrieval, filtering, and statistics.
"""

import json
import sqlite3
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Dict, Any, List, Optional

from ...services import NewsService
from ...repositories import ArticleRepository
from ...models.article import (
    Article, 
    ArticleSearchRequest,
    ArticleStats,
    IngestRequest,
    IngestResponse
)
from ...models.api import BaseResponse, PaginatedResponse, PaginationInfo
from ...core.exceptions import NewsIngestionError

router = APIRouter(prefix="/news", tags=["News"])

# Dependency injection
def get_news_service() -> NewsService:
    """Get news service instance."""
    return NewsService()

def get_article_repository() -> ArticleRepository:
    """Get article repository instance."""
    from ...core.config import get_settings
    settings = get_settings()
    return ArticleRepository(settings.get_database_file_path())


@router.get("/", response_model=PaginatedResponse[Article])
async def get_articles(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    source: Optional[str] = Query(default=None, description="Filter by news source"),
    category: Optional[List[str]] = Query(default=None, description="Filter by category tag (repeatable; OR-ed)"),
    author: Optional[str] = Query(default=None, description="Filter by author"),
    has_summary: Optional[bool] = Query(default=None, description="Filter by summary presence"),
    sort_by: Optional[str] = Query(default="created_at", description="Sort field"),
    sort_desc: bool = Query(default=True, description="Sort in descending order"),
    repo: ArticleRepository = Depends(get_article_repository)
) -> PaginatedResponse[Article]:
    """
    Get paginated list of news articles with optional filtering.

    Args:
        page: Page number (starting from 1)
        page_size: Number of articles per page (1-100)
        source: Optional source filter
        category: Optional category filter — matches articles whose
            ``categories`` JSON-array contains any of the supplied values.
            Repeatable, OR-ed across values (?category=AI/ML&category=Cloud).
        author: Optional author filter
        has_summary: Filter by presence of summary
        sort_by: Field to sort by (created_at, published_date, title, views)
        sort_desc: Sort in descending order

    Returns:
        Paginated response with articles and pagination info
    """
    try:
        # Create filter object
        ArticleSearchRequest(
            source=source,
            author=author,
            has_summary=has_summary,
            sort_by=sort_by,
            sort_desc=sort_desc
        )

        # Calculate offset
        offset = (page - 1) * page_size

        # Normalize category filter: drop empties so an explicit ?category=
        # (no value) doesn't accidentally filter every article out.
        categories_filter = [c for c in (category or []) if c and c.strip()] or None

        # Get articles and total count
        articles, total_count = await repo.list_articles(
            limit=page_size,
            offset=offset,
            source=source,
            categories=categories_filter,
        )
        
        # Calculate pagination info
        total_pages = (total_count + page_size - 1) // page_size
        pagination = PaginationInfo(
            page=page,
            page_size=page_size,
            total_items=total_count,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1
        )
        
        return PaginatedResponse(
            data=articles,
            pagination=pagination
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve articles: {str(e)}"
        )


@router.post("/ingest", response_model=BaseResponse[IngestResponse])
async def ingest_news(
    request: IngestRequest,
    service: NewsService = Depends(get_news_service),
    repo: ArticleRepository = Depends(get_article_repository)
) -> BaseResponse[IngestResponse]:
    """
    Trigger RSS feed ingestion to fetch new articles.
    
    Args:
        request: Ingest request containing feed URLs
        
    Returns:
        Ingestion results and statistics
    """
    try:
        # Fetch articles from RSS feeds
        new_articles = await service.fetch_rss_feeds(request.feed_urls)
        
        # Store articles in database
        stored_count = 0
        skipped_count = 0
        errors = []
        
        for article_data in new_articles:
            try:
                # Check if article already exists
                existing = await repo.get_by_url(article_data.url)
                if existing:
                    skipped_count += 1
                    continue
                
                # Create new article
                await repo.create(article_data)
                stored_count += 1
                
            except Exception as e:
                errors.append(f"Failed to store article {article_data.url}: {str(e)}")
                continue
        
        response_data = IngestResponse(
            processed=len(new_articles),
            new_articles=stored_count,
            duplicates=skipped_count,
            errors=errors[:10]  # Limit error list
        )
        
        return BaseResponse(
            success=True,
            message=f"Ingestion completed. Stored: {stored_count}, Skipped: {skipped_count}",
            data=response_data
        )
        
    except NewsIngestionError as e:
        raise HTTPException(status_code=500, detail=f"News ingestion failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.get("/sources", response_model=BaseResponse[Dict[str, Any]])
async def get_news_sources(
    repo: ArticleRepository = Depends(get_article_repository)
) -> BaseResponse[Dict[str, Any]]:
    """
    Get information about configured news sources and their statistics.
    
    Returns:
        News source information and statistics
    """
    try:
        stats = await repo.get_stats()
        
        return BaseResponse(
            success=True,
            message="News sources retrieved successfully",
            data={
                "configured_sources": len(stats.get("top_sources", [])),
                "source_statistics": stats.get("top_sources", []),
                "total_articles": stats.get("total_articles", 0)
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get news sources: {str(e)}"
        )


@router.get("/categories", response_model=BaseResponse[Dict[str, Any]])
async def get_news_categories() -> BaseResponse[Dict[str, Any]]:
    """
    Return the distinct categories actually present in the article DB.

    This powers the frontend Topic Filter chips so it only ever shows
    categories that have live articles backing them - no more orphaned
    "Robotics" / "Biotech" chips that filter to zero results because no
    feed maps to them. As ingestion adds new categories the chip list
    grows automatically.
    """
    try:
        from ...core.config import get_settings
        settings = get_settings()
        db_path = settings.get_database_file_path()

        seen: set[str] = set()
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT DISTINCT categories FROM articles "
                "WHERE is_archived = 0 AND categories IS NOT NULL"
            ).fetchall()

        for row in rows:
            raw = row["categories"]
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(parsed, list):
                for c in parsed:
                    if c:
                        seen.add(str(c))

        # Sorted for stable UI rendering.
        categories = sorted(seen)

        return BaseResponse(
            success=True,
            message=f"Retrieved {len(categories)} categor{'y' if len(categories) == 1 else 'ies'}",
            data={"categories": categories},
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get categories: {str(e)}",
        )


@router.get("/stats", response_model=BaseResponse[ArticleStats])
async def get_news_stats(
    repo: ArticleRepository = Depends(get_article_repository)
) -> BaseResponse[ArticleStats]:
    """
    Get comprehensive statistics about news articles.
    
    Returns:
        Detailed article statistics
    """
    try:
        stats_data = await repo.get_stats()
        
        stats = ArticleStats(
            total_articles=stats_data.get("total_articles", 0),
            articles_today=0,  # Would need date-based query
            articles_this_week=stats_data.get("recent_articles_7d", 0),
            unique_sources=len(stats_data.get("top_sources", [])),
            articles_with_summaries=stats_data.get("articles_with_summaries", 0),
            articles_with_embeddings=stats_data.get("articles_with_embeddings", 0)
        )
        
        return BaseResponse(
            success=True,
            message="Statistics retrieved successfully",
            data=stats
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get statistics: {str(e)}"
        )


@router.get("/search", response_model=BaseResponse[List[Article]])
async def search_articles(
    q: str = Query(..., min_length=1, max_length=200, description="Search query"),
    limit: int = Query(default=20, ge=1, le=50, description="Maximum results"),
    repo: ArticleRepository = Depends(get_article_repository)
) -> BaseResponse[List[Article]]:
    """
    Search articles by text content.
    
    Args:
        q: Search query string
        limit: Maximum number of results to return
        
    Returns:
        List of matching articles
    """
    try:
        articles = await repo.search_articles(q, limit)
        
        return BaseResponse(
            success=True,
            message=f"Found {len(articles)} articles matching '{q}'",
            data=articles
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}"
        )


@router.get("/front-page", response_model=Dict[str, Any])
async def get_front_page(
    date: Optional[str] = Query(default=None, description="YYYY-MM-DD; defaults to latest snapshot"),
    recompute: bool = Query(default=False, description="Force fresh computation"),
) -> Dict[str, Any]:
    """
    Return the precomputed News Feed front-page composition.

    The daily ingestion orchestrator bakes a snapshot into the
    ``front_page_snapshots`` table at the end of each run (5th phase).
    This endpoint serves that snapshot in a single query. With
    ``recompute=true`` callers can force a fresh compute (admin
    debugging / smoke tests). If no snapshot exists yet on a fresh DB
    we fall back to live-compute so the UI is never blank.
    """
    from ...core.config import get_settings
    from ...services.front_page_precompute import (
        compute_front_page,
        load_latest_snapshot,
    )

    settings = get_settings()
    db_path = settings.get_database_file_path()

    try:
        if recompute:
            snap = await compute_front_page(db_path)
        else:
            snap = load_latest_snapshot(db_path, date)
            if snap is None:
                # No snapshot yet (fresh DB or first deploy). Live-
                # compute on the fly so the response is always usable.
                snap = await compute_front_page(db_path)
        return snap.to_dict()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load front page: {str(e)}",
        )


@router.get("/{article_id}", response_model=BaseResponse[Article])
async def get_article(
    article_id: int,
    repo: ArticleRepository = Depends(get_article_repository)
) -> BaseResponse[Article]:
    """
    Get a specific article by ID.
    
    Args:
        article_id: The article ID
        
    Returns:
        Article details
    """
    try:
        article = await repo.get_by_id(article_id)
        return BaseResponse(
            success=True,
            message="Article retrieved successfully",
            data=article
        )
        
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=f"Article not found: {article_id}")
        raise HTTPException(status_code=500, detail=f"Failed to get article: {str(e)}")
