"""Sessões separadas de escrita e leitura e o repositório abstrato que as recebe.

`WriteSession` e `ReadSession` são subclasses distintas de `AsyncSession`: o type
checker impede injetar uma no lugar da outra. Cada uma tem sua fábrica/engine, o que
permite apontar a leitura para uma réplica (`DATABASE_READ_URL`) sem mudar código.
"""

from abc import ABC

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class WriteSession(AsyncSession):
    """Sessão transacional do banco primário, usada pelos repositórios de escrita."""


class ReadSession(AsyncSession):
    """Sessão de consulta (AUTOCOMMIT, sem transação), usada pelos repositórios de leitura."""


class BaseRepository[S: AsyncSession](ABC):  # noqa: B024  (abstrata por intenção: só estado comum)
    """Base abstrata dos repositórios: guarda a sessão recebida; não é instanciada diretamente."""

    def __init__(self, session: S) -> None:
        """Recebe a sessão (de escrita ou de leitura, conforme a subclasse)."""
        self._session = session


def create_write_engine(url: str) -> AsyncEngine:
    """Engine do banco primário (escrita)."""
    return create_async_engine(url)


def create_read_engine(url: str) -> AsyncEngine:
    """Engine de leitura em AUTOCOMMIT: cada consulta sem transação aberta."""
    return create_async_engine(url, isolation_level="AUTOCOMMIT")


def create_write_session_factory(engine: AsyncEngine) -> async_sessionmaker[WriteSession]:
    """Fábrica de sessões de escrita."""
    return async_sessionmaker(engine, class_=WriteSession, expire_on_commit=False)


def create_read_session_factory(engine: AsyncEngine) -> async_sessionmaker[ReadSession]:
    """Fábrica de sessões de leitura."""
    return async_sessionmaker(engine, class_=ReadSession, expire_on_commit=False)
