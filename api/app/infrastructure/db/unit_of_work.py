"""Unidade de trabalho SQLAlchemy: uma sessão/transação por operação de negócio."""

from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.infrastructure.db.sessions import WriteSession
from app.infrastructure.db.write_repositories import (
    SqlProductWriteRepository,
    SqlSaleWriteRepository,
    SqlUserWriteRepository,
)


class SqlAlchemyUnitOfWork:
    """Abre sessão e transação ao entrar; commit sem erro, rollback com erro."""

    users: SqlUserWriteRepository
    products: SqlProductWriteRepository
    sales: SqlSaleWriteRepository

    def __init__(self, session_factory: async_sessionmaker[WriteSession]) -> None:
        """Guarda a fábrica de sessões; a sessão em si só existe dentro do `async with`."""
        self._session_factory = session_factory
        self._session: WriteSession | None = None

    async def __aenter__(self) -> Self:
        """Abre a sessão, inicia a transação e expõe os repositórios."""
        self._session = self._session_factory()
        await self._session.begin()
        self.users = SqlUserWriteRepository(self._session)
        self.products = SqlProductWriteRepository(self._session)
        self.sales = SqlSaleWriteRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Confirma ou desfaz a transação e fecha a sessão."""
        assert self._session is not None
        try:
            if exc_type is None:
                await self._session.commit()
            else:
                await self._session.rollback()
        finally:
            await self._session.close()
