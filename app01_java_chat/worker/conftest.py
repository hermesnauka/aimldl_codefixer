"""Ensures `worker/` (this directory) is on sys.path so `import app...` in
tests resolves the same way it does when uvicorn runs `app.main:app` from
this directory — no package install step required for `pytest` to work."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
