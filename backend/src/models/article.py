"""
Article Data Models
==================

Pydantic models for article data structures.
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ArticleBase(BaseModel):
    """Base article model with common fields."""
    title: str = Field(..., min_length=1, max_length=500)
    content: Optional[str] = Field(None, description="Full article content")
    summary: Optional[str] = Field(None, description="AI-generated summary")
    source: str = Field(..., min_length=1, max_length=100)
    url: str = Field(..., description="Original article URL")
    published_date: Optional[datetime] = Field(None, description="Publication date")
    image_url: Optional[str] = Field(None, description="Hero/thumbnail image URL extracted from the feed")


class ArticleCreate(ArticleBase):
    """Model for creating new articles."""
    author: Optional[str] = Field(None, description="Article author")
    published_at: Optional[datetime] = Field(None, description="Publication timestamp")
    categories: Optional[List[str]] = Field(None, description="Article categories")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class ArticleUpdate(BaseModel):
    """Model for updating existing articles."""
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    content: Optional[str] = None
    summary: Optional[str] = None
    url: Optional[str] = None


class Article(ArticleBase):
    """Complete article model with all fields."""
    id: int = Field(..., description="Unique article identifier")
    author: Optional[str] = Field(None, description="Article author")
    published_at: Optional[datetime] = Field(None, description="Publication timestamp")
    categories: Optional[List[str]] = Field(None, description="Article categories")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")
    embedding: Optional[List[float]] = Field(None, description="Vector embedding")
    embedding_model: Optional[str] = Field(None, description="Model used for embedding")
    embedding_dim: Optional[int] = Field(None, description="Embedding dimension")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
    is_archived: Optional[bool] = Field(False, description="Whether article is archived")
    view_count: Optional[int] = Field(0, description="Number of times article has been viewed")
    embedding_generated: Optional[bool] = Field(False, description="Whether embedding has been generated")
    summary_generated: Optional[bool] = Field(False, description="Whether AI summary has been generated")

    model_config = {"from_attributes": True}


class ArticleSummary(BaseModel):
    """Model for article summary view (basic article info + summary)."""
    id: int = Field(..., description="Article ID")
    title: str = Field(..., description="Article title")
    summary: str = Field(..., description="Article summary")
    source: str = Field(..., description="Article source")
    published_date: Optional[datetime] = Field(None, description="Publication date")
    url: str = Field(..., description="Article URL")
    # Optional metadata fields for summarization details
    word_count: Optional[int] = Field(None, description="Word count of summary")
    original_length: Optional[int] = Field(None, description="Original content length")
    summary_length: Optional[int] = Field(None, description="Summary length")
    compression_ratio: Optional[float] = Field(None, description="Compression ratio")
    processing_time: Optional[float] = Field(None, description="Processing time in seconds")
    model_used: Optional[str] = Field(None, description="Model used for generation")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Creation timestamp")


class AISummary(BaseModel):
    """Model for AI-generated summary information."""
    summary: str = Field(..., description="Generated summary text")
    provider: Optional[str] = Field(None, description="AI provider used")
    model: Optional[str] = Field(None, description="Model used for generation")
    content_length: Optional[int] = Field(None, description="Original content length")
    summary_length: Optional[int] = Field(None, description="Summary length")
    key_points: Optional[List[str]] = Field(default_factory=list, description="Key points extracted")
    word_count: Optional[int] = Field(None, description="Word count of summary")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ArticleStats(BaseModel):
    """Model for article statistics."""
    total_articles: int = Field(0, description="Total number of articles")
    articles_today: int = Field(0, description="Articles ingested today")
    articles_this_week: int = Field(0, description="Articles ingested in the last 7 days")
    unique_sources: int = Field(0, description="Number of distinct sources")
    articles_with_summaries: int = Field(0, description="Articles with AI summaries")
    articles_with_embeddings: int = Field(0, description="Articles with embeddings")
    sources: Dict[str, int] = Field(default_factory=dict, description="Articles per source")
    top_sources: List[Dict[str, Any]] = Field(default_factory=list, description="Top article sources with counts")
    recent_articles: int = Field(0, description="Number of recent articles")
    date_range: Optional[Dict[str, Optional[datetime]]] = Field(None, description="Date range of articles")


class ArticleSearchRequest(BaseModel):
    """Model for article search requests."""
    query: Optional[str] = Field(None, max_length=500)
    limit: int = Field(20, ge=1, le=100)
    source: Optional[str] = None
    similarity_threshold: float = Field(0.7, ge=0.0, le=1.0)


class ArticleSearchResult(BaseModel):
    """Model for article search results."""
    article: Article
    similarity_score: float = Field(..., ge=0.0, le=1.0)
    matching_snippets: List[str] = Field(default_factory=list)


class SummarizationRequest(BaseModel):
    """Model for article summarization requests."""
    content: str = Field(..., min_length=1, description="Content to summarize")
    title: Optional[str] = Field(None, description="Article title")
    max_length: int = Field(200, ge=50, le=1000, description="Maximum summary length in words")
    style: str = Field("concise", pattern="^(concise|detailed|bullet_points)$", description="Summary style")
    focus_keywords: Optional[List[str]] = Field(None, description="Keywords to focus on in summary")


class BatchSummarizationRequest(BaseModel):
    """Model for batch summarization requests."""
    requests: List[SummarizationRequest] = Field(..., min_length=1, max_length=10, description="List of summarization requests")
    batch_size: int = Field(5, ge=1, le=10, description="Batch processing size")


class IngestRequest(BaseModel):
    """Model for news ingestion requests."""
    feed_urls: List[str] = Field(..., min_length=1, description="List of RSS feed URLs to ingest")


class IngestResponse(BaseModel):
    """Model for news ingestion response data."""
    processed: int = Field(..., description="Total number of articles processed")
    new_articles: int = Field(..., description="Number of new articles added")
    duplicates: int = Field(..., description="Number of duplicate articles skipped")
    errors: List[str] = Field(default_factory=list, description="Any error messages encountered")


class AgentEvent(BaseModel):
    """
    Event emitted by the agentic research loop.

    Used by ``AgenticResearchService.run`` (M1) and serialised over SSE by
    the ``POST /api/research`` route (M2). The same shape is consumed by
    ``ResearchMode.tsx`` on the frontend (M3); keep this contract stable.

    ``type`` is one of:
      - ``"phase"``  - a phase transition (e.g. "Decomposing", "Searching (i/N)",
        "Synthesizing", "done"). ``data`` is a string label.
      - ``"token"``  - a streaming token chunk during synthesis (M2). ``data``
        is the token text. M1 does not emit token events.
      - ``"done"``   - terminal event carrying the full assembled report.
        ``data`` is the markdown report string.
      - ``"error"``  - terminal error event. ``data`` is a human-readable
        error message.
    """

    type: str = Field(
        ...,
        description="Event type: 'phase' | 'token' | 'done' | 'error'",
    )
    data: Any = Field(
        ...,
        description="Event payload: string label, token chunk, or final report",
    )
