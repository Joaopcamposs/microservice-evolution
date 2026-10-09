"""Agregado `Sale`: venda com itens e ciclo de vida PENDING -> PAID -> COMPLETED.

A venda falha em PENDING -> PAYMENT_FAILED. Itens são imutáveis depois de criados.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Self
from uuid import UUID

from app.domain.base import Entity
from app.domain.errors import InvalidSaleTransitionError, InvalidValueError


class SaleStatus(StrEnum):
    """Estados possíveis de uma venda."""

    PENDING = "PENDING"
    PAID = "PAID"
    COMPLETED = "COMPLETED"
    PAYMENT_FAILED = "PAYMENT_FAILED"


@dataclass(frozen=True, slots=True)
class SaleItem:
    """Item da venda com o preço unitário congelado no momento da compra."""

    product_id: UUID
    quantity: int
    unit_price_cents: int


@dataclass(slots=True, eq=False, kw_only=True)
class Sale(Entity):
    """Raiz do agregado: comprador, itens e status; o total é derivado dos itens."""

    user_id: UUID
    status: SaleStatus
    items: list[SaleItem]

    @property
    def total_cents(self) -> int:
        """Soma quantidade x preço unitário de todos os itens, em centavos."""
        return sum(i.quantity * i.unit_price_cents for i in self.items)

    @classmethod
    def place(cls, user_id: UUID, items: list[SaleItem]) -> Self:
        """Abre uma venda PENDING; exige itens, quantidades positivas e produtos distintos."""
        if not items:
            raise InvalidValueError("venda sem itens")
        if any(i.quantity <= 0 or i.unit_price_cents <= 0 for i in items):
            raise InvalidValueError("quantidade e preço devem ser positivos")
        if len({i.product_id for i in items}) != len(items):
            raise InvalidValueError("produto repetido nos itens")
        return cls(user_id=user_id, status=SaleStatus.PENDING, items=list(items))

    def mark_paid(self) -> None:
        """Registra cobrança aprovada (só a partir de PENDING)."""
        self._transition(SaleStatus.PENDING, SaleStatus.PAID)

    def mark_payment_failed(self) -> None:
        """Registra cobrança recusada (só a partir de PENDING)."""
        self._transition(SaleStatus.PENDING, SaleStatus.PAYMENT_FAILED)

    def complete(self) -> None:
        """Conclui a venda após a notificação (só a partir de PAID)."""
        self._transition(SaleStatus.PAID, SaleStatus.COMPLETED)

    def _transition(self, expected: SaleStatus, new: SaleStatus) -> None:
        """Aplica `new` se o status atual for `expected`; senão rejeita."""
        if self.status is not expected:
            raise InvalidSaleTransitionError(f"{self.status} -> {new} não permitido")
        self.status = new
