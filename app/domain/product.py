"""Agregado `Product`: preço e estoque, com a regra de reserva."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from uuid_utils.compat import uuid7


@dataclass(eq=False, kw_only=True)
class Product:
    """Produto do catálogo; o estoque nunca fica negativo. Só nasce por `create`."""

    id: UUID = field(default_factory=uuid7)
    name: str
    price_cents: int
    stock: int
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(cls, name: str, price_cents: int, stock: int = 0) -> "Product":
        """Cria o produto com nome aparado; `ValueError` se preço <= 0 ou estoque < 0."""
        if price_cents <= 0:
            raise ValueError("price_cents deve ser positivo")
        if stock < 0:
            raise ValueError("stock não pode ser negativo")
        return cls(name=name.strip(), price_cents=price_cents, stock=stock)

    def has_stock(self, quantity: int) -> bool:
        """Diz se há estoque para `quantity` unidades."""
        return self.stock >= quantity

    def reserve(self, quantity: int) -> None:
        """Tira `quantity` unidades do estoque; `ValueError` se não houver (checar `has_stock`)."""
        if not self.has_stock(quantity):
            raise ValueError(f"estoque insuficiente no produto {self.id}")
        self.stock -= quantity
