"""Shared pytest fixtures. Sets required env vars BEFORE any `app.*` module
is imported, since app/config.py fail-fasts on DATABASE_URL / WORKER_URL /
INTEGRATION_BRIDGE_URL at import time.
"""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgres://test:test@localhost:5432/test")
os.environ.setdefault("WORKER_URL", "http://worker.test:8100")
os.environ.setdefault("INTEGRATION_BRIDGE_URL", "http://bridge.test:8080")
# Intentionally do NOT set OPENROUTER_API_KEY/OPENAI_API_KEY here — the whole
# point of the fail-fast design is that the service must be importable and
# most of it testable without them. Tests that need a "key present" path set
# it locally via monkeypatch.
