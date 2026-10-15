"""
tests/conftest.py
=================
Shared test fixtures for all phases.

Provides:
  - A single test‑database engine (``test.db``) used by every test.
  - An ``app.dependency_overrides[get_db]`` that routes all FastAPI requests
    to this test database.
  - An ``autouse`` fixture that drops **and** re‑creates every table before
    each test, so tests are fully isolated.
  - A ``client`` fixture that yields a Starlette ``TestClient``.
  - A ``db_session`` fixture for direct DB access in tests.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.main import app
from app.database import Base, get_db


# Single test‑database engine shared by ALL test modules

TEST_DATABASE_URL = "sqlite:///./test.db"
test_engine = create_engine(
    TEST_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=test_engine
)


def _override_get_db():
    """Dependency override: yield sessions from the test engine."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# Override once — every test module sees the same override.
app.dependency_overrides[get_db] = _override_get_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_db():
    """Drop and re‑create all tables before **each** test for isolation."""
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def client():
    """Starlette TestClient wired to the overridden app."""
    return TestClient(app)


@pytest.fixture
def db_session():
    """Direct DB session for test helpers that bypass the API."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
