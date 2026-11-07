import os
import tempfile
from pathlib import Path

# Isolated test environment: temp SQLite DB + upload dir, deterministic date, no LLM key.
_tmp = Path(tempfile.mkdtemp(prefix="udyam_test_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_tmp / 'test.db').as_posix()}"
os.environ["UPLOAD_DIR"] = str(_tmp / "uploads")
os.environ["REFERENCE_DATE"] = "2026-07-15"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""
os.environ["LLM_PROVIDER"] = "mock"
os.environ["PAYMENT_GATEWAY"] = "sandbox"
os.environ["SANDBOX_SETTLE_SECONDS"] = "0"
os.environ["GOOGLE_CLIENT_ID"] = ""
os.environ["ADMIN_EMAIL"] = "admin@test.example"
os.environ["ADMIN_PASSWORD"] = "AdminPass#123"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.security import auth_limiter, payment_limiter, upload_limiter  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_limits():
    auth_limiter.reset()
    upload_limiter.reset()
    payment_limiter.reset()


@pytest.fixture()
def db():
    from app.db import SessionLocal

    with SessionLocal() as s:
        yield s


@pytest.fixture(scope="session")
def catalogue_map(client):
    from app.db import SessionLocal
    from app.services.catalogue import all_products

    with SessionLocal() as s:
        return all_products(s)
