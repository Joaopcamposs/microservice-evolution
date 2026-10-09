"""Mapeamento imperativo: liga cada agregado de `app/domain` à sua tabela, sem tocar no domínio."""

from sqlalchemy.orm import registry, relationship

from app.domain.order import Order, OrderItem, OrderStatusChange
from app.domain.product import Product
from app.domain.user import User
from app.repository.orm import tables


class Mappers:
    """Registro dos mapeamentos; `start` é idempotente."""

    registry = registry(metadata=tables.metadata)

    @classmethod
    def start(cls) -> None:
        """Mapeia os agregados nas tabelas (uma vez por processo)."""
        if cls.registry.mappers:
            return
        cls.registry.map_imperatively(User, tables.users)
        cls.registry.map_imperatively(Product, tables.products)
        cls.registry.map_imperatively(OrderItem, tables.order_items)
        cls.registry.map_imperatively(OrderStatusChange, tables.order_status_history)
        cls.registry.map_imperatively(
            Order,
            tables.orders,
            properties={
                "items": relationship(OrderItem, lazy="selectin", order_by=tables.order_items.c.id),
                "history": relationship(
                    OrderStatusChange, lazy="selectin", order_by=tables.order_status_history.c.id
                ),
            },
        )
