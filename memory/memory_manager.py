"""
Memory manager with pluggable backend: "json" (default) or "qdrant".
Switch via config/api_keys.json:  {"memory_backend": "qdrant"}

On first qdrant start, migrates long_term.json → Qdrant automatically.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from threading import Lock
from typing import Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR    = get_base_dir()
MEMORY_PATH = BASE_DIR / "memory" / "long_term.json"
QDRANT_PATH = BASE_DIR / "data" / "qdrant"

_lock = Lock()
MAX_VALUE_LENGTH = 300


# ---------------------------------------------------------------------------
# MemoryStore Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class MemoryStore(Protocol):
    def upsert_fact(self, category: str, key: str, value: str, source_text: str = "") -> None: ...
    def search_facts(self, query: str, limit: int = 5) -> list[dict]: ...
    def get_all_facts(self) -> dict: ...


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _get_config() -> dict:
    cfg = BASE_DIR / "config" / "api_keys.json"
    try:
        return json.loads(cfg.read_text(encoding="utf-8")) if cfg.exists() else {}
    except Exception:
        return {}


def _get_backend() -> str:
    return _get_config().get("memory_backend", "json")


# ---------------------------------------------------------------------------
# Qdrant backend — lazy singleton
# ---------------------------------------------------------------------------

_qdrant_store: "QdrantMemoryStore | None" = None  # type: ignore[name-defined]


def _get_qdrant():
    global _qdrant_store
    if _qdrant_store is None:
        from memory.qdrant_store import QdrantMemoryStore
        store = QdrantMemoryStore(QDRANT_PATH)
        if store.is_ready:
            _maybe_migrate(store)
        _qdrant_store = store
    return _qdrant_store


def _maybe_migrate(store) -> None:
    """Migrate long_term.json → Qdrant if Qdrant is empty and JSON exists."""
    if not MEMORY_PATH.exists():
        return
    # Check if collection already has data
    try:
        all_facts = store.get_all_facts()
        if all_facts:
            return  # already migrated
        raw = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
        count = store.migrate_from_json(raw)
        print(f"[Memory] ✅ Migrated {count} facts from long_term.json → Qdrant")
    except Exception as e:
        print(f"[Memory] ⚠️ Migration failed: {e}")


# ---------------------------------------------------------------------------
# JSON backend (original implementation, unchanged)
# ---------------------------------------------------------------------------

def _empty_memory() -> dict:
    return {
        "identity":      {},
        "preferences":   {},
        "relationships": {},
        "notes":         {},
    }


def load_memory() -> dict:
    if _get_backend() == "qdrant":
        store = _get_qdrant()
        if store.is_ready:
            return store.get_all_facts() or _empty_memory()

    if not MEMORY_PATH.exists():
        return _empty_memory()

    with _lock:
        try:
            data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else _empty_memory()
        except Exception as e:
            print(f"[Memory] ⚠️ Load error: {e}")
            return _empty_memory()


def save_memory(memory: dict) -> None:
    if not isinstance(memory, dict):
        return

    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)

    with _lock:
        MEMORY_PATH.write_text(
            json.dumps(memory, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def _truncate_value(val: str) -> str:
    if isinstance(val, str) and len(val) > MAX_VALUE_LENGTH:
        return val[:MAX_VALUE_LENGTH].rstrip() + "…"
    return val


def _recursive_update(target: dict, updates: dict) -> bool:
    changed = False

    for key, value in updates.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue

        if isinstance(value, dict) and "value" not in value:
            if key not in target or not isinstance(target[key], dict):
                target[key] = {}
                changed = True
            if _recursive_update(target[key], value):
                changed = True
        else:
            if isinstance(value, dict) and "value" in value:
                entry = {"value": _truncate_value(str(value["value"]))}
            else:
                entry = {"value": _truncate_value(str(value))}

            if key not in target or target[key] != entry:
                target[key] = entry
                changed = True

    return changed


def update_memory(memory_update: dict) -> dict:
    if not isinstance(memory_update, dict) or not memory_update:
        return load_memory()

    if _get_backend() == "qdrant":
        store = _get_qdrant()
        if store.is_ready:
            for category, entries in memory_update.items():
                if isinstance(entries, dict):
                    for key, entry in entries.items():
                        val = entry.get("value", "") if isinstance(entry, dict) else str(entry)
                        if val:
                            store.upsert_fact(category, key, str(val))
            print(f"[Memory] 💾 Qdrant updated: {list(memory_update.keys())}")
            return store.get_all_facts()

    memory = load_memory()
    if _recursive_update(memory, memory_update):
        save_memory(memory)
        print(f"[Memory] 💾 Saved: {list(memory_update.keys())}")
    return memory


def format_memory_for_prompt(memory: dict | None, recent_text: str = "") -> str:
    """
    Format memory for LLM context.
    With Qdrant backend: semantic search on recent_text for top-5 relevant facts.
    With JSON backend: original full-scan approach.
    """
    if _get_backend() == "qdrant" and recent_text:
        store = _get_qdrant()
        if store.is_ready:
            hits = store.search_facts(recent_text, limit=5)
            if not hits:
                return ""
            lines = [f"{h['key']}: {h['value']}" for h in hits if h.get("value")]
            if not lines:
                return ""
            result = "[USER MEMORY]\n" + "\n".join(f"- {l}" for l in lines)
            return (result[:797] + "…" if len(result) > 800 else result) + "\n"

    # JSON / fallback path
    if not memory:
        return ""

    lines = []

    identity = memory.get("identity", {})
    name = identity.get("name", {}).get("value")
    age  = identity.get("age",  {}).get("value")
    bday = identity.get("birthday", {}).get("value")
    city = identity.get("city", {}).get("value")
    if name: lines.append(f"Name: {name}")
    if age:  lines.append(f"Age: {age}")
    if bday: lines.append(f"Birthday: {bday}")
    if city: lines.append(f"City: {city}")

    for i, (key, entry) in enumerate(memory.get("preferences", {}).items()):
        if i >= 5:
            break
        val = entry.get("value") if isinstance(entry, dict) else entry
        if val:
            lines.append(f"{key.replace('_', ' ').title()}: {val}")

    for i, (key, entry) in enumerate(memory.get("relationships", {}).items()):
        if i >= 5:
            break
        val = entry.get("value") if isinstance(entry, dict) else entry
        if val:
            lines.append(f"{key.title()}: {val}")

    for i, (key, entry) in enumerate(memory.get("notes", {}).items()):
        if i >= 5:
            break
        val = entry.get("value") if isinstance(entry, dict) else entry
        if val:
            lines.append(f"{key}: {val}")

    if not lines:
        return ""

    result = "[USER MEMORY]\n" + "\n".join(f"- {l}" for l in lines)
    if len(result) > 800:
        result = result[:797] + "…"
    return result + "\n"
