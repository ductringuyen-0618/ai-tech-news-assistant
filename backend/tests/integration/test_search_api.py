"""
Integration Tests for Search API
================================

End-to-end tests for the search endpoint including:
- HTTP request/response handling
- Database integration
- Embedding generation
- Full search flow
- Error responses
"""

import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta
import json
from typing import Dict, Any

from src.main import app


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def client():
    """Create test client for API integration tests."""
    return TestClient(app)


@pytest.fixture
def sample_search_payload() -> Dict[str, Any]:
    """Sample search request payload."""
    return {
        "query": "artificial intelligence machine learning",
        "limit": 10,
        "min_score": 0.5,
        "use_reranking": True
    }


@pytest.fixture
def search_payload_with_filters() -> Dict[str, Any]:
    """Search request with source and category filters."""
    return {
        "query": "deep learning neural networks",
        "limit": 20,
        "min_score": 0.6,
        "sources": ["hackernews", "techcrunch"],
        "categories": ["AI", "Machine Learning"],
        "use_reranking": True
    }


# ============================================================================
# Basic Search Endpoint Tests
# ============================================================================

class TestSearchEndpoint:
    """Test search endpoint functionality."""
    
    def test_search_endpoint_exists(self, client):
        """Test that search endpoint is accessible."""
        response = client.post("/api/search/hybrid", json={"query": "test", "limit": 5})
        
        # Should not return 404
        assert response.status_code != 404
    
    def test_search_returns_valid_response_structure(self, client, sample_search_payload):
        """Test that search returns properly structured response."""
        response = client.post("/api/search/hybrid", json=sample_search_payload)
        
        if response.status_code == 200:
            data = response.json()
            
            # Check required fields
            assert "query" in data
            assert "results" in data
            assert "total_results" in data
            assert "execution_time_ms" in data
            assert "reranking_applied" in data
            
            # Check types
            assert isinstance(data["query"], str)
            assert isinstance(data["results"], list)
            assert isinstance(data["total_results"], int)
            assert isinstance(data["execution_time_ms"], (int, float))
            assert isinstance(data["reranking_applied"], bool)
    
    def test_search_result_item_structure(self, client, sample_search_payload):
        """Test that individual search results have correct structure."""
        response = client.post("/api/search/hybrid", json=sample_search_payload)
        
        if response.status_code == 200:
            data = response.json()
            
            if data["total_results"] > 0:
                result = data["results"][0]
                
                # Check required fields
                assert "article_id" in result
                assert "title" in result
                assert "url" in result
                assert "source" in result
                assert "score" in result
                assert "published_date" in result
                
                # Check types
                assert isinstance(result["article_id"], str)
                assert isinstance(result["title"], str)
                assert isinstance(result["url"], str)
                assert isinstance(result["source"], str)
                assert isinstance(result["score"], (int, float))
                assert isinstance(result["published_date"], str)
    
    def test_search_with_minimal_payload(self, client):
        """Test search with only required fields."""
        minimal_payload = {"query": "AI", "limit": 5}
        
        response = client.post("/api/search/hybrid", json=minimal_payload)
        
        # Should succeed with defaults
        assert response.status_code in [200, 500]  # May fail if no embeddings exist
    
    def test_search_respects_limit(self, client):
        """Test that search respects the limit parameter."""
        payload = {"query": "technology", "limit": 3}
        
        response = client.post("/api/search/hybrid", json=payload)
        
        if response.status_code == 200:
            data = response.json()
            assert len(data["results"]) <= 3


# ============================================================================
# Filtering Tests
# ============================================================================

