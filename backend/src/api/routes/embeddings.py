"""
Embedding Routes
==============

API routes for embedding generation, storage, and similarity search operations.
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Dict, Any, List, Optional

from ...services import EmbeddingService
from ...services.embedding_service import get_shared_embedding_service
from ...repositories import EmbeddingRepository, ArticleRepository
from ...models.embedding import (
    EmbeddingRequest,
    EmbeddingResponse,
    SimilarityRequest,
    SimilarityResult,
    EmbeddingStats
)
from ...models.api import BaseResponse, AsyncTaskResponse
from ...core.exceptions import EmbeddingError, ValidationError

router = APIRouter(prefix="/embeddings", tags=["Embeddings"])

# Dependency injection
def get_embedding_service() -> EmbeddingService:
    """Get the shared embedding service singleton (model loads once, not per-request)."""
    return get_shared_embedding_service()

def get_embedding_repository() -> EmbeddingRepository:
    """Get embedding repository instance."""
    return EmbeddingRepository()

def get_article_repository() -> ArticleRepository:
    """Get article repository instance."""
    return ArticleRepository()


@router.post("/generate", response_model=BaseResponse[EmbeddingResponse])
async def generate_embeddings(
    request: EmbeddingRequest,
    service: EmbeddingService = Depends(get_embedding_service)
) -> BaseResponse[EmbeddingResponse]:
    """
    Generate embeddings for the provided texts.
    
    Args:
        request: Embedding generation request
        
    Returns:
        Generated embeddings with metadata
    """
    try:
        response = await service.generate_embeddings(request)
        
        return BaseResponse(
            success=True,
            message=f"Generated {len(response.embeddings)} embeddings",
            data=response
        )
        
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except EmbeddingError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.post("/similarity", response_model=BaseResponse[List[SimilarityResult]])
async def similarity_search(
    request: SimilarityRequest,
    content_type: Optional[str] = Query(default=None, description="Filter by content type"),
    service: EmbeddingService = Depends(get_embedding_service),
    repo: EmbeddingRepository = Depends(get_embedding_repository)
) -> BaseResponse[List[SimilarityResult]]:
    """
    Perform similarity search using embedding vectors.
    
    Args:
        request: Similarity search request
        content_type: Optional filter by content type
        
    Returns:
        List of similar items with scores
    """
    try:
        # Generate embedding for query text
        query_embedding_request = EmbeddingRequest(
            texts=[request.query_text],
            batch_size=1
        )
        
        query_response = await service.generate_embeddings(query_embedding_request)
        query_embedding = query_response.embeddings[0]
        
        # Perform similarity search
        results = await repo.similarity_search(
            query_embedding=query_embedding,
            model_name=query_response.model_name,
            top_k=request.top_k,
            similarity_threshold=request.similarity_threshold,
            content_type=content_type
        )
        
        return BaseResponse(
            success=True,
            message=f"Found {len(results)} similar items",
            data=results
        )
        
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Similarity search failed: {str(e)}")


@router.post("/articles/generate", response_model=AsyncTaskResponse)
async def generate_article_embeddings(
    article_ids: Optional[List[int]] = None,
    limit: int = Query(default=100, ge=1, le=500, description="Max articles to process"),
    service: EmbeddingService = Depends(get_embedding_service),
    embedding_repo: EmbeddingRepository = Depends(get_embedding_repository),
    article_repo: ArticleRepository = Depends(get_article_repository)
) -> AsyncTaskResponse:
    """
    Generate embeddings for articles.
    
    Args:
        article_ids: Optional list of specific article IDs to process
        limit: Maximum number of articles to process (if article_ids not provided)
        
    Returns:
        Async task information for tracking progress
    """
    try:
        import uuid
        task_id = str(uuid.uuid4())
        
        # This would typically be implemented as a background task
        # For now, return a placeholder response
        
        return AsyncTaskResponse(
            task_id=task_id,
            status="initiated",
            progress_percentage=0.0
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start embedding generation: {str(e)}"
        )


@router.get("/articles/{article_id}", response_model=BaseResponse[Dict[str, Any]])
async def get_article_embedding(
    article_id: int,
    model_name: Optional[str] = Query(default=None, description="Embedding model name"),
    service: EmbeddingService = Depends(get_embedding_service),
    repo: EmbeddingRepository = Depends(get_embedding_repository)
) -> BaseResponse[Dict[str, Any]]:
    """
    Get embedding for a specific article.
    
    Args:
        article_id: Article ID
        model_name: Optional model name filter
        
    Returns:
        Article embedding information
    """
    try:
        # Use default model if not specified
        if not model_name:
            model_info = await service.get_model_info()
            model_name = model_info["model_name"]
        
        # Get embedding from repository
        result = await repo.get_embedding(
            content_id=str(article_id),
            content_type="article",
            model_name=model_name
        )
        
        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"No embedding found for article {article_id}"
            )
        
        embedding_vector, metadata = result
        
        return BaseResponse(
            success=True,
            message="Article embedding retrieved",
            data={
                "article_id": article_id,
                "model_name": model_name,
                "embedding_dimension": len(embedding_vector),
                "metadata": metadata,
                "has_embedding": True
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get article embedding: {str(e)}"
        )


@router.delete("/articles/{article_id}", response_model=BaseResponse[Dict[str, Any]])
async def delete_article_embeddings(
    article_id: int,
    model_name: Optional[str] = Query(default=None, description="Specific model to delete"),
    repo: EmbeddingRepository = Depends(get_embedding_repository)
) -> BaseResponse[Dict[str, Any]]:
    """
    Delete embeddings for a specific article.
    
    Args:
        article_id: Article ID
        model_name: Optional specific model name to delete
        
    Returns:
        Deletion result
    """
    try:
        deleted_count = await repo.delete_embeddings(
            content_id=str(article_id),
            content_type="article",
            model_name=model_name
        )
        
        return BaseResponse(
            success=True,
            message=f"Deleted {deleted_count} embeddings for article {article_id}",
            data={
                "article_id": article_id,
                "deleted_count": deleted_count
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete embeddings: {str(e)}"
        )


@router.get("/stats", response_model=BaseResponse[EmbeddingStats])
async def get_embedding_stats(
    repo: EmbeddingRepository = Depends(get_embedding_repository)
) -> BaseResponse[EmbeddingStats]:
    """
    Get comprehensive embedding statistics.
    
    Returns:
        Detailed embedding statistics
    """
    try:
        stats_data = await repo.get_stats()
        
        # Convert to EmbeddingStats model
        models_used = {
            item["model"]: item["count"] 
            for item in stats_data.get("by_model", [])
        }
        
        stats = EmbeddingStats(
            total_embeddings=stats_data.get("total_embeddings", 0),
            models_used=models_used,
            average_dimension=stats_data.get("average_dimension", 0.0),
            storage_size_mb=stats_data.get("estimated_storage_mb", 0.0)
        )
        
        return BaseResponse(
            success=True,
            message="Embedding statistics retrieved",
            data=stats
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get embedding statistics: {str(e)}"
        )


@router.get("/status", response_model=BaseResponse[Dict[str, Any]])
async def get_embedding_status(
    service: EmbeddingService = Depends(get_embedding_service)
) -> BaseResponse[Dict[str, Any]]:
    """
    Get the status of the embedding service.
    
    Returns:
        Service status and model information
    """
    try:
        health_status = await service.health_check()
        model_info = await service.get_model_info()
        
        return BaseResponse(
            success=True,
            message="Embedding service status retrieved",
            data={
                "health": health_status,
                "model_info": model_info,
                "embedding_ready": health_status.get("status") == "healthy"
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get embedding status: {str(e)}"
        )


@router.post("/maintenance/cleanup", response_model=BaseResponse[Dict[str, Any]])
async def cleanup_embeddings(
    repo: EmbeddingRepository = Depends(get_embedding_repository)
) -> BaseResponse[Dict[str, Any]]:
    """
    Perform maintenance cleanup of orphaned embedding metadata.
    
    Returns:
        Cleanup results
    """
    try:
        cleaned_count = await repo.cleanup_orphaned_metadata()
        
        return BaseResponse(
            success=True,
            message="Embedding cleanup completed",
            data={
                "cleaned_records": cleaned_count
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Cleanup failed: {str(e)}"
        )
