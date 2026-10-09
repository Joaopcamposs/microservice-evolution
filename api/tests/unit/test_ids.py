"""Identificadores: UUID v7 gerado no domínio."""

from app.domain.ids import new_id
from app.domain.user import User


def test_new_id_is_uuid7():
    assert new_id().version == 7


def test_ids_are_unique_and_time_ordered_across_milliseconds():
    import time

    first = new_id()
    time.sleep(0.005)
    assert new_id() > first


def test_entity_gets_id_on_creation():
    assert User.register("Ana", "a@b.com").id.version == 7
