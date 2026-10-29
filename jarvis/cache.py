"""
jarvis/cache.py - small thread-safe TTL cache.

Replaces Streamlit's @st.cache_data decorators so jarvis/ and api/ never
need Streamlit imported. Two flavours:

  * ``cache_data(ttl=...)``  -> memoizes a function's return value (TTL).
  * ``TTLCache(namespace, ttl)`` -> explicit dict with expiry + clear().

Streamlit pages can still call ``st.cache_data.clear()`` (harmless: streamlit
keeps its own empty cache there) but the real clearing is done via a
``bust()`` function exported alongside.
"""
from __future__ import annotations

import threading
import time
from functools import wraps
from typing import Any, Callable, Dict, Tuple

_lock = threading.RLock()
_store: Dict[Tuple, Any] = {}        # key -> value
_expiry: Dict[Tuple, float] = {}     # key -> epoch expiry


def cache_data(ttl: int = 60, max_entries: int = 256):
    """Memoize a (hashable-args) function for *ttl* seconds."""
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            key = (fn.__qualname__, args, frozenset(sorted(kwargs.items())))
            now = time.monotonic()
            with _lock:
                if key in _store and _expiry.get(key, 0) > now:
                    return _store[key]
                value = fn(*args, **kwargs)
                _store[key] = value
                _expiry[key] = now + max(1, int(ttl))
                # simple bound on cache size
                if len(_store) > max_entries:
                    # drop the oldest by expiry
                    oldest = min(_expiry, key=lambda k: _expiry[k])
                    _store.pop(oldest, None)
                    _expiry.pop(oldest, None)
                return value
        def _clear() -> None:
            with _lock:
                for k in list(_store):
                    if k[0] == fn.__qualname__:
                        _store.pop(k, None)
                        _expiry.pop(k, None)
        wrapper.clear = _clear  # type: ignore[attr-defined]
        return wrapper
    return decorator


def bust_all() -> None:
    """Clear every entry (Streamlit-equivalent of st.cache_data.clear())."""
    with _lock:
        _store.clear()
        _expiry.clear()


_STATE: Dict[str, Any] = {}
_STATE_LOCK = threading.RLock()


def get_state(token, default=None):
    with _STATE_LOCK:
        return _STATE.get(token, default)


def set_state(token, value):
    with _STATE_LOCK:
        _STATE[token] = value


def clear_state(token):
    with _STATE_LOCK:
        _STATE.pop(token, None)
