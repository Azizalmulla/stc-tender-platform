"""
Voyage AI Embedding Service
Uses voyage-law-2 model optimized for legal documents (government tenders)
"""

import voyageai
from typing import List, Optional
from app.core.config import settings


class VoyageEmbeddingService:
    """
    Service for generating embeddings using Voyage AI
    
    Model: voyage-law-2
    - Optimized for legal documents (perfect for government tenders)
    - Context length: 16,000 tokens (~24,000 Arabic characters)
    - Embedding dimension: 1024
    - Excellent Arabic language support
    """
    
    def __init__(self):
        """Initialize Voyage AI client"""
        try:
            # Client automatically uses VOYAGE_API_KEY environment variable
            self.client = voyageai.Client()
            self.model = "voyage-law-2"  # Best for legal/government documents
            self.embedding_dimension = 1024
            print("✅ Voyage AI service initialized successfully")
        except Exception as e:
            print(f"⚠️  Voyage AI initialization warning: {e}")
            self.client = None
    
    def generate_embedding(
        self, 
        text: str, 
        input_type: str = "document"
    ) -> List[float]:
        """
        Generate embedding vector for text
        
        Args:
            text: Text to embed (tender content or search query)
            input_type: "document" for storing tenders, "query" for search queries
                       This optimizes the embedding for retrieval tasks
        
        Returns:
            List of 1024 floats representing the embedding vector
            Returns zero vector on error
        """
        if not self.client:
            print("  ⚠️  Voyage client not initialized, returning zero vector")
            return [0.0] * self.embedding_dimension
        
        try:
            # Voyage automatically handles truncation with truncation=True (default)
            # voyage-law-2 supports up to 16,000 tokens (~24,000 Arabic chars)
            result = self.client.embed(
                texts=[text],
                model=self.model,
                input_type=input_type,  # "document" or "query"
                truncation=True  # Auto-truncate if text exceeds context length
            )
            
            # Log token usage
            tokens_used = result.total_tokens
            print(f"  ✅ Voyage embedding generated ({tokens_used} tokens, input_type={input_type})")
            
            # Return the embedding (list of 1024 floats)
            return result.embeddings[0]
            
        except Exception as e:
            print(f"  ❌ Voyage embedding generation error: {e}")
            # Return zero vector as fallback
            return [0.0] * self.embedding_dimension
    
    def generate_batch_embeddings(
        self, 
        texts: List[str], 
        input_type: str = "document"
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batch
        
        Args:
            texts: List of texts to embed (max 1000)
            input_type: "document" or "query"
        
        Returns:
            List of embedding vectors
        """
        if not self.client:
            print("  ⚠️  Voyage client not initialized")
            return [[0.0] * self.embedding_dimension for _ in texts]
        
        try:
            # Batch processing (max 1000 texts, 120K tokens total for voyage-law-2)
            result = self.client.embed(
                texts=texts,
                model=self.model,
                input_type=input_type,
                truncation=True
            )
            
            print(f"  ✅ Voyage batch embeddings generated ({len(texts)} texts, {result.total_tokens} tokens)")
            
            return result.embeddings
            
        except Exception as e:
            print(f"  ❌ Voyage batch embedding error: {e}")
            return [[0.0] * self.embedding_dimension for _ in texts]


# Global instance
voyage_service = VoyageEmbeddingService()
