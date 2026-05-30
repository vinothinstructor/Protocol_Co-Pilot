"""
JSON file cache for LLM scoring responses.
Cache key: SHA-256 of (operation, clause_text, context_json).
Used by cached mode; populated by scripts/precache_scores.py in live mode.
"""
import hashlib
import json
import pathlib
from typing import Any

CACHE_PATH = pathlib.Path(__file__).parent.parent / "cache" / "score_cache.json"


def _key(operation: str, clause_text: str, context: dict | None = None) -> str:
    payload = json.dumps({"op": operation, "text": clause_text, "ctx": context or {}}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _load() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save(data: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(data, indent=2))


def cache_get(operation: str, clause_text: str, context: dict | None = None) -> Any | None:
    store = _load()
    return store.get(_key(operation, clause_text, context))


def cache_set(operation: str, clause_text: str, value: Any, context: dict | None = None) -> None:
    store = _load()
    store[_key(operation, clause_text, context)] = value
    _save(store)


def cache_has(operation: str, clause_text: str, context: dict | None = None) -> bool:
    return _load().get(_key(operation, clause_text, context)) is not None
