"""
RAG (Retrieval Augmented Generation) Search using ChromaDB
Based on official Polymarket agents framework
"""
import os
import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import hashlib

logger = logging.getLogger(__name__)

# Try to import chromadb (optional dependency)
try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    logger.warning("ChromaDB not installed - RAG search disabled. Install with: pip install chromadb")

# Try to import OpenAI for embeddings
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


@dataclass
class MarketDocument:
    """Document representing a market for RAG"""
    id: str
    question: str
    description: str
    metadata: Dict[str, Any]
    embedding: Optional[List[float]] = None


class ChromaRAGConnector:
    """
    ChromaDB-based RAG for semantic market search
    
    Uses OpenAI embeddings for semantic similarity search across markets
    
    Usage:
        connector = ChromaRAGConnector()
        connector.index_markets(markets)
        results = connector.search("Who will win the presidential election?")
    """
    
    def __init__(
        self,
        collection_name: str = "polymarket_markets",
        persist_directory: Optional[str] = None,
        openai_api_key: Optional[str] = None
    ):
        """
        Initialize ChromaDB connector
        
        Args:
            collection_name: Name of the ChromaDB collection
            persist_directory: Directory to persist the database
            openai_api_key: OpenAI API key for embeddings
        """
        self.collection_name = collection_name
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY", "")
        self.client = None
        self.collection = None
        
        if not CHROMADB_AVAILABLE:
            logger.warning("ChromaDB not available")
            return
        
        try:
            if persist_directory:
                self.client = chromadb.PersistentClient(path=persist_directory)
            else:
                self.client = chromadb.Client()
            
            # Get or create collection
            self.collection = self.client.get_or_create_collection(
                name=collection_name,
                metadata={"description": "Polymarket markets for RAG search"}
            )
            
            logger.info(f"ChromaDB initialized with collection '{collection_name}'")
            
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}")
            self.client = None
            self.collection = None
    
    def _get_embedding(self, text: str) -> Optional[List[float]]:
        """Get embedding for text using OpenAI"""
        if not OPENAI_AVAILABLE or not self.openai_api_key:
            return None
        
        try:
            client = openai.OpenAI(api_key=self.openai_api_key)
            response = client.embeddings.create(
                model="text-embedding-3-small",
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"OpenAI embedding failed: {e}")
            return None
    
    def _generate_doc_id(self, market_id: str) -> str:
        """Generate consistent document ID"""
        return hashlib.md5(market_id.encode()).hexdigest()
    
    def index_market(self, market: Dict[str, Any]) -> bool:
        """
        Index a single market
        
        Args:
            market: Market data dict
            
        Returns:
            True if indexed successfully
        """
        if not self.collection:
            return False
        
        try:
            market_id = market.get("condition_id") or market.get("id", "")
            question = market.get("question", "")
            description = market.get("description", "")
            
            # Combine text for embedding
            text = f"{question} {description}"
            doc_id = self._generate_doc_id(market_id)
            
            # Add to collection (ChromaDB generates embeddings if not provided)
            self.collection.upsert(
                ids=[doc_id],
                documents=[text],
                metadatas=[{
                    "market_id": market_id,
                    "question": question,
                    "volume": str(market.get("volume", 0)),
                    "liquidity": str(market.get("liquidity", 0)),
                    "end_date": market.get("end_date_iso", ""),
                    "slug": market.get("slug", "")
                }]
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to index market: {e}")
            return False
    
    def index_markets(self, markets: List[Dict[str, Any]]) -> int:
        """
        Index multiple markets
        
        Args:
            markets: List of market data dicts
            
        Returns:
            Number of markets indexed
        """
        if not self.collection:
            return 0
        
        indexed = 0
        for market in markets:
            if self.index_market(market):
                indexed += 1
        
        logger.info(f"Indexed {indexed}/{len(markets)} markets")
        return indexed
    
    def search(
        self,
        query: str,
        n_results: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Semantic search for markets
        
        Args:
            query: Natural language query
            n_results: Number of results to return
            
        Returns:
            List of matching market metadata
        """
        if not self.collection:
            return []
        
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results
            )
            
            matches = []
            if results and results.get("metadatas"):
                for i, metadata in enumerate(results["metadatas"][0]):
                    matches.append({
                        **metadata,
                        "score": 1.0 - (results.get("distances", [[]])[0][i] if results.get("distances") else 0)
                    })
            
            return matches
            
        except Exception as e:
            logger.error(f"RAG search failed: {e}")
            return []
    
    def get_similar_markets(
        self,
        market_id: str,
        n_results: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Find markets similar to a given market
        
        Args:
            market_id: ID of the reference market
            n_results: Number of similar markets to return
            
        Returns:
            List of similar market metadata
        """
        if not self.collection:
            return []
        
        try:
            doc_id = self._generate_doc_id(market_id)
            
            # Get the market's embedding
            result = self.collection.get(
                ids=[doc_id],
                include=["embeddings", "documents"]
            )
            
            if not result or not result.get("documents"):
                return []
            
            # Search for similar
            query_text = result["documents"][0]
            similar = self.search(query_text, n_results=n_results + 1)
            
            # Filter out the original market
            return [m for m in similar if m.get("market_id") != market_id][:n_results]
            
        except Exception as e:
            logger.error(f"Similar markets search failed: {e}")
            return []
    
    def clear(self):
        """Clear all indexed markets"""
        if self.client and self.collection:
            try:
                self.client.delete_collection(self.collection_name)
                self.collection = self.client.create_collection(
                    name=self.collection_name,
                    metadata={"description": "Polymarket markets for RAG search"}
                )
                logger.info("Cleared RAG index")
            except Exception as e:
                logger.error(f"Failed to clear index: {e}")
    
    @property
    def count(self) -> int:
        """Get number of indexed documents"""
        if not self.collection:
            return 0
        return self.collection.count()


class SimpleRAGConnector:
    """
    Simple in-memory RAG connector (no external dependencies)
    Uses TF-IDF-like scoring for basic semantic search
    """
    
    def __init__(self):
        self.documents: Dict[str, Dict[str, Any]] = {}
        self.index: Dict[str, List[str]] = {}  # word -> [doc_ids]
    
    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenization"""
        import re
        text = text.lower()
        words = re.findall(r'\b[a-z]+\b', text)
        # Remove common stop words
        stop_words = {"the", "a", "an", "is", "are", "will", "be", "to", "in", "on", "for", "of", "by", "at"}
        return [w for w in words if w not in stop_words and len(w) > 2]
    
    def index_market(self, market: Dict[str, Any]) -> bool:
        """Index a single market"""
        try:
            market_id = market.get("condition_id") or market.get("id", "")
            question = market.get("question", "")
            description = market.get("description", "")
            
            text = f"{question} {description}"
            tokens = self._tokenize(text)
            
            self.documents[market_id] = {
                "market_id": market_id,
                "question": question,
                "description": description,
                "volume": market.get("volume", 0),
                "liquidity": market.get("liquidity", 0),
                "tokens": set(tokens)
            }
            
            for token in tokens:
                if token not in self.index:
                    self.index[token] = []
                if market_id not in self.index[token]:
                    self.index[token].append(market_id)
            
            return True
        except Exception as e:
            logger.error(f"Failed to index market: {e}")
            return False
    
    def index_markets(self, markets: List[Dict[str, Any]]) -> int:
        """Index multiple markets"""
        indexed = 0
        for market in markets:
            if self.index_market(market):
                indexed += 1
        return indexed
    
    def search(self, query: str, n_results: int = 10) -> List[Dict[str, Any]]:
        """Search for markets matching query"""
        query_tokens = set(self._tokenize(query))
        
        if not query_tokens:
            return []
        
        # Score documents by token overlap
        scores: Dict[str, float] = {}
        for token in query_tokens:
            for doc_id in self.index.get(token, []):
                doc = self.documents.get(doc_id)
                if doc:
                    # Score based on overlap ratio
                    overlap = len(query_tokens & doc["tokens"])
                    score = overlap / len(query_tokens)
                    scores[doc_id] = max(scores.get(doc_id, 0), score)
        
        # Sort by score
        sorted_docs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        results = []
        for doc_id, score in sorted_docs[:n_results]:
            doc = self.documents[doc_id]
            results.append({
                "market_id": doc["market_id"],
                "question": doc["question"],
                "volume": doc["volume"],
                "liquidity": doc["liquidity"],
                "score": score
            })
        
        return results
    
    @property
    def count(self) -> int:
        """Get number of indexed documents"""
        return len(self.documents)
