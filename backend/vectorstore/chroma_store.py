"""
ChromaDB Vector Store Implementation
====================================

Production-ready vector database for storing and querying article embeddings.

Features:
- Persistent storage with ChromaDB
- Automatic embedding generation
- Similarity search with metadata filtering
- Batch operations for efficiency
- Error handling and logging
"""

from typing import List, Dict, Any, Optional
from pathlib import Path
import uuid

try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False

from vectorstore.embeddings import EmbeddingGenerator
import logging
# from utils.config import get_settings  # stub

logger = logging.getLogger(__name__)
settings = None  # legacy reference


class ChromaVectorStore:
    """
    Production ChromaDB vector store for article embeddings.
    
    This implementation uses:
    - Local persistent storage (no cloud costs)
    - Sentence Transformers for embeddings
    - Metadata filtering for advanced queries
    - Batch operations for efficiency
    """
    
    def __init__(self, 
                 collection_name: str = "news_articles",
                 persist_directory: Optional[str] = None):
        """
        Initialize ChromaDB vector store.
        
        Args:
            collection_name: Name of the collection
            persist_directory: Directory for persistent storage
        """
        if not CHROMADB_AVAILABLE:
            raise ImportError(
                "chromadb is required. Install with: pip install chromadb"
            )
        
        self.collection_name = collection_name
        self.persist_directory = persist_directory or settings.chroma_persist_directory
        
        # Ensure directory exists
        Path(self.persist_directory).mkdir(parents=True, exist_ok=True)
        
        # Initialize ChromaDB client with persistent storage
        self.client = chromadb.PersistentClient(
            path=self.persist_directory,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=False
            )
        )
        
        # Initialize embedding generator
        self.embedding_generator = EmbeddingGenerator()
        self.collection = None
        
        logger.info(
            f"ChromaDB initialized at {self.persist_directory} "
            f"with collection '{collection_name}'"
        )
    
    async def initialize(self) -> bool:
        """
        Initialize the vector store and embedding generator.
        
        Returns:
            Success status
        """
        try:
            # Initialize embedding generator
            await self.embedding_generator.initialize()
            
            # Get or create collection
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"description": "Tech news articles with embeddings"}
            )
            
            count = self.collection.count()
            logger.info(
                f"ChromaDB collection '{self.collection_name}' ready "
                f"with {count} documents"
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}")
            return False
    
    async def add_articles(
        self,
        articles: List[Dict[str, Any]],
        batch_size: int = 100
    ) -> Dict[str, Any]:
        """
        Add articles to the vector store with embeddings.
        
        Args:
            articles: List of article dictionaries with 'id', 'content', 'title', etc.
            batch_size: Number of articles to process at once
            
        Returns:
            Dict with success status and statistics
        """
        if not self.collection:
            await self.initialize()
        
        try:
            total_added = 0
            total_skipped = 0
            
            # Process in batches
            for i in range(0, len(articles), batch_size):
                batch = articles[i:i + batch_size]
                
                # Prepare data
                ids = []
                texts = []
                metadatas = []
                
                for article in batch:
                    # Use article ID or generate one
                    article_id = article.get('id', str(uuid.uuid4()))
                    
                    # Combine title and content for better embeddings
                    text = f"{article.get('title', '')} {article.get('content', '')}"
                    
                    # Prepare metadata (ChromaDB requires all values to be strings, ints, floats, or bools)
                    metadata = {
                        'article_id': str(article_id),
                        'title': article.get('title', '')[:500],  # Limit length
                        'source': article.get('source', 'unknown'),
                        'url': article.get('url', ''),
                        'published_at': str(article.get('published_at', '')),
                    }
                    
                    # Add categories if available
                    if 'categories' in article and article['categories']:
                        metadata['category'] = ','.join(article['categories'][:3])
                    
                    ids.append(article_id)
                    texts.append(text)
                    metadatas.append(metadata)
                
                # Generate embeddings
                embeddings = await self.embedding_generator.generate_embeddings(
                    texts,
                    batch_size=32
                )
                
                # Add to ChromaDB (will skip duplicates by ID)
                try:
                    self.collection.add(
                        ids=ids,
                        embeddings=embeddings.tolist(),
                        documents=texts,
                        metadatas=metadatas
                    )
                    total_added += len(batch)
                    logger.info(f"Added batch of {len(batch)} articles to ChromaDB")
                    
                except Exception as e:
                    if "already exists" in str(e).lower():
                        total_skipped += len(batch)
                        logger.debug(f"Skipped {len(batch)} duplicate articles")
                    else:
                        raise
            
            return {
                'success': True,
                'total_added': total_added,
                'total_skipped': total_skipped,
                'total_documents': self.collection.count()
            }
            
        except Exception as e:
            logger.error(f"Error adding articles to ChromaDB: {e}")
            return {
                'success': False,
                'error': str(e),
                'total_added': total_added,
                'total_skipped': total_skipped
            }
    
    async def similarity_search(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        min_score: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Perform similarity search in the vector store.
        
        Args:
            query: Search query text
            top_k: Number of results to return
            filters: Metadata filters (e.g., {'source': 'techcrunch'})
            min_score: Minimum similarity score (0-1)
            
        Returns:
            List of matching articles with scores
        """
        if not self.collection:
            await self.initialize()
        
        try:
            # Generate query embedding
            query_embeddings = await self.embedding_generator.generate_embeddings(
                [query],
                batch_size=1
            )
            
            # Prepare where clause for filtering
            where_clause = None
            if filters:
                where_clause = {}
                for key, value in filters.items():
                    where_clause[key] = value
            
            # Query ChromaDB
            results = self.collection.query(
                query_embeddings=query_embeddings.tolist(),
                n_results=top_k,
                where=where_clause
            )
            
            # Format results
            formatted_results = []
            if results and results['ids'] and len(results['ids']) > 0:
                for i in range(len(results['ids'][0])):
                    # Calculate similarity score (ChromaDB returns distances, convert to similarity)
                    distance = results['distances'][0][i] if results.get('distances') else 0
                    similarity = 1 / (1 + distance)  # Convert distance to similarity
                    
                    # Filter by minimum score
                    if similarity < min_score:
                        continue
                    
                    formatted_results.append({
                        'id': results['ids'][0][i],
                        'content': results['documents'][0][i],
                        'metadata': results['metadatas'][0][i],
                        'score': similarity
                    })
            
            logger.info(f"Similarity search returned {len(formatted_results)} results")
            return formatted_results
            
        except Exception as e:
            logger.error(f"Error performing similarity search: {e}")
            return []
    
    async def get_by_id(self, article_id: str) -> Optional[Dict[str, Any]]:
        """
        Get article by ID from vector store.
        
        Args:
            article_id: Article ID
            
        Returns:
            Article data or None
        """
        if not self.collection:
            await self.initialize()
        
        try:
            result = self.collection.get(ids=[article_id])
            
            if result and result['ids'] and len(result['ids']) > 0:
                return {
                    'id': result['ids'][0],
                    'content': result['documents'][0],
                    'metadata': result['metadatas'][0]
                }
            return None
            
        except Exception as e:
            logger.error(f"Error getting article by ID: {e}")
            return None
    
    async def delete_by_id(self, article_id: str) -> bool:
        """
        Delete article from vector store.
        
        Args:
            article_id: Article ID to delete
            
        Returns:
            Success status
        """
        if not self.collection:
            await self.initialize()
        
        try:
            self.collection.delete(ids=[article_id])
            logger.info(f"Deleted article {article_id} from ChromaDB")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting article: {e}")
            return False
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Get vector store statistics.
        
        Returns:
            Statistics dictionary
        """
        if not self.collection:
            await self.initialize()
        
        try:
            count = self.collection.count()
            return {
                'total_documents': count,
                'collection_name': self.collection_name,
                'persist_directory': self.persist_directory,
                'embedding_model': self.embedding_generator.model_name,
                'embedding_dimension': self.embedding_generator.embedding_dim
            }
            
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {'error': str(e)}
    
    def reset(self) -> bool:
        """
        Delete all documents from the collection (dangerous!).
        
        Returns:
            Success status
        """
        try:
            if self.collection:
                self.client.delete_collection(name=self.collection_name)
                logger.warning(f"Deleted collection '{self.collection_name}'")
            return True
            
        except Exception as e:
            logger.error(f"Error resetting collection: {e}")
            return False


# Singleton instance
_vector_store: Optional[ChromaVectorStore] = None


async def get_vector_store() -> ChromaVectorStore:
    """
    Get or create the singleton vector store instance.
    
    Returns:
        Initialized ChromaVectorStore
    """
    global _vector_store
    
    if _vector_store is None:
        _vector_store = ChromaVectorStore()
        await _vector_store.initialize()
    
    return _vector_store
