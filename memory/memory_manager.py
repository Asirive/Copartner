"""
Copartner Memory Manager
==========================
Persistent 4-tier memory system backed by ChromaDB.

Ported from the working Eidos memory/memory_manager.py with these changes:
  - Collection prefix: snap_c1_ → copartner_
  - Embedding function is injected externally (Gemini Embedding API)
  - Falls back to ChromaDB's default (all-MiniLM) if no embedder is set
  - persist_dir defaults to data/memory_store/

Tiers:
  episodic    — conversation history and interaction logs
  semantic    — facts, technical knowledge, learned concepts
  skills      — successful task traces, approach patterns, SKILL.md references
  preferences — user style profile, coding conventions, tool preferences
"""

import json
import time
import hashlib
import logging
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass, asdict

logger = logging.getLogger("Copartner.MemoryManager")

try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    logger.warning("ChromaDB not installed. Run: pip install chromadb")

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_MEMORY_DIR = PROJECT_ROOT / "data" / "memory_store"


@dataclass
class Memory:
    """A single memory entry."""
    content: str
    memory_type: str        # episodic | semantic | skills | preferences
    source: str             # conversation | self_reflection | tool_output | user | skill
    timestamp: float
    metadata: dict
    importance: float = 0.5
    access_count: int = 0
    last_accessed: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Memory":
        return cls(**data)


