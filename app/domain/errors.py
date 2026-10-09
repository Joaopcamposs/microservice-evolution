"""Erros de regra de negócio levantados pelos agregados; quem chama traduz para HTTP."""

from uuid import UUID

from app.domain.status import OrderStatus


class DomainError(Exception):
    """Base dos erros de regra de negócio."""


class InsufficientStock(DomainError):
    """Algum produto não tem estoque para a quantidade pedida."""

    def __init__(self, product_ids: list[UUID]) -> None:
        """Guarda os produtos sem estoque suficiente."""
        super().__init__(f"estoque insuficiente: {[str(p) for p in product_ids]}")
        self.product_ids = product_ids


class InvalidTransition(DomainError):
    """O pedido não pode ir do estado atual para o destino pedido."""

    def __init__(self, current: OrderStatus, target: OrderStatus) -> None:
        """Monta a mensagem com o estado atual, o destino e os possíveis."""
        allowed = sorted(s.value for s in current.next_states)
        super().__init__(f"{current} → {target} não permitido; possíveis: {allowed}")
