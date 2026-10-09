"""Fixtures de integração: banco `sales_test` isolado, tabelas recriadas por teste via ORM."""

import asyncio
from collections.abc import AsyncGenerator

import asyncpg
import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import Settings
from app.infrastructure.db.base import Base
from app.infrastructure.db.schema import create_tables
from app.main import create_app

ADMIN_URL = "postgresql://sales:sales@localhost:5432/postgres"
TEST_URL = "postgresql+asyncpg://sales:sales@localhost:5432/sales_test"


async def _recreate_database() -> None:
    """Recria o banco de testes vazio."""
    admin = await asyncpg.connect(ADMIN_URL)
    await admin.execute("DROP DATABASE IF EXISTS sales_test")
    await admin.execute("CREATE DATABASE sales_test")
    await admin.close()


@pytest.fixture(scope="session", autouse=True)
def database() -> None:
    """Prepara o banco de testes uma vez por sessão."""
    asyncio.run(_recreate_database())


async def _reset_tables(engine: AsyncEngine) -> None:
    """Derruba e recria as tabelas para isolar cada teste."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await create_tables(engine)


async def _client(failure_rate: float) -> AsyncGenerator[httpx.AsyncClient]:
    """Sobe a app sem latência e com taxa de falha de cobrança fixa (0 ou 1)."""
    settings = Settings(
        database_url=TEST_URL,
        payment_latency_min_ms=0,
        payment_latency_max_ms=0,
        payment_failure_rate=failure_rate,
        email_latency_min_ms=0,
        email_latency_max_ms=0,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        await _reset_tables(app.state.write_engine)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient]:
    """Cliente HTTP com cobrança sempre aprovada."""
    async for c in _client(failure_rate=0.0):
        yield c


@pytest.fixture
async def failing_client() -> AsyncGenerator[httpx.AsyncClient]:
    """Cliente HTTP com cobrança sempre recusada."""
    async for c in _client(failure_rate=1.0):
        yield c
