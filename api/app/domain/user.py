"""Agregado `User`: quem compra e quem cadastra produtos."""

import re
from dataclasses import dataclass
from typing import Self

from app.domain.base import Entity
from app.domain.errors import InvalidValueError

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(slots=True, eq=False, kw_only=True)
class User(Entity):
    """Usuário com nome e e-mail válidos; o e-mail é único (garantido pelo repositório)."""

    name: str
    email: str

    @classmethod
    def register(cls, name: str, email: str) -> Self:
        """Cria um usuário novo validando nome e e-mail."""
        if not name.strip():
            raise InvalidValueError("nome obrigatório")
        if not _EMAIL.match(email):
            raise InvalidValueError("e-mail inválido")
        return cls(name=name.strip(), email=email.lower())
