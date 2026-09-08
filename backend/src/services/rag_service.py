"""
RAG Service
===========

Retrieval-Augmented Generation pipeline. Combines:
  1. Semantic search via SearchService (retrieval)
  2. Context construction from top-k articles
  3. LLM generation via SummarizationService (Ollama by default)

Migrated from the legacy `backend/rag/pipeline.py` as part of the
src/-only consolidation. The public surface (`RAGPipeline`,
`get_rag_pipeline`) is unchanged so route code keeps working.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..core.config import get_settings
from ..models.article import SummarizationRequest

logger = logging.getLogger(__name__)
settings = get_settings()


class RAGPipeline:
    """Retrieval-Augmented Generation pipeline."""

    def __init__(self):
        self.search_service = None
        self.summarization_service = None
        self._initialized = False
        logger.info("RAG Pipeline created - awaiting initialization")

    async def initialize(self):
        """Lazily wire up SearchService and SummarizationService."""
        if self._initialized:
            return
        try:
            from .search_service import SearchService
            from .summarization_service import SummarizationService

            self.search_service = SearchService()
            await self.search_service.initialize()
            # SummarizationService talks to Ollama; cheap to construct.
            self.summarization_service = SummarizationService()

            self._initialized = True
            logger.info("RAG Pipeline initialized successfully")
        except Exception as exc:
            logger.error("Failed to initialize RAG Pipeline: %s", exc)
            raise

    async def query(
        self,
        question: str,
        top_k: int = 5,
        min_score: float = 0.7,
        use_reranking: bool = True,
        include_sources: bool = True,
    ) -> Dict[str, Any]:
        """Answer a question using retrieval + generation."""
        try:
            await self.initialize()

            search_request = self._build_search_request(
                query=question,
                top_k=top_k,
                min_score=min_score,
                use_reranking=use_reranking,
            )
            search_results = await self.search_service.search(search_request)
            articles_for_context = list(search_results.results)

            # Fallback: vector search may return nothing if embeddings have not
            # been generated yet. In that case, use a simple keyword + recency
            # query against the SQL store so the chat is still useful.
            if not articles_for_context:
                fallback = await self._fallback_keyword_search(question, top_k)
                if not fallback:
                    return {
                        "answer": "I couldn\'t find any relevant articles to answer your question.",
                        "sources": [],
                        "confidence": 0.0,
                        "metadata": {
                            "articles_found": 0,
                            "fallback_used": True,
                        },
                    }
                articles_for_context = fallback

            context = self._build_context(articles_for_context)
            answer = await self._generate_answer(question, context)

            return {
                "answer": answer["text"],
                "sources": self._format_sources(articles_for_context)
                if include_sources
                else [],
                "confidence": self._calculate_confidence(articles_for_context),
                "metadata": {
                    "articles_found": len(articles_for_context),
                    "search_time_ms": getattr(
                        search_results, "execution_time_ms", 0
                    ),
                    "llm_model": answer.get("model"),
                    "llm_provider": "ollama",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            }
        except Exception as exc:
            logger.error("RAG query failed: %s", exc, exc_info=True)
            return {
                "answer": f"Sorry, I encountered an error: {exc}",
                "sources": [],
                "confidence": 0.0,
                "metadata": {"error": str(exc)},
            }

    async def summarize_with_context(
        self,
        text: str,
        context_query: Optional[str] = None,
        max_context_articles: int = 3,
    ) -> Dict[str, Any]:
        """Summarize `text` with extra context fetched via `context_query`."""
        try:
            await self.initialize()

            context_articles: List[Any] = []
            if context_query:
                req = self._build_search_request(
                    query=context_query, top_k=max_context_articles, min_score=0.6
                )
                search_results = await self.search_service.search(req)
                context_articles = search_results.results

            ctx = f"Text to summarize:\n{text}\n\n"
            if context_articles:
                ctx += "Related context:\n"
                for i, art in enumerate(context_articles, 1):
                    ctx += f"{i}. {art.title}: {(art.summary or art.content or '')[:200]}\n"

            prompt = (
                "Based on the following text and related context, provide a "
                "comprehensive summary. Focus on key points, technical details, "
                "and implications.\n\n"
                f"{ctx}\n\nSummary:"
            )

            article_summary = await self.summarization_service.summarize_content(
                SummarizationRequest(content=prompt, max_length=300)
            )

            return {
                "summary": article_summary.summary,
                "context_articles": self._format_sources(context_articles),
                "metadata": {
                    "context_articles_count": len(context_articles),
                    "model": article_summary.model_used,
                    "provider": "ollama",
                },
            }
        except Exception as exc:
            logger.error("Context summarization failed: %s", exc)
            return {
                "summary": f"Summarization failed: {exc}",
                "context_articles": [],
                "metadata": {"error": str(exc)},
            }

    # --------------------------- helpers --------------------------- #

    async def _fallback_keyword_search(self, question: str, top_k: int) -> list:
        """SQL fallback when vector search returns 0 results."""
        import sqlite3
        from types import SimpleNamespace
        try:
            db_path = settings.get_database_file_path()
            keywords = [w for w in question.split() if len(w) > 3][:5]
            con = sqlite3.connect(db_path)
            con.row_factory = sqlite3.Row
            if keywords:
                clauses = " OR ".join("(title LIKE ? OR content LIKE ?)" for _ in keywords)
                params = []
                for k in keywords:
                    like = f"%{k}%"
                    params.extend([like, like])
                sql = ("SELECT id, title, url, source, content, summary, published_at "
                       f"FROM articles WHERE is_archived = 0 AND ({clauses}) "
                       "ORDER BY created_at DESC LIMIT ?")
                params.append(top_k)
            else:
                sql = ("SELECT id, title, url, source, content, summary, published_at "
                       "FROM articles WHERE is_archived = 0 "
                       "ORDER BY created_at DESC LIMIT ?")
                params = [top_k]
            rows = con.execute(sql, params).fetchall()
            con.close()
            return [
                SimpleNamespace(
                    id=r["id"], title=r["title"], url=r["url"],
                    source=r["source"], content=r["content"],
                    summary=r["summary"], published_at=r["published_at"],
                    similarity_score=0.5, relevance_score=0.5,
                )
                for r in rows
            ]
        except Exception as exc:
            logger.error("RAG fallback keyword search failed: %s", exc)
            return []

    def _build_search_request(
        self,
        query: str,
        top_k: int,
        min_score: float,
        use_reranking: bool = True,
    ):
        from ..models.search import SearchRequest

        return SearchRequest(
            query=query,
            limit=top_k,
            min_score=min_score,
            use_reranking=use_reranking,
            include_summary=True,
            sources=None,
            categories=None,
            date_from=None,
            date_to=None,
        )

    def _build_context(self, articles: List[Any]) -> str:
        ctx = "Relevant articles:\n\n"
        for i, art in enumerate(articles, 1):
            ctx += f"Article {i}:\n"
            ctx += f"Title: {art.title}\n"
            ctx += f"Source: {art.source}\n"
            content = art.summary or art.content
            if content:
                ctx += f"Content: {content[:500]}...\n"
            ctx += f"Relevance Score: {art.similarity_score:.2f}\n\n"
        return ctx

    async def _generate_answer(
        self, question: str, context: str
    ) -> Dict[str, Any]:
        prompt = (
            "You are a knowledgeable AI assistant specialising in technology news.\n"
            "Based on the following articles, answer the user's question accurately and concisely.\n\n"
            f"{context}\n\nQuestion: {question}\n\n"
            "Instructions:\n"
            "- Provide a clear, informative answer based on the articles above\n"
            "- **Cite every factual claim with an inline citation marker `[N]`** where N matches the article number above. "
            "For example, write `OpenAI announced ...[1]` or `The chip is reported to ship in Q4 [2][3]`. Cite at least one source for every paragraph\n"
            "- Include specific technical details when relevant\n"
            "- If the articles don't fully answer the question, acknowledge the gap\n"
            "- Keep the answer to 2-4 paragraphs\n\n"
            "Answer (with `[N]` citations):"
        )
        try:
            result = await self.summarization_service.summarize_content(
                SummarizationRequest(content=prompt, max_length=400)
            )
            return {
                "text": result.summary,
                "model": result.model_used,
                "success": True,
            }
        except Exception as exc:
            logger.error("LLM generation failed: %s", exc)
            return {
                "text": "I apologize, but I couldn't generate a response at this time.",
                "error": str(exc),
                "success": False,
            }

    def _format_sources(self, articles: List[Any]) -> List[Dict[str, Any]]:
        return [
            {
                "id": getattr(a, "id", None),
                "title": getattr(a, "title", None),
                "url": getattr(a, "url", None),
                "source": getattr(a, "source", None),
                "published_at": getattr(a, "published_at", None),
                "similarity_score": getattr(a, "similarity_score", None),
                "relevance_score": getattr(a, "relevance_score", None),
            }
            for a in articles
        ]

    def _calculate_confidence(self, articles: List[Any]) -> float:
        if not articles:
            return 0.0
        top = [a.similarity_score for a in articles[:3]]
        conf = sum(top) / len(top)
        if len(articles) < 3:
            conf *= 0.8
        return round(conf, 2)


# ----------------------- Singleton accessor ----------------------- #

_rag_pipeline: Optional[RAGPipeline] = None


async def get_rag_pipeline() -> RAGPipeline:
    """Return a lazily-initialised RAGPipeline singleton."""
    global _rag_pipeline
    if _rag_pipeline is None:
        _rag_pipeline = RAGPipeline()
        await _rag_pipeline.initialize()
    return _rag_pipeline
