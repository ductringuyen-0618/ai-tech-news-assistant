"""
Search Routes
===========

API routes for semantic search functionality combining text search and embeddings.
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Dict, Any, List, Optional
from enum import Enum

from ...services import EmbeddingService
from ...services.embedding_service import get_shared_embedding_service
from ...repositories import ArticleRepository, EmbeddingRepository
from ...models.article import Article
from ...models.embedding import SimilarityResult
from ...models.api import BaseResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/search", tags=["Search"])


class SearchMode(str, Enum):
    """Search modes for different types of search."""
    TEXT = "text"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


class SemanticSearchRequest(BaseModel):
    """Model for semantic search requests."""
    query: str = Field(..., min_length=1, max_length=1000, description="Search query")
    limit: int = Field(20, ge=1, le=50, description="Maximum results")
    threshold: float = Field(0.7, ge=0.0, le=1.0, description="Similarity threshold")
    content_type: str = Field("article", description="Type of content to search")


class HybridSearchRequest(BaseModel):
    """Model for hybrid search requests."""
    query: str = Field(..., min_length=1, max_length=1000, description="Search query")
    limit: int = Field(20, ge=1, le=50, description="Maximum results")
    text_weight: float = Field(0.5, ge=0.0, le=1.0, description="Weight for text search")
    semantic_weight: float = Field(0.5, ge=0.0, le=1.0, description="Weight for semantic search")
    similarity_threshold: float = Field(0.7, ge=0.0, le=1.0, description="Similarity threshold")


# Dependency injection
def get_embedding_service() -> EmbeddingService:
    """Get the shared embedding service singleton (model loads once, not per-request)."""
    return get_shared_embedding_service()

def get_embedding_repository() -> EmbeddingRepository:
    """Get embedding repository instance."""
    return EmbeddingRepository()

def get_article_repository() -> ArticleRepository:
    """Get article repository instance."""
    from ...core.config import get_settings
    settings = get_settings()
    return ArticleRepository(settings.get_database_file_path())


@router.get("/", response_model=BaseResponse[Dict[str, Any]])
async def search(
    q: str = Query(..., min_length=1, max_length=200, description="Search query"),
    mode: SearchMode = Query(default=SearchMode.HYBRID, description="Search mode"),
    limit: int = Query(default=20, ge=1, le=50, description="Maximum results"),
    similarity_threshold: float = Query(default=0.7, ge=0.0, le=1.0, description="Similarity threshold for semantic search"),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    embedding_repo: EmbeddingRepository = Depends(get_embedding_repository),
    article_repo: ArticleRepository = Depends(get_article_repository)
) -> BaseResponse[Dict[str, Any]]:
    """
    Perform search across articles using different search modes.
    
    Args:
        q: Search query string
        mode: Search mode (text, semantic, or hybrid)
        limit: Maximum number of results
        similarity_threshold: Minimum similarity score for semantic search
        
    Returns:
        Search results with articles and similarity information
    """
    try:
        results = {
            "query": q,
            "mode": mode,
            "articles": [],
            "semantic_results": [],
            "total_results": 0
        }
        
        if mode in [SearchMode.TEXT, SearchMode.HYBRID]:
            # Perform text-based search
            text_articles = await article_repo.search_articles(q, limit)
            results["articles"] = text_articles
        
        if mode in [SearchMode.SEMANTIC, SearchMode.HYBRID]:
            # Perform semantic search using embeddings
            try:
                # Generate embedding for query
                from ...models.embedding import EmbeddingRequest
                embedding_request = EmbeddingRequest(texts=[q], batch_size=1)
                embedding_response = await embedding_service.generate_embeddings(embedding_request)
                query_embedding = embedding_response.embeddings[0]
                
                # Search for similar embeddings
                semantic_results = await embedding_repo.similarity_search(
                    query_embedding=query_embedding,
                    model_name=embedding_response.model_name,
                    top_k=limit,
                    similarity_threshold=similarity_threshold,
                    content_type="article"
                )
                
                results["semantic_results"] = semantic_results
                
                # If hybrid mode, combine results
                if mode == SearchMode.HYBRID:
                    results = await _combine_search_results(
                        text_articles=results["articles"],
                        semantic_results=semantic_results,
                        article_repo=article_repo,
                        limit=limit
                    )
                    
            except Exception as e:
                # Fall back to text search if semantic search fails
                if mode == SearchMode.SEMANTIC:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Semantic search failed: {str(e)}"
                    )
                # For hybrid mode, continue with text results only
                pass
        
        results["total_results"] = len(results["articles"])
        
        return BaseResponse(
            success=True,
            message=f"Search completed. Found {results['total_results']} results.",
            data=results
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}"
        )


async def _combine_search_results(
    text_articles: List[Article],
    semantic_results: List[SimilarityResult],
    article_repo: ArticleRepository,
    limit: int
) -> Dict[str, Any]:
    """
    Combine text and semantic search results with scoring.
    
    Args:
        text_articles: Results from text search
        semantic_results: Results from semantic search
        article_repo: Article repository for fetching full articles
        limit: Maximum number of results
        
    Returns:
        Combined and ranked results
    """
    # Create a scoring system that combines text relevance and semantic similarity
    combined_scores = {}
    
    # Add text search results with base score
    for i, article in enumerate(text_articles):
        score = 1.0 - (i / len(text_articles)) * 0.5  # Higher rank = higher score
        combined_scores[article.id] = {
            "article": article,
            "text_score": score,
            "semantic_score": 0.0,
            "combined_score": score * 0.6  # Text weight: 60%
        }
    
    # Add semantic search results
    for result in semantic_results:
        try:
            # Extract article ID from result ID (format: "article:123")
            if result.id.startswith("article:"):
                article_id = int(result.id.split(":")[1])
                
                if article_id in combined_scores:
                    # Update existing entry
                    combined_scores[article_id]["semantic_score"] = result.similarity_score
                    combined_scores[article_id]["combined_score"] = (
                        combined_scores[article_id]["text_score"] * 0.6 +
                        result.similarity_score * 0.4  # Semantic weight: 40%
                    )
                else:
                    # Add new entry from semantic search
                    article = await article_repo.get_by_id(article_id)
                    combined_scores[article_id] = {
                        "article": article,
                        "text_score": 0.0,
                        "semantic_score": result.similarity_score,
                        "combined_score": result.similarity_score * 0.4
                    }
        except (ValueError, IndexError):
            continue
    
    # Sort by combined score and limit results
    sorted_results = sorted(
        combined_scores.values(),
        key=lambda x: x["combined_score"],
        reverse=True
    )[:limit]
    
    return {
        "articles": [item["article"] for item in sorted_results],
        "semantic_results": semantic_results,
        "scoring_details": [
            {
                "article_id": item["article"].id,
                "text_score": item["text_score"],
                "semantic_score": item["semantic_score"],
                "combined_score": item["combined_score"]
            }
            for item in sorted_results
        ],
        "total_results": len(sorted_results)
    }


@router.get("/suggestions", response_model=BaseResponse[List[str]])
async def get_search_suggestions(
    q: str = Query(..., min_length=1, max_length=100, description="Partial query"),
    limit: int = Query(default=5, ge=1, le=10, description="Maximum suggestions"),
    article_repo: ArticleRepository = Depends(get_article_repository)
) -> BaseResponse[List[str]]:
    """
    Get search suggestions based on partial query.
    
    Args:
        q: Partial search query
        limit: Maximum number of suggestions
        
    Returns:
        List of search suggestions
    """
    try:
        # This is a simplified implementation
        # In a real system, you might use a search index or pre-computed suggestions
        
        suggestions = []
        
        # Get articles that match the partial query and extract terms
        articles = await article_repo.search_articles(q, limit * 2)
        
        # Extract potential search terms from titles
        terms = set()
        for article in articles:
            words = article.title.lower().split()
            for word in words:
                if q.lower() in word and len(word) > 3:
                    terms.add(word)
        
        suggestions = list(terms)[:limit]
        
        return BaseResponse(
            success=True,
            message=f"Generated {len(suggestions)} suggestions",
            data=suggestions
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate suggestions: {str(e)}"
        )


@router.get("/similar/{article_id}", response_model=BaseResponse[List[SimilarityResult]])
async def find_similar_articles(
    article_id: int,
    limit: int = Query(default=10, ge=1, le=20, description="Maximum similar articles"),
    similarity_threshold: float = Query(default=0.6, ge=0.0, le=1.0),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    embedding_repo: EmbeddingRepository = Depends(get_embedding_repository),
    article_repo: ArticleRepository = Depends(get_article_repository)
) -> BaseResponse[List[SimilarityResult]]:
    """
    Find articles similar to a specific article.
    
    Args:
        article_id: ID of the reference article
        limit: Maximum number of similar articles
        similarity_threshold: Minimum similarity score
        
    Returns:
        List of similar articles with similarity scores
    """
    try:
        # Check if article exists
        await article_repo.get_by_id(article_id)
        
        # Get model info
        model_info = await embedding_service.get_model_info()
        model_name = model_info["model_name"]
        
        # Get embedding for the reference article
        result = await embedding_repo.get_embedding(
            content_id=str(article_id),
            content_type="article",
            model_name=model_name
        )
        
        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"No embedding found for article {article_id}. Generate embeddings first."
            )
        
        reference_embedding, _ = result
        
        # Find similar articles
        similar_results = embedding_repo.similarity_search(
            query_embedding=reference_embedding,
            model_name=model_name,
            top_k=limit + 1,  # +1 because the reference article might be included
            similarity_threshold=similarity_threshold,
            content_type="article"
        )
        
        # Filter out the reference article itself
        filtered_results = [
            result for result in similar_results
            if result.id != f"article:{article_id}"
        ][:limit]
        
        return BaseResponse(
            success=True,
            message=f"Found {len(filtered_results)} similar articles",
            data=filtered_results
        )
        
    except HTTPException:
        raise
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=f"Article not found: {article_id}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to find similar articles: {str(e)}"
        )


@router.get("/text")
async def text_search(
    query: str = Query(..., description="Search query"),
    limit: int = Query(default=20, ge=1, le=50, description="Maximum results"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    article_repo: ArticleRepository = Depends(get_article_repository)
) -> Dict[str, Any]:
    """
    Perform text-based search across articles.
    
    Args:
        query: Search query string
        limit: Maximum number of results
        offset: Offset for pagination
        
    Returns:
        Search results with articles and metadata
    """
    try:
        # Custom validation for empty query
        if not query or query.strip() == "":
            raise HTTPException(
                status_code=400,
                detail="Query cannot be empty"
            )
        
        # Validate query length
        if len(query) > 500:
            raise HTTPException(
                status_code=400,
                detail="Query too long. Maximum length is 500 characters."
            )
        
        articles = await article_repo.search_articles(query, limit, offset)
        
        return {
            "results": articles,
            "total_count": len(articles),
            "query": query,
            "limit": limit,
            "offset": offset
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Text search failed: {str(e)}"
        )


@router.post("/semantic")
async def semantic_search(
    request: SemanticSearchRequest,
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    embedding_repo: EmbeddingRepository = Depends(get_embedding_repository),
    article_repo: ArticleRepository = Depends(get_article_repository)
) -> Dict[str, Any]:
    """
    Perform semantic search using embeddings and return full article objects.
    
    Args:
        request: Semantic search parameters
        
    Returns:
        Dict with results containing full article objects and similarity scores
    """
    try:
        # Try vector search first; if no embeddings exist yet, fall back below.
        from ...models.embedding import EmbeddingRequest
        embedding_request = EmbeddingRequest(texts=[request.query], batch_size=1)
        embedding_response = await embedding_service.generate_embeddings(embedding_request)
        query_embedding = embedding_response.embeddings[0]

        try:
            similar_results = embedding_repo.similarity_search(
            query_embedding=query_embedding,
            model_name=embedding_response.model_name,
            top_k=request.limit,
            similarity_threshold=request.threshold,
            content_type=request.content_type,
            )
        except Exception as exc:
            # No embeddings table / no rows yet - fall back to a keyword search
            # so the Research tab still returns something useful.
            similar_results = []
            import logging as _logging
            _logging.getLogger(__name__).info(
                "vector similarity_search unavailable, falling back to keyword: %s", exc
            )
        
        # If vector search produced nothing, do a keyword search via the
        # article repo so the user always gets some response.
        if not similar_results:
            kw_articles = await article_repo.search_articles(request.query, request.limit)
            return {
                "results": [{"article": a, "score": 0.5} for a in (kw_articles or [])],
                "query": request.query,
                "total": len(kw_articles or []),
                "fallback_used": "keyword",
            }

        # Fetch full article details for each result
        results_with_articles = []
        for result in similar_results:
            try:
                # Extract article ID from result.id (format: "article:123")
                if result.id and ":" in result.id:
                    article_id = int(result.id.split(":")[1])
                elif result.content_id:
                    article_id = int(result.content_id)
                else:
                    continue
                
                # Fetch full article
                article = await article_repo.get_by_id(article_id)
                if article:
                    results_with_articles.append({
                        "article": article,
                        "score": result.similarity_score
                    })
            except (ValueError, IndexError, AttributeError):
                # Skip invalid results
                continue
        
        return {
            "results": results_with_articles,
            "query": request.query,
            "total": len(results_with_articles)
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Semantic search failed: {str(e)}"
        )


@router.post("/hybrid", response_model=BaseResponse[Dict[str, Any]])
async def hybrid_search(
    request: HybridSearchRequest,
    article_repo: ArticleRepository = Depends(get_article_repository),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    embedding_repo: EmbeddingRepository = Depends(get_embedding_repository)
) -> BaseResponse[Dict[str, Any]]:
    """
    Perform hybrid search combining text and semantic search.
    
    Args:
        request: Hybrid search parameters
        
    Returns:
        Combined search results
    """
    try:
        if request.text_weight + request.semantic_weight != 1.0:
            raise HTTPException(status_code=400, detail="Text weight and semantic weight must sum to 1.0")
        
        # Perform text search
        text_articles = await article_repo.search_articles(request.query, request.limit)
        
        # Perform semantic search
        from ...models.embedding import EmbeddingRequest
        embedding_request = EmbeddingRequest(texts=[request.query], batch_size=1)
        embedding_response = await embedding_service.generate_embeddings(embedding_request)
        query_embedding = embedding_response.embeddings[0]
        
        semantic_results = await embedding_repo.similarity_search(
            query_embedding=query_embedding,
            model_name=embedding_response.model_name,
            top_k=request.limit,
            similarity_threshold=request.similarity_threshold,
            content_type="article"
        )
        
        return BaseResponse(
            success=True,
            message="Hybrid search completed",
            data={
                "query": request.query,
                "text_results": text_articles,
                "semantic_results": semantic_results,
                "weights": {"text": request.text_weight, "semantic": request.semantic_weight}
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Hybrid search failed: {str(e)}"
        )


@router.get("/trending", response_model=BaseResponse[List[str]])
async def get_trending_searches() -> BaseResponse[List[str]]:
    """
    Get trending search queries.
    
    Returns:
        List of trending search terms
    """
    try:
        # Mock trending searches for now
        trending = [
            "artificial intelligence",
            "machine learning",
            "neural networks",
            "deep learning",
            "natural language processing"
        ]
        
        return BaseResponse(
            success=True,
            message="Trending searches retrieved successfully",
            data=trending
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get trending searches: {str(e)}"
        )


@router.get("/analytics", response_model=BaseResponse[Dict[str, Any]])
async def get_search_analytics() -> BaseResponse[Dict[str, Any]]:
    """
    Get search analytics and statistics.
    
    Returns:
        Search analytics data
    """
    try:
        # Mock analytics data for now
        analytics = {
            "total_searches": 1250,
            "unique_queries": 890,
            "top_queries": [
                {"query": "artificial intelligence", "count": 45},
                {"query": "machine learning", "count": 38},
                {"query": "neural networks", "count": 32}
            ],
            "search_trends": {
                "last_7_days": 156,
                "last_30_days": 678
            }
        }
        
        return BaseResponse(
            success=True,
            message="Search analytics retrieved successfully",
            data=analytics
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get search analytics: {str(e)}"
        )


@router.post("/advanced", response_model=BaseResponse[List[Article]])
async def advanced_search(
    query: str,
    sources: Optional[List[str]] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    authors: Optional[List[str]] = None,
    categories: Optional[List[str]] = None,
    limit: int = 20,
    article_repo: ArticleRepository = Depends(get_article_repository)
) -> BaseResponse[List[Article]]:
    """
    Perform advanced search with filters.
    
    Args:
        query: Search query string
        sources: Filter by news sources
        date_from: Start date filter (YYYY-MM-DD)
        date_to: End date filter (YYYY-MM-DD)
        authors: Filter by authors
        categories: Filter by categories
        limit: Maximum number of results
        
    Returns:
        Filtered search results
    """
    try:
        # For now, just perform basic text search
        # Advanced filtering would require more complex repository methods
        articles = await article_repo.search_articles(query, limit)
        
        return BaseResponse(
            success=True,
            message="Advanced search completed",
            data=articles
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Advanced search failed: {str(e)}"
        )


@router.get("/export", response_model=BaseResponse[Dict[str, Any]])
async def export_search_results(
    query: str = Query(..., description="Search query"),
    format: str = Query(default="json", description="Export format (json, csv)"),
    limit: int = Query(default=100, ge=1, le=1000, description="Maximum results"),
    article_repo: ArticleRepository = Depends(get_article_repository)
) -> BaseResponse[Dict[str, Any]]:
    """
    Export search results in various formats.
    
    Args:
        query: Search query string
        format: Export format (json or csv)
        limit: Maximum number of results
        
    Returns:
        Export data and metadata
    """
    try:
        if format not in ["json", "csv"]:
            raise HTTPException(status_code=400, detail="Format must be 'json' or 'csv'")
        
        articles = await article_repo.search_articles(query, limit)
        
        export_data = {
            "query": query,
            "format": format,
            "total_results": len(articles),
            "exported_at": "2024-01-01T00:00:00Z",  # Would use actual timestamp
            "data": articles
        }
        
        return BaseResponse(
            success=True,
            message=f"Search results exported in {format} format",
            data=export_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Export failed: {str(e)}"
        )
