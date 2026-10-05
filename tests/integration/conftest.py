from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from tests.fakes import CountingTransformer
from transform_cache.config import Settings
from transform_cache.db import create_engine, create_session_factory, init_db
from transform_cache.main import create_app


@pytest.fixture
async def engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    # A file per test, not ":memory:": every pooled connection must see the
    # same database, as it does in production.
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await init_db(engine)
    yield engine
    await engine.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(engine)


@pytest.fixture
def transformer() -> CountingTransformer:
    return CountingTransformer()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(database_url=f"sqlite+aiosqlite:///{tmp_path / 'app.db'}")


@pytest.fixture
def client(
    settings: Settings, transformer: CountingTransformer
) -> Iterator[TestClient]:
    # The context manager runs the app's lifespan: tables, engine, service.
    with TestClient(create_app(settings, transformer)) as client:
        yield client
