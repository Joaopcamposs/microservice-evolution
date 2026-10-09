"""Repositórios de pedido: `OrderReader` só lê, `OrderWriter` grava e trava o pedido."""

from uuid import UUID

from sqlalchemy import select

from app.domain.order import Order
from app.domain.product import Product
from app.domain.user import User
from app.repository.base import Repository
from app.repository.orm.tables import orders
from app.repository.products import ProductWriter
from app.repository.users import UserReader


class OrderReader(Repository):
    """Consultas de pedido, sem efeito colateral."""

    async def list(
        self, order_id: UUID | None, user_id: UUID | None, limit: int, offset: int
    ) -> list[Order]:
        """Lista pedidos, mais recentes primeiro; `order_id` e `user_id` opcionais filtram."""
        stmt = select(Order).order_by(orders.c.id.desc()).limit(limit).offset(offset)
        if order_id is not None:
            stmt = stmt.where(orders.c.id == order_id)
        if user_id is not None:
            stmt = stmt.where(orders.c.user_id == user_id)
        return list(await self.session.scalars(stmt))


class OrderWriter(Repository):
    """Gravações de pedido; o commit é de quem chama."""

    async def load_placement(
        self, user_id: UUID, product_ids: list[UUID]
    ) -> tuple[User | None, dict[UUID, Product]]:
        """Busca o que a criação do pedido precisa: o usuário e os produtos (travados).

        Ausentes ficam de fora (`None` / fora do dict); quem decide é o agregado e o handler.
        """
        user = await UserReader(self.session).get(user_id)
        products = await ProductWriter(self.session).get_for_update(product_ids)
        return user, products

    def add(self, order: Order) -> None:
        """Registra o pedido (com itens e histórico) na sessão."""
        self.session.add(order)

    async def load_for_update(self, order_id: UUID) -> tuple[Order, User] | None:
        """Busca o pedido travando a linha (`FOR UPDATE`) até o fim da transação, e seu usuário.

        `None` se o pedido não existe.
        """
        order = await self.session.get(Order, order_id, with_for_update=True)
        if order is None:
            return None
        user = await UserReader(self.session).get(order.user_id)
        assert user is not None  # FK garante
        return order, user
