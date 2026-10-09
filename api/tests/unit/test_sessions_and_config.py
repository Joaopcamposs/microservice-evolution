"""Sessões de leitura/escrita distintas, repositório base e fallback da URL de leitura."""

from unittest.mock import Mock

from app.config import Settings
from app.infrastructure.db.read_repositories import SaleReadRepository
from app.infrastructure.db.sessions import BaseRepository, ReadSession, WriteSession
from app.infrastructure.db.write_repositories import SqlSaleWriteRepository


def test_read_and_write_sessions_are_distinct_types():
    assert not issubclass(ReadSession, WriteSession)
    assert not issubclass(WriteSession, ReadSession)


def test_repositories_share_the_base_and_keep_their_session():
    read_session, write_session = Mock(spec=ReadSession), Mock(spec=WriteSession)
    reader, writer = SaleReadRepository(read_session), SqlSaleWriteRepository(write_session)
    assert isinstance(reader, BaseRepository) and isinstance(writer, BaseRepository)
    assert reader._session is read_session
    assert writer._session is write_session


def test_read_url_falls_back_to_primary():
    assert Settings(database_url="a").read_url == "a"
    assert Settings(database_url="a", database_read_url="b").read_url == "b"
