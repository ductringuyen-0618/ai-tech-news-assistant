"""
Embedding Service
===============

Business logic for embedding generation, storage, and similarity search.
Handles the core embedding operations with proper error handling and performance optimization.
"""

import asyncio
import logging
from typing import List, Dict, Any
from datetime import datetime, timezone

from ..core.config import get_settings
from ..core.exceptions import EmbeddingError, ValidationError
from ..models.embedding import (
    EmbeddingRequest,
    EmbeddingResponse
)

settings = get_settings()

# Import at module level for testing purposes.
# Each dep is imported independently so a missing torch/sentence_transformers
# does not disable the numpy-only similarity-compute paths.
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    np = None
    NUMPY_AVAILABLE = False

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    torch = None
    TORCH_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SentenceTransformer = None
    SENTENCE_TRANSFORMERS_AVAILABLE = False

TRANSFORMERS_AVAILABLE = SENTENCE_TRANSFORMERS_AVAILABLE and TORCH_AVAILABLE

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Service for handling embedding generation and similarity operations.
    
    This service encapsulates all embedding-related business logic,
    providing a clean interface for embedding operations while handling
    performance optimization, error recovery, and resource management.
    """
    
    def __init__(self):
        """Initialize the embedding service."""
        self.model_name = settings.embedding_model
        self.embedding_dim = None
        self.model = None
        self.device = None
        self._initialized = False
        
    async def initialize(self) -> None:
        """
        Initialize the embedding model and resources.
        
        Raises:
            EmbeddingError: If model initialization fails
        """
        if self._initialized:
            return
            
        try:
            logger.info(f"Initializing embedding service with model: {self.model_name}")
            
            # Check if transformers are available
            if not TRANSFORMERS_AVAILABLE:
                raise EmbeddingError("sentence-transformers package is not installed")
            
            # Detect device
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"Using device: {self.device}")
            
            # Load model
            self.model = SentenceTransformer(self.model_name)
            self.model.to(self.device)
            
            # Get embedding dimension
            self.embedding_dim = self.model.get_sentence_embedding_dimension()
            
            self._initialized = True
            logger.info(f"Embedding service initialized. Dimension: {self.embedding_dim}")
            
        except Exception as e:
            logger.error(f"Failed to initialize embedding service: {e}")
            raise EmbeddingError(f"Model initialization failed: {str(e)}")
    
    async def generate_embeddings(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """
        Generate embeddings for the provided texts.
        
        Args:
            request: Embedding generation request
            
        Returns:
            EmbeddingResponse with generated embeddings
            
        Raises:
            EmbeddingError: If embedding generation fails
            ValidationError: If request validation fails
        """
        if not self._initialized:
            await self.initialize()
            
        try:
            start_time = datetime.now(timezone.utc)
            
            # Validate request
            if not request.texts:
                raise ValidationError("No texts provided for embedding")
                
            if len(request.texts) > 100:
                raise ValidationError("Too many texts provided (max 100)")
            
            # Generate embeddings in batches
            embeddings = await self._generate_embeddings_batch(
                texts=request.texts,
                batch_size=request.batch_size,
                normalize=request.normalize
            )
            
            # Calculate processing time
            end_time = datetime.now(timezone.utc)
            processing_time = (end_time - start_time).total_seconds()
            
            logger.info(f"Generated {len(embeddings)} embeddings in {processing_time:.2f}s")
            
            return EmbeddingResponse(
                embeddings=embeddings,
                model_name=self.model_name,
                embedding_dim=self.embedding_dim,
                processing_time=processing_time
            )
            
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise EmbeddingError(f"Failed to generate embeddings: {str(e)}")
    
    async def _generate_embeddings_batch(
        self, 
        texts: List[str], 
        batch_size: int = 32,
        normalize: bool = True
    ) -> List[List[float]]:
        """
        Generate embeddings in batches for memory efficiency.
        
        Args:
            texts: List of texts to embed
            batch_size: Size of each batch
            normalize: Whether to normalize embeddings
            
        Returns:
            List of embedding vectors
        """
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            
            # Run in thread pool to avoid blocking
            embeddings = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.model.encode(
                    batch_texts,
                    normalize_embeddings=normalize,
                    convert_to_numpy=True
                )
            )
            
            # Convert numpy arrays to lists
            batch_embeddings = embeddings.tolist()
            all_embeddings.extend(batch_embeddings)
            
            logger.debug(f"Processed batch {i//batch_size + 1}, embeddings: {len(batch_embeddings)}")
        
        return all_embeddings
    
    async def compute_similarity(
        self, 
        embedding1: List[float], 
        embedding2: List[float]
    ) -> float:
        """
        Compute cosine similarity between two embeddings.
        
        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector
            
        Returns:
            Cosine similarity score (0.0 to 1.0)
            
        Raises:
            ValidationError: If embeddings have different dimensions
        """
        if len(embedding1) != len(embedding2):
            raise ValidationError("Embeddings must have the same dimension")
        
        try:
            if np is None:
                raise EmbeddingError("numpy package is not available")
            
            # Convert to numpy arrays
            emb1 = np.array(embedding1)
            emb2 = np.array(embedding2)
            
            # Compute cosine similarity
            dot_product = np.dot(emb1, emb2)
            norm1 = np.linalg.norm(emb1)
            norm2 = np.linalg.norm(emb2)
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
            
            similarity = dot_product / (norm1 * norm2)
            
            # Ensure result is in [0, 1] range
            return max(0.0, min(1.0, similarity))
            
        except Exception as e:
            logger.error(f"Similarity computation failed: {e}")
            raise EmbeddingError(f"Failed to compute similarity: {str(e)}")
    
    async def batch_similarity(
        self, 
        query_embedding: List[float], 
        candidate_embeddings: List[List[float]]
    ) -> List[float]:
        """
        Compute similarity between a query and multiple candidates efficiently.
        
        Args:
            query_embedding: Query embedding vector
            candidate_embeddings: List of candidate embedding vectors
            
        Returns:
            List of similarity scores
        """
        try:
            if np is None:
                raise EmbeddingError("numpy package is not available")
            
            query = np.array(query_embedding)
            candidates = np.array(candidate_embeddings)
            
            # Vectorized cosine similarity computation
            dot_products = np.dot(candidates, query)
            query_norm = np.linalg.norm(query)
            candidate_norms = np.linalg.norm(candidates, axis=1)
            
            # Avoid division by zero
            similarities = np.where(
                (candidate_norms != 0) & (query_norm != 0),
                dot_products / (candidate_norms * query_norm),
                0.0
            )
            
            # Ensure results are in [0, 1] range
            similarities = np.clip(similarities, 0.0, 1.0)
            
            return similarities.tolist()
            
        except Exception as e:
            logger.error(f"Batch similarity computation failed: {e}")
            raise EmbeddingError(f"Failed to compute batch similarity: {str(e)}")
    
    async def get_model_info(self) -> Dict[str, Any]:
        """
        Get information about the current embedding model.
        
        Returns:
            Dictionary with model information
        """
        if not self._initialized:
            await self.initialize()
        
        return {
            "model_name": self.model_name,
            "embedding_dimension": self.embedding_dim,
            "device": self.device,
            "max_sequence_length": getattr(self.model, 'max_seq_length', 'unknown'),
            "initialized": self._initialized
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform a health check on the embedding service.
        
        Returns:
            Dictionary with health status information
        """
        try:
            if not self._initialized:
                await self.initialize()
            
            # Test embedding generation with a simple text
            test_request = EmbeddingRequest(
                texts=["health check test"],
                batch_size=1
            )
            
            response = await self.generate_embeddings(test_request)
            
            return {
                "status": "healthy",
                "model_loaded": True,
                "test_embedding_dim": len(response.embeddings[0]),
                "processing_time": response.processing_time
            }
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "model_loaded": self._initialized
            }
