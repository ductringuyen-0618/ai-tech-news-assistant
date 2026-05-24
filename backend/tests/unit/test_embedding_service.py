"""
Unit Tests for Embedding Service
===============================

Tests for embedding service business logic operations.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.services.embedding_service import EmbeddingService
from src.models.embedding import EmbeddingRequest, EmbeddingResponse
from src.core.exceptions import EmbeddingError, ValidationError


class TestEmbeddingService:
    """Test cases for EmbeddingService."""
    
    @pytest.fixture
    def service(self):
        """Create service instance."""
        return EmbeddingService()
    
    @pytest.mark.requires_torch
    @pytest.mark.asyncio
    async def test_initialize_service(self, service):
        """Test service initialization."""
        with patch('src.services.embedding_service.SentenceTransformer') as mock_transformer:
            mock_model = MagicMock()
            mock_model.get_sentence_embedding_dimension.return_value = 384
            mock_transformer.return_value = mock_model

            with patch('torch.cuda.is_available', return_value=False):
                await service.initialize()

            assert service._initialized is True
            assert service.embedding_dim == 384
            assert service.device == "cpu"

    @pytest.mark.requires_torch
    @pytest.mark.asyncio
    async def test_initialize_with_cuda(self, service):
        """Test service initialization with CUDA."""
        with patch('src.services.embedding_service.SentenceTransformer') as mock_transformer:
            mock_model = MagicMock()
            mock_model.get_sentence_embedding_dimension.return_value = 384
            mock_transformer.return_value = mock_model

            with patch('torch.cuda.is_available', return_value=True):
                await service.initialize()

            assert service.device == "cuda"
    
    @pytest.mark.asyncio
    async def test_initialization_failure(self, service):
        """Test service initialization failure."""
        with patch('src.services.embedding_service.SentenceTransformer', side_effect=Exception("Model load failed")):
            with pytest.raises(EmbeddingError, match="Model initialization failed"):
                await service.initialize()
    
    @pytest.mark.asyncio
    async def test_generate_embeddings_success(self, service):
        """Test successful embedding generation."""
        # Mock initialization
        service._initialized = True
        service.model_name = "test-model"
        service.embedding_dim = 384
        
        # Mock the batch generation method
        service._generate_embeddings_batch = AsyncMock(
            return_value=[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        )
        
        request = EmbeddingRequest(
            texts=["Hello world", "Test text"],
            batch_size=2,
            normalize=True
        )
        
        with patch('src.services.embedding_service.datetime') as mock_datetime:
            # Configure the mock to return proper datetime objects when .now() is called
            start_dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
            end_dt = datetime(2024, 1, 1, 12, 0, 1, tzinfo=timezone.utc)
            mock_datetime.now.side_effect = [start_dt, end_dt]
            mock_datetime.timezone = timezone
            
            result = await service.generate_embeddings(request)
        
        assert isinstance(result, EmbeddingResponse)
        assert len(result.embeddings) == 2
        assert result.model_name == "test-model"
        assert result.embedding_dim == 384
        assert result.processing_time == 1.0
    
    @pytest.mark.asyncio
    async def test_generate_embeddings_validation_error(self, service):
        """Test embedding generation with validation errors."""
        service._initialized = True
        
        # Test that Pydantic validation catches empty texts (this will raise pydantic ValidationError)
        from pydantic import ValidationError as PydanticValidationError
        with pytest.raises(PydanticValidationError):
            EmbeddingRequest(texts=[], batch_size=1)
        
        # Test that Pydantic validation catches too many texts  
        with pytest.raises(PydanticValidationError):
            EmbeddingRequest(texts=["text"] * 101, batch_size=1)
    
    @pytest.mark.asyncio
    async def test_generate_embeddings_auto_initialize(self, service):
        """Test that generate_embeddings initializes service if needed."""
        service.initialize = AsyncMock()
        service._generate_embeddings_batch = AsyncMock(return_value=[[0.1, 0.2]])
        service.model_name = "test-model"
        service.embedding_dim = 2
        
        request = EmbeddingRequest(texts=["test"], batch_size=1)
        
        await service.generate_embeddings(request)
        
        service.initialize.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_compute_similarity_success(self, service):
        """Test successful similarity computation."""
        embedding1 = [1.0, 0.0, 0.0]
        embedding2 = [0.0, 1.0, 0.0]
        
        similarity = await service.compute_similarity(embedding1, embedding2)
        
        assert similarity == 0.0  # Orthogonal vectors
    
    @pytest.mark.asyncio
    async def test_compute_similarity_identical_vectors(self, service):
        """Test similarity computation with identical vectors."""
        embedding = [1.0, 1.0, 1.0]
        
        similarity = await service.compute_similarity(embedding, embedding)
        
        assert similarity == 1.0  # Identical vectors
    
    @pytest.mark.asyncio
    async def test_compute_similarity_dimension_mismatch(self, service):
        """Test similarity computation with different dimensions."""
        embedding1 = [1.0, 0.0]
        embedding2 = [0.0, 1.0, 0.0]
        
        with pytest.raises(ValidationError, match="same dimension"):
            await service.compute_similarity(embedding1, embedding2)
    
    @pytest.mark.asyncio
    async def test_batch_similarity_success(self, service):
        """Test batch similarity computation."""
        query_embedding = [1.0, 0.0]
        candidate_embeddings = [
            [1.0, 0.0],  # Same as query
            [0.0, 1.0],  # Orthogonal
            [-1.0, 0.0]  # Opposite
        ]
        
        similarities = await service.batch_similarity(query_embedding, candidate_embeddings)
        
        assert len(similarities) == 3
        assert similarities[0] == 1.0   # Same vector
        assert similarities[1] == 0.0   # Orthogonal
        assert similarities[2] == 0.0   # Opposite (clipped to 0)
    
    @pytest.mark.asyncio
    async def test_get_model_info_uninitialized(self, service):
        """Test getting model info initializes service."""
        service.initialize = AsyncMock()
        service._initialized = True
        service.model_name = "test-model"
        service.embedding_dim = 384
        service.device = "cpu"
        service.model = MagicMock()
        service.model.max_seq_length = 512
        
        info = await service.get_model_info()
        
        assert info["model_name"] == "test-model"
        assert info["embedding_dimension"] == 384
        assert info["device"] == "cpu"
        assert info["max_sequence_length"] == 512
        assert info["initialized"] is True
    
    @pytest.mark.asyncio
    async def test_health_check_healthy(self, service):
        """Test health check when service is healthy."""
        service.initialize = AsyncMock()
        service.generate_embeddings = AsyncMock()
        
        # Mock the embedding response
        mock_response = EmbeddingResponse(
            embeddings=[[0.1, 0.2, 0.3]],
            model_name="test-model",
            embedding_dim=3,
            processing_time=0.1
        )
        service.generate_embeddings.return_value = mock_response
        
        result = await service.health_check()
        
        assert result["status"] == "healthy"
        assert result["model_loaded"] is True
        assert result["test_embedding_dim"] == 3
        assert "processing_time" in result
    
    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self, service):
        """Test health check when service is unhealthy."""
        service.initialize = AsyncMock(side_effect=Exception("Initialization failed"))
        
        result = await service.health_check()
        
        assert result["status"] == "unhealthy"
        assert "error" in result
        assert result["model_loaded"] is False
    
    @pytest.mark.asyncio
    async def test_generate_embeddings_batch_internal(self, service):
        """Test internal batch generation method."""
        # Setup mock model
        mock_model = MagicMock()
        mock_embeddings = MagicMock()
        mock_embeddings.tolist.return_value = [[0.1, 0.2], [0.3, 0.4]]
        mock_model.encode.return_value = mock_embeddings
        service.model = mock_model
        
        # Mock asyncio.get_event_loop().run_in_executor to actually call the lambda
        with patch('asyncio.get_event_loop') as mock_loop:
            def mock_executor(executor, func):
                # Actually call the lambda function to trigger model.encode
                return func()
            
            mock_loop.return_value.run_in_executor = AsyncMock(side_effect=mock_executor)
            
            result = await service._generate_embeddings_batch(
                texts=["text1", "text2"],
                batch_size=2,
                normalize=True
            )
        
        assert result == [[0.1, 0.2], [0.3, 0.4]]
        mock_model.encode.assert_called_once()
