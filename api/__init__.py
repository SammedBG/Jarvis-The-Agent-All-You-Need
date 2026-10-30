"""api - FastAPI backend for JARVIS desktop assistant.

Thin HTTP layer over the existing jarvis/ package. No agent logic, approval
behaviour, fast path, lookup tools or safety code is changed here; every route
calls the existing jarvis.* functions directly.
"""
from .main import app

__all__ = ["app"]
