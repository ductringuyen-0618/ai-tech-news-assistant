"""
Learning Routes
===============

API routes for the Learning feed (proposal 003): trending AI agent
skills/techniques/setups, tagged during ingestion with the reserved
``Agent Skills`` category (see ``src/services/learning_ingestion.py``)
and served here the same way ``/api/news/`` serves the main feed.
"""

from fastapi import APIRouter, HTTPException, Query, Depends

from ...repositories import ArticleRepository
from ...models.article import Article
from ...models.api import PaginatedResponse, PaginationInfo
from ...services.learning_ingestion import LEARNING_CATEGORY

router = APIRouter(prefix="/learning", tags=["Learning"])


def get_article_repository() -> ArticleRepository:
    """Get article repository instance."""
    from ...core.config import get_settings
    settings = get_settings()
    return ArticleRepository(settings.get_database_file_path())


@router.get("/", response_model=PaginatedResponse[Article])
async def get_learning_items(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    repo: ArticleRepository = Depends(get_article_repository),
) -> PaginatedResponse[Article]:
    """Get paginated Learning-feed items (articles tagged ``Agent Skills``).

    Same offset-pagination shape as ``GET /api/news/`` -- reuses
    ``ArticleRepository.list_articles``'s existing ``categories`` filter
    rather than a bespoke query, so this endpoint stays consistent with
    the main feed's pagination semantics and total-count behavior.
    """
    try:
        offset = (page - 1) * page_size

        articles, total_count, _next_cursor = await repo.list_articles(
            limit=page_size,
            offset=offset,
            categories=[LEARNING_CATEGORY],
        )

        total_count = total_count or 0
        total_pages = (total_count + page_size - 1) // page_size if total_count else 0
        pagination = PaginationInfo(
            page=page,
            page_size=page_size,
            total_items=total_count,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
            next_cursor=None,
        )

        return PaginatedResponse(data=articles, pagination=pagination)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve learning items: {str(e)}",
        )
