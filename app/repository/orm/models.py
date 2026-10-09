"""Modelos ORM (tabelas). Ids são UUID v7 gerados na aplicação; dinheiro em centavos."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid_utils.compat import uuid7

from app.infra.database import Base


class User(Base):
    """Usuário que faz pedidos; o e-mail é único e a senha fica só como hash."""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Product(Base):
    """Produto do catálogo."""

    __tablename__ = "products"
    __table_args__ = (CheckConstraint("price_cents > 0"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(200))
    price_cents: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OrderItem(Base):
    """Item de um pedido; guarda o preço unitário do momento da compra."""

    __tablename__ = "order_items"
    __table_args__ = (CheckConstraint("quantity > 0"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id"), index=True)
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int]
    unit_price_cents: Mapped[int]


class Order(Base):
    """Pedido de um usuário com seus itens."""

    __tablename__ = "orders"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    items: Mapped[list[OrderItem]] = relationship(lazy="selectin", order_by=OrderItem.id)

    @property
    def total_cents(self) -> int:
        """Soma quantidade x preço unitário dos itens."""
        return sum(i.quantity * i.unit_price_cents for i in self.items)
