"""
Search Service
==============

Semantic search service with vector similarity, RAG integration, and reranking.
"""

import sqlite3
import time
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from pathlib import Path
import numpy as np

from src.models.search import SearchRequest, SearchResponse, SearchResultItem, SearchHealthResponse
from vectorstore.embeddings import EmbeddingGenerator
import logging
from src.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class SearchService:
    """
    Semantic search service using vector embeddings.
    
    Features:
    - Vector similarity search
    - Metadata filtering
    - Result reranking
    - RAG pipeline integration (optional)
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize search service.
        
        Args:
            db_path: Path to SQLite database (defaults to settings)
        """
        self.db_path = db_path or settings.get_database_file_path()
        
        self.embedding_generator = None
        self._initialized = False
        
        logger.info(f"SearchService initialized with db: {self.db_path}")
    
    async def initialize(self):
        """Initialize embedding generator and verify database."""
        if self._initialized:
            return
        
        try:
            # Initialize embedding generator (it auto-initializes in __init__)
            if not self.embedding_generator:
                self.embedding_generator = EmbeddingGenerator()
            
            # Verify database exists
            db_file = Path(self.db_path)
            if not db_file.exists():
                logger.warning(f"Database file not found: {self.db_path}")
            
            self._initialized = True
            logger.info("SearchService initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize SearchService: {e}")
            raise
    
    async def health_check(self) -> SearchHealthResponse:
        """
        Check search service health and statistics.
        
        Returns:
            Health status with statistics
        """
        try:
            await self.initialize()
            
            # Get statistics from database
            stats = self._get_index_statistics()
            
            return SearchHealthResponse(
                status="healthy" if stats['total'] > 0 else "no_data",
                embeddings_available=self.embedding_generator is not None,
                total_indexed_articles=stats['total'],
                last_indexed=stats.get('last_indexed'),
                vector_dimensions=384 if self.embedding_generator else None
            )
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return SearchHealthResponse(
                status="unhealthy",
                embeddings_available=False,
                total_indexed_articles=0,
                last_indexed=None,
                vector_dimensions=None
            )
    
    async def search(self, request: SearchRequest) -> SearchResponse:
        """
        Perform semantic search on articles.
        
        Args:
            request: Search request with query and filters
            
        Returns:
            Ranked search results
        """
        start_time = time.time()
        
        try:
            await self.initialize()
            
            # Generate query embedding
            query_embedding = await self._generate_query_embedding(request.query)
            
            # Retrieve candidates using vector similarity
            candidates = await self._vector_search(
                query_embedding=query_embedding,
                limit=request.limit * 3,  # Get more candidates for reranking
                min_score=request.min_score,
                filters={
                    'sources': request.sources,
                    'categories': request.categories,
                    'date_from': request.date_from,
                    'date_to': request.date_to
                }
            )
            
            # Apply reranking if requested
            if request.use_reranking and len(candidates) > 0:
                candidates = await self._rerank_results(
                    query=request.query,
                    candidates=candidates,
                    top_k=request.limit
                )
            else:
                candidates = candidates[:request.limit]
            
            # Convert to response format
            results = []
            for article, score, rerank_score in candidates:
                result_item = SearchResultItem(
                    # ``SearchResultItem.id`` is typed as ``str`` but the
                    # ``articles`` PK is an integer — coerce to keep the
                    # contract intact.
                    id=str(article['id']),
                    title=article['title'],
                    url=article['url'],
                    source=article['source'],
                    published_at=article['published_at'],
                    content=article.get('content_preview'),
                    summary=article.get('ai_summary') if request.include_summary else None,
                    categories=article.get('categories', []),
                    keywords=article.get('keywords', []),
                    similarity_score=score,
                    relevance_score=rerank_score,
                    metadata=article.get('metadata', {})
                )
                results.append(result_item)
            
            execution_time = (time.time() - start_time) * 1000  # Convert to ms
            
            return SearchResponse(
                query=request.query,
                results=results,
                total_results=len(candidates),
                execution_time_ms=round(execution_time, 2),
                filters_applied=self._get_applied_filters(request),
                metadata={
                    'embedding_model': 'all-MiniLM-L6-v2',
                    'reranking_applied': request.use_reranking,
                    'candidates_retrieved': len(candidates)
                }
            )
            
        except Exception as e:
            logger.error(f"Search failed: {e}", exc_info=True)
            execution_time = (time.time() - start_time) * 1000
            
            return SearchResponse(
                query=request.query,
                results=[],
                total_results=0,
                execution_time_ms=round(execution_time, 2),
                filters_applied={},
                metadata={'error': str(e)}
            )
    
    async def _generate_query_embedding(self, query: str) -> np.ndarray:
        """
        Generate embedding for search query.
        
        Args:
            query: Search query text
            
        Returns:
            Query embedding vector
        """
        try:
            embeddings = await self.embedding_generator.generate_embeddings([query])
            return embeddings[0]
        except Exception as e:
            logger.error(f"Failed to generate query embedding: {e}")
            raise
    
    async def _vector_search(
        self,
        query_embedding: np.ndarray,
        limit: int,
        min_score: float = 0.0,
        filters: Optional[Dict] = None
    ) -> List[Tuple[Dict, float, Optional[float]]]:
        """
        Perform vector similarity search.
        
        Args:
            query_embedding: Query vector
            limit: Maximum results
            min_score: Minimum similarity threshold
            filters: Optional filters (sources, categories, dates)
            
        Returns:
            List of (article_dict, similarity_score, rerank_score) tuples
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Build query with filters. Column names match the live
            # ``articles`` schema (see ``ArticleRepository._row_to_article``):
            # ``published_at`` (not published_date), ``summary`` (not
            # ai_summary). ``keywords`` doesn't exist on this table —
            # we coalesce it to an empty list downstream.
            sql = """
                SELECT
                    a.id, a.title, a.url, a.source, a.published_at,
                    a.summary AS ai_summary, a.categories,
                    SUBSTR(a.content, 1, 500) as content_preview,
                    e.embedding
                FROM articles a
                INNER JOIN article_embeddings e ON a.id = e.article_id
                WHERE 1=1
            """

            params = []

            # Apply filters
            if filters:
                if filters.get('sources'):
                    placeholders = ','.join('?' * len(filters['sources']))
                    sql += f" AND a.source IN ({placeholders})"
                    params.extend(filters['sources'])

                if filters.get('date_from'):
                    sql += " AND a.published_at >= ?"
                    params.append(filters['date_from'].isoformat())

                if filters.get('date_to'):
                    sql += " AND a.published_at <= ?"
                    params.append(filters['date_to'].isoformat())
            
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            conn.close()
            
            # Calculate similarity scores
            results = []
            for row in rows:
                try:
                    # Parse embedding
                    import json
                    article_embedding = np.array(json.loads(row['embedding']))
                    
                    # Calculate cosine similarity
                    similarity = self._cosine_similarity(query_embedding, article_embedding)
                    
                    if similarity >= min_score:
                        # ``published_at`` may be NULL or non-ISO on some
                        # legacy rows — fall back to ``datetime.min`` so
                        # the recency reranker doesn't crash on bad data.
                        try:
                            pub_at = datetime.fromisoformat(row['published_at'])
                        except (TypeError, ValueError):
                            pub_at = datetime.min

                        article_dict = {
                            'id': row['id'],
                            'title': row['title'],
                            'url': row['url'],
                            'source': row['source'],
                            'published_at': pub_at,
                            'ai_summary': row['ai_summary'],
                            'categories': (
                                json.loads(row['categories'])
                                if row['categories'] else []
                            ),
                            # ``keywords`` column was dropped from the
                            # schema; legacy callers still expect the key.
                            'keywords': [],
                            'content_preview': row['content_preview']
                        }

                        results.append((article_dict, float(similarity), None))
                        
                except Exception as e:
                    logger.warning(f"Error processing article {row.get('id')}: {e}")
                    continue
            
            # Sort by similarity score
            results.sort(key=lambda x: x[1], reverse=True)
            
            return results[:limit]
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}", exc_info=True)
            return []
    
    async def _rerank_results(
        self,
        query: str,
        candidates: List[Tuple[Dict, float, Optional[float]]],
        top_k: int
    ) -> List[Tuple[Dict, float, float]]:
        """
        Rerank results using additional signals.
        
        Args:
            query: Original query
            candidates: Initial candidates with similarity scores
            top_k: Number of top results to return
            
        Returns:
            Reranked results with updated scores
        """
        try:
            query_lower = query.lower()
            query_terms = set(query_lower.split())
            
            reranked = []
            for article, similarity_score, _ in candidates:
                # Calculate reranking score based on multiple factors
                title_lower = article['title'].lower()
                
                # Factor 1: Title keyword match (weight: 0.3)
                title_terms = set(title_lower.split())
                title_match = len(query_terms & title_terms) / len(query_terms) if query_terms else 0
                
                # Factor 2: Vector similarity (weight: 0.5)
                vector_score = similarity_score
                
                # Factor 3: Recency boost (weight: 0.2)
                days_old = (datetime.now() - article['published_at']).days
                recency_score = max(0, 1 - (days_old / 365))  # Decay over a year
                
                # Combined reranking score
                rerank_score = (
                    0.5 * vector_score +
                    0.3 * title_match +
                    0.2 * recency_score
                )
                
                reranked.append((article, similarity_score, rerank_score))
            
            # Sort by reranking score
            reranked.sort(key=lambda x: x[2], reverse=True)
            
            return reranked[:top_k]
            
        except Exception as e:
            logger.error(f"Reranking failed: {e}")
            # Return original results if reranking fails
            return [(article, score, score) for article, score, _ in candidates[:top_k]]
    
    @staticmethod
    def _cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
        """
        Calculate cosine similarity between two vectors.
        
        Args:
            vec1: First vector
            vec2: Second vector
            
        Returns:
            Similarity score (0-1)
        """
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(dot_product / (norm1 * norm2))
    
    def _get_index_statistics(self) -> Dict[str, Any]:
        """Get statistics about indexed articles."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get total count
            cursor.execute("""
                SELECT COUNT(*) FROM article_embeddings
            """)
            total = cursor.fetchone()[0]
            
            # Get last indexed
            cursor.execute("""
                SELECT MAX(created_at) FROM article_embeddings
            """)
            last_indexed_str = cursor.fetchone()[0]
            
            conn.close()
            
            last_indexed = None
            if last_indexed_str:
                try:
                    last_indexed = datetime.fromisoformat(last_indexed_str)
                except (ValueError, TypeError):
                    pass
            
            return {
                'total': total,
                'last_indexed': last_indexed
            }
            
        except Exception as e:
            logger.error(f"Failed to get index statistics: {e}")
            return {'total': 0, 'last_indexed': None}
    
    @staticmethod
    def _get_applied_filters(request: SearchRequest) -> Dict[str, Any]:
        """Extract applied filters from request."""
        filters = {}
        
        if request.sources:
            filters['sources'] = request.sources
        if request.categories:
            filters['categories'] = request.categories
        if request.date_from:
            filters['date_from'] = request.date_from.isoformat()
        if request.date_to:
            filters['date_to'] = request.date_to.isoformat()
        if request.min_score > 0:
            filters['min_score'] = request.min_score
        
        return filters


# Global service instance
_search_service: Optional[SearchService] = None


def get_search_service() -> SearchService:
    """
    Get or create global search service instance.
    
    Returns:
        SearchService instance
    """
    global _search_service
    
    if _search_service is None:
        _search_service = SearchService()
    
    return _search_service