class MemoryManager:
    """
    Manages Copartner's persistent cross-session memory.

    Designed to be injected with a Gemini embedding function for
    semantic search. Without it, falls back to ChromaDB's built-in
    all-MiniLM-L6-v2 (CPU, ~22M params) — fast enough for MVP.
    """

    COLLECTIONS = {
        "episodic":    "Conversation history and interaction memories",
        "semantic":    "Facts, knowledge, and learned concepts",
        "skills":      "Successful task traces, patterns, and SKILL.md references",
        "preferences": "User style profile, conventions, and tool preferences",
    }

    def __init__(
        self,
        persist_dir: str | Path | None = None,
        embedding_fn: Optional[Callable] = None,
    ):
        if not CHROMADB_AVAILABLE:
            logger.error("ChromaDB is required. Install: pip install chromadb")
            self.client = None
            return

        persist_dir = Path(persist_dir) if persist_dir else DEFAULT_MEMORY_DIR
        persist_dir.mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(
            path=str(persist_dir),
            settings=Settings(anonymized_telemetry=False),
        )

        self._embedding_fn = embedding_fn  # Optional Gemini embedder
        self.collections: dict = {}
        self._init_collections()
        logger.info(f"MemoryManager initialized at: {persist_dir}")
        self._log_stats()

    def _init_collections(self):
        """Create or load ChromaDB collections for each memory tier."""
        for name, description in self.COLLECTIONS.items():
            kwargs = {
                "name": f"copartner_{name}",
                "metadata": {"description": description},
            }
            if self._embedding_fn is not None:
                kwargs["embedding_function"] = self._embedding_fn
            self.collections[name] = self.client.get_or_create_collection(**kwargs)

    def set_embedding_fn(self, embedding_fn: Callable):
        """
        Inject a Gemini-backed embedding function post-init.
        Re-creates collections with the new embedder.
        NOTE: existing documents are NOT re-embedded — this only affects future queries.
        """
        self._embedding_fn = embedding_fn
        self._init_collections()
        logger.info("MemoryManager: Gemini embedding function injected")

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _log_stats(self):
        for name, coll in self.collections.items():
            logger.info(f"  {name}: {coll.count()} memories")

    def _generate_id(self, content: str, memory_type: str) -> str:
        hash_input = f"{content}:{memory_type}:{time.time()}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    # ── Core CRUD ─────────────────────────────────────────────────────────────

    def store(
        self,
        content: str,
        memory_type: str,
        source: str = "conversation",
        importance: float = 0.5,
        metadata: dict | None = None,
    ) -> str:
        """
        Store a memory in the appropriate tier.

        Returns:
            The generated memory ID (or "" on failure).
        """
        if self.client is None:
            return ""

        if memory_type not in self.COLLECTIONS:
            logger.error(f"Invalid memory_type '{memory_type}'. Must be one of: {list(self.COLLECTIONS)}")
            return ""

        memory_id = self._generate_id(content, memory_type)
        now = time.time()

        meta = {
            "source": source,
            "importance": importance,
            "timestamp": now,
            "access_count": 0,
            "last_accessed": now,
        }
        if metadata:
            meta.update(metadata)

        self.collections[memory_type].add(
            ids=[memory_id],
            documents=[content],
            metadatas=[meta],
        )
        logger.debug(f"Stored [{memory_type}] {memory_id} ({len(content)} chars)")
        return memory_id

    def recall(
        self,
        query: str,
        memory_type: str | None = None,
        n_results: int = 5,
        min_importance: float = 0.0,
    ) -> list[dict]:
        """
        Recall memories relevant to a query using semantic similarity.

        Args:
            query:          Natural language search query.
            memory_type:    Specific tier to search (None = search all).
            n_results:      Max results to return.
            min_importance: Filter out memories below this threshold.

        Returns:
            List of dicts: {id, content, metadata, relevance, collection}
        """
        if self.client is None:
            return []

        collections_to_search = (
            [self.collections[memory_type]] if memory_type
            else list(self.collections.values())
        )

        results = []
        for coll in collections_to_search:
            if coll.count() == 0:
                continue

            raw = coll.query(
                query_texts=[query],
                n_results=min(n_results, coll.count()),
            )

            if not raw["documents"] or not raw["documents"][0]:
                continue

            for i, (doc, meta, dist) in enumerate(zip(
                raw["documents"][0],
                raw["metadatas"][0],
                raw["distances"][0],
            )):
                if meta.get("importance", 0) < min_importance:
                    continue

                # Update access tracking
                mem_id = raw["ids"][0][i]
                meta["access_count"] = meta.get("access_count", 0) + 1
                meta["last_accessed"] = time.time()
                coll.update(ids=[mem_id], metadatas=[meta])

                results.append({
                    "id":         mem_id,
                    "content":    doc,
                    "metadata":   meta,
                    "relevance":  1.0 - dist,
                    "collection": coll.name,
                })

        results.sort(key=lambda x: x["relevance"], reverse=True)
        return results[:n_results]

    def forget(self, memory_id: str, memory_type: str) -> bool:
        """Delete a specific memory by ID."""
        if self.client is None or memory_type not in self.collections:
            return False
        try:
            self.collections[memory_type].delete(ids=[memory_id])
            logger.debug(f"Forgot memory: {memory_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to forget {memory_id}: {e}")
            return False

    def consolidate(self, memory_type: str = "episodic", max_age_days: int = 30):
        """
        Prune old, low-importance, rarely-accessed memories.
        High-importance and frequently-accessed memories are always kept.
        """
        if self.client is None:
            return

        coll = self.collections.get(memory_type)
        if not coll or coll.count() == 0:
            return

        cutoff = time.time() - (max_age_days * 86400)
        all_data = coll.get(include=["metadatas"])

        to_delete = []
        for mem_id, meta in zip(all_data["ids"], all_data["metadatas"]):
            ts         = meta.get("timestamp", 0)
            importance = meta.get("importance", 0.5)
            accesses   = meta.get("access_count", 0)

            if ts > cutoff:       continue  # recent
            if importance >= 0.7: continue  # important
            if accesses >= 5:     continue  # well-used

            to_delete.append(mem_id)

        if to_delete:
            coll.delete(ids=to_delete)
            logger.info(f"Consolidated {len(to_delete)} old '{memory_type}' memories")

    # ── Convenience write helpers ─────────────────────────────────────────────

    def store_conversation(self, user_msg: str, assistant_msg: str, quality: float = 0.5):
        """Store a Q/A exchange as episodic memory."""
        content = f"User: {user_msg[:300]}\nCopartner: {assistant_msg[:600]}"
        self.store(content, "episodic", source="conversation", importance=quality)

    def store_skill(self, description: str, example: str, domain: str = "general"):
        """Store a successful approach as a skill memory."""
        content = f"Skill: {description}\nExample: {example}"
        self.store(content, "skills", source="self_reflection", importance=0.75,
                   metadata={"domain": domain})

    def store_fact(self, fact: str, source: str = "learned", confidence: float = 0.8):
        """Store a learned fact or piece of knowledge."""
        self.store(fact, "semantic", source=source, importance=confidence,
                   metadata={"confidence": confidence})

    def store_preference(self, key: str, value: str):
        """Store a user preference or style convention."""
        content = f"{key}: {value}"
        self.store(content, "preferences", source="user", importance=0.9,
                   metadata={"key": key})

    # ── Context injection for Gemini prompt ──────────────────────────────────

    def get_context_injection(self, query: str, max_chars: int = 4000) -> str:
        """
        Build a context block to prepend to the Gemini prompt.
        Pulls the most relevant memories and formats them as readable context.
        """
        memories = self.recall(query, n_results=8)
        if not memories:
            return ""

        lines = ["[Relevant memories from past sessions:]"]
        total = 0
        for mem in memories:
            entry = f"- [{mem['metadata'].get('source', '?')}] {mem['content']}"
            if total + len(entry) > max_chars:
                break
            lines.append(entry)
            total += len(entry)

        return "\n".join(lines)

    def stats(self) -> dict:
        """Return memory statistics."""
        if self.client is None:
            return {"status": "unavailable"}

        colls = {}
        for name, coll in self.collections.items():
            colls[name] = {"count": coll.count()}

        return {
            "status": "active",
            "collections": colls,
            "total_memories": sum(c["count"] for c in colls.values()),
        }
