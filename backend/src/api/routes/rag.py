"""
RAG API Routes
=============

API endpoints for Retrieval-Augmented Generation functionality.
Combines semantic search with LLM generation for intelligent Q&A.
"""

from fastapi import APIRouter, HTTPException
from typing import Optional
from pydantic import BaseModel, Field

from src.services.rag_service import get_rag_pipeline
from ...models.api import BaseResponse
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/rag", tags=["RAG"])


class RAGQueryRequest(BaseModel):
    """Request model for RAG queries."""
    question: str = Field(..., min_length=1, max_length=500, description="User's question")
    top_k: int = Field(5, ge=1, le=10, description="Number of articles to retrieve")
    min_score: float = Field(0.7, ge=0.0, le=1.0, description="Minimum similarity score")
    use_reranking: bool = Field(True, description="Apply reranking to results")
    include_sources: bool = Field(True, description="Include source articles in response")


class RAGSummarizeRequest(BaseModel):
    """Request model for context-aware summarization."""
    text: str = Field(..., min_length=1, description="Text to summarize")
    context_query: Optional[str] = Field(None, description="Query to find related context")
    max_context_articles: int = Field(3, ge=0, le=5, description="Max context articles")


@router.post("/query")
async def rag_query(request: RAGQueryRequest):
    """
    Answer a question using RAG pipeline.
    
    This endpoint:
    1. Retrieves relevant articles using semantic search
    2. Builds context from top matches
    3. Generates answer using LLM (Groq)
    4. Returns answer with sources and confidence score
    
    Example:
        POST /api/rag/query
        {
            "question": "What are the latest developments in AI?",
            "top_k": 5,
            "include_sources": true
        }
    """
    try:
        rag = await get_rag_pipeline()
        
        result = await rag.query(
            question=request.question,
            top_k=request.top_k,
            min_score=request.min_score,
            use_reranking=request.use_reranking,
            include_sources=request.include_sources
        )
        
        return BaseResponse(
            success=True,
            message="Query processed successfully",
            data=result
        )
        
    except Exception as e:
        logger.error(f"RAG query failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"RAG query failed: {str(e)}"
        )


@router.post("/summarize")
async def rag_summarize(request: RAGSummarizeRequest):
    """
    Summarize text with additional context from related articles.
    
    This endpoint:
    1. Optionally retrieves related articles for context
    2. Combines input text with context
    3. Generates comprehensive summary using LLM
    
    Example:
        POST /api/rag/summarize
        {
            "text": "Long article text...",
            "context_query": "AI developments",
            "max_context_articles": 3
        }
    """
    try:
        rag = await get_rag_pipeline()
        
        result = await rag.summarize_with_context(
            text=request.text,
            context_query=request.context_query,
            max_context_articles=request.max_context_articles
        )
        
        return BaseResponse(
            success=True,
            message="Summary generated successfully",
            data=result
        )
        
    except Exception as e:
        logger.error(f"RAG summarization failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"RAG summarization failed: {str(e)}"
        )


@router.get("/health")
async def rag_health():
    """
    Check RAG pipeline health status.
    
    Returns information about:
    - Search service availability
    - LLM provider status
    - Pipeline initialization state
    """
    try:
        rag = await get_rag_pipeline()
        
        # Check if services are initialized
        search_available = rag.search_service is not None and rag.search_service._initialized
        llm_available = rag.llm_provider is not None
        
        # Get LLM provider info if available
        llm_info = {}
        if llm_available:
            llm_info = {
                "provider": rag.llm_provider.__class__.__name__,
                "available": await rag.llm_provider.is_available()
            }
        
        status = "healthy" if (search_available and llm_available) else "degraded"
        
        return BaseResponse(
            success=True,
            message=f"RAG pipeline is {status}",
            data={
                "status": status,
                "search_service": "available" if search_available else "unavailable",
                "llm_service": "available" if llm_available else "unavailable",
                "llm_info": llm_info,
                "pipeline_initialized": rag._initialized
            }
        )
        
    except Exception as e:
        logger.error(f"RAG health check failed: {e}")
        return BaseResponse(
            success=False,
            message="RAG pipeline health check failed",
            data={
                "status": "unhealthy",
                "error": str(e)
            }
        )


@router.get("/info")
async def rag_info():
    """
    Get information about RAG pipeline capabilities.
    
    Returns:
        Pipeline features, models, and configuration
    """
    return BaseResponse(
        success=True,
        message="RAG pipeline information",
        data={
            "name": "AI Tech News RAG Pipeline",
            "version": "1.0.0",
            "features": [
                "Semantic search using embeddings (all-MiniLM-L6-v2)",
                "Multi-LLM support (Groq, Ollama, Claude)",
                "Result reranking for improved relevance",
                "Source attribution and confidence scoring",
                "Context-aware summarization"
            ],
            "endpoints": {
                "query": "/api/rag/query - Question answering with sources",
                "summarize": "/api/rag/summarize - Context-aware summarization",
                "health": "/api/rag/health - Health check",
                "info": "/api/rag/info - This endpoint"
            },
            "configuration": {
                "default_top_k": 5,
                "min_similarity_score": 0.7,
                "embedding_dimensions": 384,
                "reranking_enabled": True
            }
        }
    )
