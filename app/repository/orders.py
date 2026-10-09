"""Repositórios de pedido: `OrderReader` só lê, `OrderWriter` grava e trava o pedido."""

from uuid import UUID

from sqlalchemy import select

from app.domain.order import Order
from app.repository.base import Repository
from app.repository.orm.tables import orders


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

    def add(self, order: Order) -> None:
        """Registra o pedido (com itens e histórico) na sessão."""
        self.session.add(order)

    async def get_for_update(self, order_id: UUID) -> Order | None:
        """Busca o pedido travando a linha (`FOR UPDATE`) até o fim da transação."""
        return await self.session.get(Order, order_id, with_for_update=True)
