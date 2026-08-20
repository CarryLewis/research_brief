from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    data = tmp_path / "state"
    data.mkdir()
    monkeypatch.setenv("DATA_DIR", str(data))

    from app.config import get_settings

    get_settings.cache_clear()

    from app.db import Base

    engine = create_engine(
        f"sqlite:///{data / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    yield session
    session.close()
    engine.dispose()
    get_settings.cache_clear()


@pytest.fixture
def vault_path(tmp_path) -> Path:
    path = tmp_path / "vault"
    path.mkdir()
    return path
