"""
Qdrant embedded vector store for long-term memory.
No external server needed — data lives in ./data/qdrant.
Embeddings: paraphrase-multilingual-MiniLM-L12-v2 (dim=384, multilingual)
"""
from __future__ import annotations

import hashlib
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("memory.qdrant_store")

COLLECTION  = "facts"
VECTOR_DIM  = 384
DATA_PATH   = Path(__file__).resolve().parent.parent / "data" / "qdrant"


def _point_id(category: str, key: str) -> int:
    """Stable integer ID from category+key."""
    h = hashlib.sha256(f"{category}:{key}".encode()).hexdigest()
    return int(h[:15], 16)  # fits in uint64


class QdrantMemoryStore:
    """Embedded Qdrant + sentence-transformers memory backend."""

    def __init__(self, path: str | Path = DATA_PATH) -> None:
        self._path = Path(path)
        self._client = None
        self._model  = None
        self._ready  = False
        self._init()

    def _init(self) -> None:
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import VectorParams, Distance

            self._path.mkdir(parents=True, exist_ok=True)
            self._client = QdrantClient(path=str(self._path))

            existing = {c.name for c in self._client.get_collections().collections}
            if COLLECTION not in existing:
                self._client.create_collection(
                    collection_name=COLLECTION,
                    vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
                )
                logger.info("[Qdrant] Collection 'facts' created")

            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
            self._ready = True
            logger.info("[Qdrant] Ready")

        except ImportError as e:
            logger.warning(f"[Qdrant] Dependency missing — falling back to JSON: {e}")
        except Exception as e:
            logger.error(f"[Qdrant] Init failed: {e}")

    @property
    def is_ready(self) -> bool:
        return self._ready

    def _embed(self, text: str) -> list[float]:
        return self._model.encode(text, show_progress_bar=False).tolist()

    def upsert_fact(
        self,
        category: str,
        key: str,
        value: str,
        source_text: str = "",
    ) -> None:
        if not self._ready:
            return
        from qdrant_client.models import PointStruct

        embed_text = f"{category} {key} {value}"
        vector     = self._embed(embed_text)
        point_id   = _point_id(category, key)

        self._client.upsert(
            collection_name=COLLECTION,
            points=[
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "category":    category,
                        "key":         key,
                        "value":       value,
                        "source_text": source_text,
                    },
                )
            ],
        )

    def search_facts(self, query: str, limit: int = 5) -> list[dict]:
        if not self._ready:
            return []
        vector = self._embed(query)
        hits   = self._client.search(
            collection_name=COLLECTION,
            query_vector=vector,
            limit=limit,
        )
        return [
            {
                "category": h.payload.get("category"),
                "key":      h.payload.get("key"),
                "value":    h.payload.get("value"),
                "score":    h.score,
            }
            for h in hits
        ]

    def get_all_facts(self) -> dict:
        """Return all facts in the same nested-dict format as long_term.json."""
        if not self._ready:
            return {}
        result: dict[str, Any] = {}
        offset = None
        while True:
            resp, offset = self._client.scroll(
                collection_name=COLLECTION,
                limit=256,
                offset=offset,
                with_payload=True,
            )
            for point in resp:
                cat = point.payload.get("category", "notes")
                key = point.payload.get("key", "unknown")
                val = point.payload.get("value", "")
                result.setdefault(cat, {})[key] = {"value": val}
            if offset is None:
                break
        return result

    def migrate_from_json(self, json_data: dict) -> int:
        """
        Import all facts from a long_term.json dict into Qdrant.
        Returns the number of facts migrated.
        """
        count = 0
        for category, entries in json_data.items():
            if not isinstance(entries, dict):
                continue
            for key, entry in entries.items():
                if isinstance(entry, dict):
                    value = str(entry.get("value", ""))
                else:
                    value = str(entry)
                if value:
                    self.upsert_fact(category, key, value)
                    count += 1
        return count