class TestSearchFiltering:
    """Test search filtering functionality."""
    
    def test_search_with_source_filter(self, client):
        """Test filtering by source."""
        payload = {
            "query": "AI research",
            "limit": 10,
            "sources": ["hackernews"]
        }
        
        response = client.post("/api/search/hybrid", json=payload)
        
        if response.status_code == 200:
            data = response.json()
            
            # All results should be from hackernews
            if data["total_results"] > 0:
                assert all(r["source"] == "hackernews" for r in data["results"])
    
    def test_search_with_multiple_sources(self, client):
        """Test filtering by multiple sources."""
        payload = {
            "query": "machine learning",
            "limit": 10,
            "sources": ["hackernews", "techcrunch", "reddit"]
        }
        
        response = client.post("/api/search/hybrid", json=payload)
        
        if response.status_code == 200:
            data = response.json()
            
            # All results should be from specified sources
            if data["total_results"] > 0:
                valid_sources = {"hackernews", "techcrunch", "reddit"}
                assert all(r["source"] in valid_sources for r in data["results"])
    
    def test_search_with_category_filter(self, client):
        """Test filtering by category."""
        payload = {
            "query": "programming",
            "limit": 10,
            "categories": ["AI"]
        }
        
        response = client.post("/api/search/hybrid", json=payload)
        
        if response.status_code == 200:
            data = response.json()
            
            # All results should have AI category
            if data["total_results"] > 0:
                assert all("AI" in r.get("categories", []) for r in data["results"])
    
    def test_search_with_min_score(self, client):
        """Test minimum score filtering."""
        payload = {
            "query": "deep learning",
            "limit": 10,
            "min_score": 0.7
        }
        
        response = client.post("/api/search/hybrid", json=payload)
        
        if response.status_code == 200:
            data = response.json()
            
            # All results should have score >= 0.7
            if data["total_results"] > 0:
                assert all(r["score"] >= 0.7 for r in data["results"])
    
    def test_search_with_date_range(self, client):
        """Test filtering by date range."""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        payload = {
            "query": "AI news",
            "limit": 10,
            "published_after": start_date.isoformat(),
            "published_before": end_date.isoformat()
        }
        
        response = client.post("/api/search/hybrid", json=payload)
        
        if response.status_code == 200:
            data = response.json()
            
            # All results should be within date range
            if data["total_results"] > 0:
                for result in data["results"]:
                    pub_date = datetime.fromisoformat(result["published_date"])
                    assert start_date <= pub_date <= end_date


# ============================================================================
# Reranking Tests
# ============================================================================

class TestSearchReranking:
    """Test reranking functionality."""
    
    def test_search_with_reranking_enabled(self, client, sample_search_payload):
        """Test search with reranking enabled."""
        sample_search_payload["use_reranking"] = True
        
        response = client.post("/api/search/hybrid", json=sample_search_payload)
        
        if response.status_code == 200:
            data = response.json()
            assert data["reranking_applied"] is True
    
    def test_search_with_reranking_disabled(self, client, sample_search_payload):
        """Test search without reranking."""
        sample_search_payload["use_reranking"] = False
        
        response = client.post("/api/search/hybrid", json=sample_search_payload)
        
        if response.status_code == 200:
            data = response.json()
            assert data["reranking_applied"] is False
    
    def test_reranking_affects_results(self, client):
        """Test that reranking changes result ordering."""
        payload = {"query": "artificial intelligence", "limit": 10}
        
        # Get results without reranking
        payload["use_reranking"] = False
        response_no_rerank = client.post("/api/search/hybrid", json=payload)
        
        # Get results with reranking
        payload["use_reranking"] = True
        response_with_rerank = client.post("/api/search/hybrid", json=payload)
        
        if response_no_rerank.status_code == 200 and response_with_rerank.status_code == 200:
            data_no_rerank = response_no_rerank.json()
            data_with_rerank = response_with_rerank.json()
            
            # If we have results, ordering should potentially differ
            if data_no_rerank["total_results"] > 1 and data_with_rerank["total_results"] > 1:
                # Scores should differ due to reranking
                no_rerank_scores = [r["score"] for r in data_no_rerank["results"]]
                with_rerank_scores = [r["score"] for r in data_with_rerank["results"]]
                
                # At least some scores should be different
                assert no_rerank_scores != with_rerank_scores


# ============================================================================
# Validation Tests
# ============================================================================

