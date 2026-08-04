"""Test env setup, applied before any test module is collected.

pytest imports conftest.py before it imports test_*.py files, regardless
of alphabetical order. That matters here: app/core/config.get_settings()
is @lru_cache'd, so whichever test module's imports trigger it FIRST wins
for the whole session. Without this file, test_ai_provider.py (collected
before test_api.py) imports app.services.ai, which calls get_settings()
before test_api.py's own os.environ assignments run -- silently locking
in whatever DATABASE_URL/AI_PROVIDER/JWT_SECRET happen to already be set
in the developer's shell (e.g. from an unrelated project) instead of the
throwaway test config.

Unconditional assignment on purpose, not setdefault: the whole point is
to guarantee an isolated test config regardless of what's already in the
ambient environment -- a stray DATABASE_URL pointing at a real Postgres
database (from an unrelated project) is exactly the failure mode this
guards against.
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_trustai.db"
os.environ["AI_PROVIDER"] = "mock"
os.environ["JWT_SECRET"] = "test-secret"
