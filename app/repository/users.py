"""Repositórios de usuário: `UserReader` só lê, `UserWriter` grava."""

from uuid import UUID

from sqlalchemy import select

from app.repository.base import Repository
from app.repository.orm.models import User


class UserReader(Repository):
    """Consultas de usuário, sem efeito colateral."""

    async def get(self, user_id: UUID) -> User | None:
        """Busca um usuário pelo id; `None` se não existir."""
        return await self.session.get(User, user_id)

    async def list(self, user_id: UUID | None, limit: int, offset: int) -> list[User]:
        """Lista usuários, mais recentes primeiro (UUID v7 ordena por criação); `user_id` filtra."""
        stmt = select(User).order_by(User.id.desc()).limit(limit).offset(offset)
        if user_id is not None:
            stmt = stmt.where(User.id == user_id)
        return list(await self.session.scalars(stmt))


class UserWriter(Repository):
    """Gravações de usuário; o commit é de quem chama."""

    def add(self, name: str, email: str, password_hash: str) -> User:
        """Registra um novo usuário na sessão (vai ao banco no commit)."""
        user = User(name=name, email=email, password_hash=password_hash)
        self.session.add(user)
        return user
