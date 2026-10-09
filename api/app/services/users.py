"""Caso de uso de escrita: cadastro de usuário."""

from collections.abc import Callable
from uuid import UUID

from app.domain.errors import EmailAlreadyRegisteredError
from app.domain.repositories import UnitOfWork
from app.domain.user import User
from app.schemas import UserIn


class UserService:
    """Cadastra usuários garantindo e-mail único."""

    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        """Recebe a fábrica de unidades de trabalho (uma por operação)."""
        self._uow_factory = uow_factory

    async def register_user(self, data: UserIn) -> UUID:
        """Valida e persiste um usuário novo; devolve o id."""
        user = User.register(data.name, data.email)
        async with self._uow_factory() as uow:
            if await uow.users.get_by_email(user.email) is not None:
                raise EmailAlreadyRegisteredError(user.email)
            await uow.users.add(user)
            return user.id
