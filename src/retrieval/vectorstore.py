"""ChromaDB vector store for skill retrieval."""

import logging
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.config import Settings

from src.skills.parser import Skill
from src.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class VectorStore:
    """ChromaDB-based vector store for semantic skill search."""
    
    COLLECTION_NAME = "skills"
    
    def __init__(
        self,
        persist_dir: Path,
        embedding_provider: LLMProvider,
    ):
        """Initialize vector store.
        
        Args:
            persist_dir: Directory to persist ChromaDB data.
            embedding_provider: LLM provider to use for embeddings.
        """
        self.persist_dir = Path(persist_dir)
        self.embedding_provider = embedding_provider
        self._client: Optional[chromadb.Client] = None
        self._collection = None
        self._disabled_skills: set[str] = set()
    
    async def initialize(self) -> None:
        """Initialize ChromaDB client and collection."""
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        
        # Create persistent client
        self._client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=Settings(
                anonymized_telemetry=False,
            ),
        )
        
        # Get or create collection
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        
        logger.info(f"Initialized ChromaDB at {self.persist_dir}")
    
    async def _get_embedding(self, text: str) -> list[float]:
        """Get embedding for text using the embedding provider."""
        try:
            return await self.embedding_provider.embed(text)
        except Exception as e:
            logger.error(f"Failed to get embedding: {e}")
            raise
    
    async def index_skill(self, skill: Skill) -> None:
        """Index a single skill."""
        if not self._collection:
            raise RuntimeError("Vector store not initialized")
        
        # Create document from description
        document = f"{skill.title}\n\n{skill.description}"
        
        # Get embedding
        embedding = await self._get_embedding(document)
        
        # Upsert to collection
        self._collection.upsert(
            ids=[skill.name],
            embeddings=[embedding],
            documents=[document],
            metadatas=[{
                "title": skill.title,
                "name": skill.name,
                "file_path": str(skill.file_path),
            }],
        )
        
        logger.debug(f"Indexed skill: {skill.name}")
    
    async def index_skills(self, skills: list[Skill]) -> None:
        """Index multiple skills."""
        for skill in skills:
            if skill.enabled:
                await self.index_skill(skill)
    
    async def search(
        self,
        query: str,
        top_k: int = 3,
    ) -> list[dict]:
        """Search for matching skills.
        
        Args:
            query: Search query.
            top_k: Number of results to return.
        
        Returns:
            List of matches with name, title, score, and document.
        """
        if not self._collection:
            raise RuntimeError("Vector store not initialized")
        
        # Get query embedding
        query_embedding = await self._get_embedding(query)
        
        # Search collection
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
        
        # Convert to list of dicts
        matches = []
        
        if results and results["ids"] and results["ids"][0]:
            for i, skill_id in enumerate(results["ids"][0]):
                # Skip disabled skills
                if skill_id in self._disabled_skills:
                    continue
                
                # ChromaDB returns distance, convert to similarity
                distance = results["distances"][0][i] if results["distances"] else 0
                score = 1 - distance  # Cosine distance to similarity
                
                metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                document = results["documents"][0][i] if results["documents"] else ""
                
                matches.append({
                    "name": skill_id,
                    "title": metadata.get("title", skill_id),
                    "score": score,
                    "document": document,
                })
        
        return matches
    
    async def delete_skill(self, skill_name: str) -> None:
        """Remove a skill from the index."""
        if not self._collection:
            raise RuntimeError("Vector store not initialized")
        
        try:
            self._collection.delete(ids=[skill_name])
            logger.debug(f"Deleted skill from index: {skill_name}")
        except Exception as e:
            logger.warning(f"Failed to delete skill {skill_name}: {e}")
    
    async def clear(self) -> None:
        """Clear all skills from the index."""
        if not self._client:
            raise RuntimeError("Vector store not initialized")
        
        # Delete and recreate collection
        try:
            self._client.delete_collection(self.COLLECTION_NAME)
        except Exception:
            pass
        
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        
        logger.info("Cleared vector store")
    
    async def count(self) -> int:
        """Get number of indexed skills."""
        if not self._collection:
            return 0
        return self._collection.count()
    
    def disable_skill(self, skill_name: str) -> None:
        """Mark a skill as disabled (excluded from search)."""
        self._disabled_skills.add(skill_name)
    
    def enable_skill(self, skill_name: str) -> None:
        """Mark a skill as enabled."""
        self._disabled_skills.discard(skill_name)
    
    def set_disabled_skills(self, skill_names: set[str]) -> None:
        """Set the complete list of disabled skills."""
        self._disabled_skills = set(skill_names)
