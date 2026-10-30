"""app_pages/_st_helpers.py - Streamlit-only helpers (kept for the Streamlit UI).

Things that genuinely depend on Streamlit live here so jarvis/ and api/
stay Streamlit-free. The React frontend never imports this module.
"""
from __future__ import annotations

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None  # type: ignore


def bust_caches() -> None:
    """Clear both the jarvis TTL cache and Streamlit's own cache (if present)."""
    try:
        from jarvis.cache import bust_all

        bust_all()
    except Exception:
        pass
    try:
        if st is not None:
            st.cache_data.clear()
    except Exception:
        pass
PY