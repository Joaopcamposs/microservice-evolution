"""Caso de uso de escrita: cadastro de produto."""

from collections.abc import Callable
from uuid import UUID

from app.domain.errors import UserNotFoundError
from app.domain.product import Product
from app.domain.repositories import UnitOfWork
from app.schemas import ProductIn


class ProductService:
    """Cadastra produtos em nome de um usuário."""

    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        """Recebe a fábrica de unidades de trabalho (uma por operação)."""
        self._uow_factory = uow_factory

    async def create_product(self, user_id: UUID, data: ProductIn) -> UUID:
        """Persiste um produto novo cadastrado por `user_id`; devolve o id."""
        async with self._uow_factory() as uow:
            if await uow.users.get(user_id) is None:
                raise UserNotFoundError(user_id)
            product = Product.create(data.name, data.price_cents, data.stock, user_id)
            await uow.products.add(product)
            return product.id
