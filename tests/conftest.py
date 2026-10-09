"""Fixtures: cliente HTTP com Postgres de testes (compose separado), tabelas novas por teste."""

import os
from collections.abc import AsyncGenerator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infra.database import Base, get_read_session, get_write_session
from app.main import app
from app.services import fakes

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5433/app_test"
)


@pytest.fixture(autouse=True)
def deterministic_fakes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cobrança e e-mail fakes sem latência e sem falha; cada teste liga o que quiser testar."""
    monkeypatch.setattr(fakes, "CHARGE_LATENCY_MS", 0)
    monkeypatch.setattr(fakes, "EMAIL_LATENCY_MS", 0)
    monkeypatch.setattr(fakes, "CHARGE_FAILURE_RATE", 0.0)
    monkeypatch.setattr(fakes, "EMAIL_FAILURE_RATE", 0.0)


@pytest.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient]:
    """Cliente HTTP ligado ao Postgres de testes; recria as tabelas e troca a sessão de produção."""
    engine = create_async_engine(TEST_DATABASE_URL, pool_size=10)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override() -> AsyncGenerator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_write_session] = override
    app.dependency_overrides[get_read_session] = override
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c
    app.dependency_overrides.clear()
    await engine.dispose()