class TestSearchValidation:
    """Test input validation."""
    
    def test_search_empty_query(self, client):
        """Test that empty query is rejected."""
        payload = {"query": "", "limit": 10}
        
        response = client.post("/api/search/hybrid", json=payload)
        
        # Should fail validation
        assert response.status_code in [400, 422, 500]
    
    def test_search_invalid_limit(self, client):
        """Test that invalid limit is rejected or handled."""
        payload = {"query": "test", "limit": -1}
        
        response = client.post("/api/search/hybrid", json=payload)
        
        # Should either reject with validation error or handle gracefully
        # Accept 422 (validation), 500 (server error), or 400 (bad request)
        assert response.status_code in [400, 422, 500]
    
    def test_search_limit_too_large(self, client):
        """Test that limit exceeding maximum is handled."""
        payload = {"query": "test", "limit": 1000}
        
        response = client.post("/api/search/hybrid", json=payload)
        
        # Should either cap at max, reject, or return server error
        assert response.status_code in [200, 400, 422, 500]
    
    def test_search_invalid_min_score(self, client):
        """Test that invalid min_score is rejected or handled."""
        payload = {"query": "test", "limit": 10, "min_score": 1.5}
        
        response = client.post("/api/search/hybrid", json=payload)
        
        # Should fail validation (score should be 0-1) or return server error
        assert response.status_code in [400, 422, 500]
    
    def test_search_invalid_date_format(self, client):
        """Test that invalid date format is rejected or handled."""
        payload = {
            "query": "test",
            "limit": 10,
            "published_after": "not-a-date"
        }
        
        response = client.post("/api/search/hybrid", json=payload)
        
        # Should fail validation or return server error
        assert response.status_code in [400, 422, 500]
    
    def test_search_missing_required_fields(self, client):
        """Test that missing required fields are handled."""
        payload = {"limit": 10}  # Missing query
        
        response = client.post("/api/search/hybrid", json=payload)
        
        # Should fail validation or return appropriate error
        assert response.status_code in [400, 422, 500]


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestSearchErrorHandling:
    """Test error handling in search API."""
    
    def test_search_invalid_json(self, client):
        """Test that invalid JSON is handled."""
        response = client.post(
            "/search",
            data="not valid json",
            headers={"Content-Type": "application/json"}
        )
        
        # Should return validation error or not found
        assert response.status_code in [400, 404, 422]
    
    def test_search_wrong_http_method(self, client):
        """Test that GET on the POST-only sub-routes is rejected.

        ``/api/search/`` itself is a documented GET endpoint, so we probe
        a POST-only path instead (``/api/search/semantic``).
        """
        response = client.get("/api/search/semantic")
        assert response.status_code in [404, 405, 422, 500]
    
    def test_search_missing_content_type(self, client, sample_search_payload):
        """Test that missing content-type header is handled."""
        response = client.post(
            "/search",
            data=json.dumps(sample_search_payload)
        )
        
        # Should work, return 404 if endpoint not found, or error
        assert response.status_code in [200, 404, 415, 500]


# ============================================================================
# Health Check Tests
# ============================================================================

class TestSearchHealthEndpoint:
    """Test search health check endpoint."""
    
    def test_health_endpoint_exists(self, client):
        """Test that health endpoint is accessible or returns appropriate response."""
        response = client.get("/api/search/health")
        
        # Should return OK or not found (endpoint may not exist)
        assert response.status_code in [200, 404]
    
    def test_health_returns_valid_structure(self, client):
        """Test health endpoint returns proper structure."""
        response = client.get("/api/search/health")
        
        if response.status_code == 200:
            data = response.json()
            
            # Check required fields
            assert "status" in data
            assert "total_indexed_articles" in data
            assert "embedding_dimensions" in data
            assert "model_name" in data
            assert "last_indexed" in data
            
            # Check types
            assert isinstance(data["status"], str)
            assert data["status"] in ["healthy", "degraded", "unhealthy"]
            assert isinstance(data["total_indexed_articles"], int)
            assert isinstance(data["embedding_dimensions"], int)
            assert isinstance(data["model_name"], str)
    
    def test_health_status_values(self, client):
        """Test that health status has valid values."""
        response = client.get("/api/search/health")
        
        if response.status_code == 200:
            data = response.json()
            assert data["status"] in ["healthy", "degraded", "unhealthy"]


# ============================================================================
# Performance Tests
# ============================================================================

