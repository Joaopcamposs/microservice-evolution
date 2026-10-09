"""Modelos ORM das tabelas e conversão de/para os agregados de domínio.

São detalhe de persistência: o domínio não os conhece. Constraints espelham as
invariantes dos agregados como defesa em profundidade.
"""

from typing import Self
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.ids import new_id
from app.domain.product import Product
from app.domain.sale import Sale, SaleItem, SaleStatus
from app.domain.user import User
from app.infrastructure.db.base import Model


class UserModel(Model):
    """Tabela `users`."""

    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(255), unique=True)

    @classmethod
    def from_domain(cls, user: User) -> Self:
        """Cria a linha a partir de um usuário novo."""
        return cls(id=user.id, name=user.name, email=user.email)

    def to_domain(self) -> User:
        """Reconstitui o agregado."""
        return User(id=self.id, name=self.name, email=self.email)


class ProductModel(Model):
    """Tabela `products`; preço em centavos."""

    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("price_cents > 0", name="ck_products_price_positive"),
        CheckConstraint("stock >= 0", name="ck_products_stock_non_negative"),
    )

    name: Mapped[str] = mapped_column(String(200))
    price_cents: Mapped[int]
    stock: Mapped[int]
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))

    @classmethod
    def from_domain(cls, product: Product) -> Self:
        """Cria a linha a partir de um produto novo."""
        return cls(
            id=product.id,
            name=product.name,
            price_cents=product.price_cents,
            stock=product.stock,
            created_by=product.created_by,
        )

    def to_domain(self) -> Product:
        """Reconstitui o agregado."""
        return Product(
            id=self.id,
            name=self.name,
            price_cents=self.price_cents,
            stock=self.stock,
            created_by=self.created_by,
        )


class SaleItemModel(Model):
    """Tabela `sale_items`; guarda o preço unitário no momento da compra."""

    __tablename__ = "sale_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_sale_items_quantity_positive"),
        CheckConstraint("unit_price_cents > 0", name="ck_sale_items_price_positive"),
    )

    sale_id: Mapped[UUID] = mapped_column(ForeignKey("sales.id"))
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int]
    unit_price_cents: Mapped[int]


class SaleModel(Model):
    """Tabela `sales`; `total_cents` é derivado do agregado na gravação."""

    __tablename__ = "sales"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    total_cents: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[SaleStatus] = mapped_column(Enum(SaleStatus, native_enum=False, length=20))
    items: Mapped[list[SaleItemModel]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", order_by="SaleItemModel.id"
    )

    @classmethod
    def from_domain(cls, sale: Sale) -> Self:
        """Cria a linha (com itens) a partir de uma venda nova."""
        return cls(
            id=sale.id,
            user_id=sale.user_id,
            total_cents=sale.total_cents,
            status=sale.status,
            items=[
                SaleItemModel(
                    id=new_id(),
                    product_id=i.product_id,
                    quantity=i.quantity,
                    unit_price_cents=i.unit_price_cents,
                )
                for i in sale.items
            ],
        )

    def to_domain(self) -> Sale:
        """Reconstitui o agregado com seus itens."""
        return Sale(
            id=self.id,
            user_id=self.user_id,
            status=self.status,
            items=[SaleItem(i.product_id, i.quantity, i.unit_price_cents) for i in self.items],
        )
