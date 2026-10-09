"""Repositórios de usuário: `UserReader` só lê, `UserWriter` grava."""

from uuid import UUID

from sqlalchemy import select

from app.domain.user import User
from app.repository.base import Repository
from app.repository.orm.tables import users


class UserReader(Repository):
    """Consultas de usuário, sem efeito colateral."""

    async def get(self, user_id: UUID) -> User | None:
        """Busca um usuário pelo id; `None` se não existir."""
        return await self.session.get(User, user_id)

    async def list(self, user_id: UUID | None, limit: int, offset: int) -> list[User]:
        """Lista usuários, mais recentes primeiro (UUID v7 ordena por criação); `user_id` filtra."""
        stmt = select(User).order_by(users.c.id.desc()).limit(limit).offset(offset)
        if user_id is not None:
            stmt = stmt.where(users.c.id == user_id)
        return list(await self.session.scalars(stmt))


class UserWriter(Repository):
    """Gravações de usuário; o commit é de quem chama."""

    def add(self, user: User) -> None:
        """Registra o usuário na sessão (vai ao banco no commit)."""
        self.session.add(user)