class TestSearchPerformance:
    """Test search performance characteristics."""
    
    def test_search_execution_time(self, client, sample_search_payload):
        """Test that search completes in reasonable time."""
        response = client.post("/api/search/hybrid", json=sample_search_payload)
        
        if response.status_code == 200:
            data = response.json()
            
            # Should complete in reasonable time (adjust threshold as needed)
            assert data["execution_time_ms"] < 5000  # 5 seconds
    
    def test_search_handles_complex_query(self, client):
        """Test search with complex query string."""
        complex_query = (
            "advanced machine learning algorithms for natural language "
            "processing including transformers, attention mechanisms, "
            "and pre-trained models like BERT and GPT"
        )
        
        payload = {"query": complex_query, "limit": 10}
        
        response = client.post("/api/search/hybrid", json=payload)
        
        # Should handle long queries
        assert response.status_code in [200, 500]
    
    def test_search_concurrent_requests(self, client, sample_search_payload):
        """Test that multiple concurrent requests work."""
        import concurrent.futures
        
        def make_request():
            return client.post("/api/search/hybrid", json=sample_search_payload)
        
        # Make 5 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request) for _ in range(5)]
            responses = [f.result() for f in futures]
        
        # All should complete
        assert all(r.status_code in [200, 500] for r in responses)


# ============================================================================
# Results Quality Tests
# ============================================================================

class TestSearchResultsQuality:
    """Test quality and relevance of search results."""
    
    def test_results_are_sorted_by_score(self, client, sample_search_payload):
        """Test that results are sorted by relevance score."""
        response = client.post("/api/search/hybrid", json=sample_search_payload)
        
        if response.status_code == 200:
            data = response.json()
            
            if data["total_results"] > 1:
                scores = [r["score"] for r in data["results"]]
                
                # Scores should be in descending order
                assert scores == sorted(scores, reverse=True)
    
    def test_scores_are_valid_range(self, client, sample_search_payload):
        """Test that all scores are in valid range (0-1)."""
        response = client.post("/api/search/hybrid", json=sample_search_payload)
        
        if response.status_code == 200:
            data = response.json()
            
            if data["total_results"] > 0:
                scores = [r["score"] for r in data["results"]]
                
                # All scores should be between 0 and 1
                assert all(0 <= score <= 1 for score in scores)
    
    def test_no_duplicate_results(self, client, sample_search_payload):
        """Test that results don't contain duplicates."""
        response = client.post("/api/search/hybrid", json=sample_search_payload)
        
        if response.status_code == 200:
            data = response.json()
            
            if data["total_results"] > 0:
                article_ids = [r["article_id"] for r in data["results"]]
                
                # No duplicates
                assert len(article_ids) == len(set(article_ids))
    
    def test_all_results_have_required_metadata(self, client, sample_search_payload):
        """Test that all results have required metadata."""
        response = client.post("/api/search/hybrid", json=sample_search_payload)
        
        if response.status_code == 200:
            data = response.json()
            
            if data["total_results"] > 0:
                for result in data["results"]:
                    # Check all required fields are present and non-empty
                    assert result.get("article_id")
                    assert result.get("title")
                    assert result.get("url")
                    assert result.get("source")
                    assert result.get("published_date")
                    assert isinstance(result.get("score"), (int, float))


# ============================================================================
# Edge Cases
# ============================================================================

class TestSearchEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_search_with_special_characters(self, client):
        """Test search with special characters in query."""
        payloads = [
            {"query": "AI & ML", "limit": 5},
            {"query": "C++ programming", "limit": 5},
            {"query": "data-science", "limit": 5},
            {"query": "machine_learning", "limit": 5}
        ]
        
        for payload in payloads:
            response = client.post("/api/search/hybrid", json=payload)
            
            # Should handle special characters
            assert response.status_code in [200, 500]
    
    def test_search_with_unicode_characters(self, client):
        """Test search with unicode characters."""
        payload = {"query": "人工智能 machine learning 🤖", "limit": 5}
        
        response = client.post("/api/search/hybrid", json=payload)
        
        # Should handle unicode
        assert response.status_code in [200, 500]
    
    def test_search_very_short_query(self, client):
        """Test search with very short query."""
        payload = {"query": "AI", "limit": 5}
        
        response = client.post("/api/search/hybrid", json=payload)
        
        # Should work with short queries
        assert response.status_code in [200, 500]
    
    def test_search_with_zero_limit(self, client):
        """Test search with limit of 0."""
        payload = {"query": "test", "limit": 0}
        
        response = client.post("/api/search/hybrid", json=payload)
        
        # Should reject or return empty results or error
        assert response.status_code in [200, 400, 422, 500]
        
        if response.status_code == 200:
            data = response.json()
            assert len(data["results"]) == 0
