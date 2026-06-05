"""Test fixtures. Forces a throwaway SQLite DB and the offline FakeLLM before
any app module is imported."""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mktemp(suffix='.db')}")
os.environ["LLM_PROVIDER"] = "fake"
os.environ["DEFAULT_MODEL"] = "fake"
os.environ.setdefault("BUS_BACKEND", "memory")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
