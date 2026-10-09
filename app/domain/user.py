"""Agregado `User`: dados normalizados e senha sempre como hash."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from uuid_utils.compat import uuid7

from app.domain.security import PasswordHasher


@dataclass(eq=False, kw_only=True)
class User:
    """Usuário que faz pedidos. Só nasce por `register`, que normaliza e faz o hash."""

    id: UUID = field(default_factory=uuid7)
    name: str
    email: str
    password_hash: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def register(cls, name: str, email: str, password: str) -> "User":
        """Cria o usuário: nome sem espaços nas pontas, e-mail em minúsculas, senha em hash.

        O hash (scrypt) é CPU-bound; quem chama de código async usa `asyncio.to_thread`.
        """
        return cls(
            name=name.strip(),
            email=email.strip().lower(),
            password_hash=PasswordHasher.hash(password),
        )
