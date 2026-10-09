"""Agregado `Product`: catálogo com controle de estoque."""

from dataclasses import dataclass
from typing import Self
from uuid import UUID

from app.domain.base import Entity
from app.domain.errors import InsufficientStockError, InvalidValueError


@dataclass(slots=True, eq=False, kw_only=True)
class Product(Entity):
    """Produto com preço em centavos, estoque não negativo e o usuário que o cadastrou."""

    name: str
    price_cents: int
    stock: int
    created_by: UUID

    @classmethod
    def create(cls, name: str, price_cents: int, stock: int, created_by: UUID) -> Self:
        """Cria um produto validando nome, preço positivo e estoque não negativo."""
        if not name.strip():
            raise InvalidValueError("nome obrigatório")
        if price_cents <= 0:
            raise InvalidValueError("preço deve ser positivo")
        if stock < 0:
            raise InvalidValueError("estoque não pode ser negativo")
        return cls(name=name.strip(), price_cents=price_cents, stock=stock, created_by=created_by)

    def reserve(self, quantity: int) -> None:
        """Baixa `quantity` do estoque; falha sem alterar nada se não houver o bastante."""
        if quantity <= 0:
            raise InvalidValueError("quantidade deve ser positiva")
        if self.stock < quantity:
            raise InsufficientStockError(self.id)
        self.stock -= quantity

    def restore(self, quantity: int) -> None:
        """Devolve `quantity` ao estoque (venda cancelada)."""
        if quantity <= 0:
            raise InvalidValueError("quantidade deve ser positiva")
        self.stock += quantity
