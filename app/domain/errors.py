"""Erros de regra de negócio; `app/routers/errors.py` traduz cada um para HTTP."""

from dataclasses import dataclass
from uuid import UUID

from app.domain.status import OrderStatus


class DomainError(Exception):
    """Base dos erros de regra de negócio."""


@dataclass(eq=False)
class UserNotFound(DomainError):
    """O usuário do pedido não existe."""

    def __str__(self) -> str:
        """Mensagem devolvida ao cliente."""
        return "usuário não encontrado"


@dataclass(eq=False)
class OrderNotFound(DomainError):
    """O pedido não existe."""

    def __str__(self) -> str:
        """Mensagem devolvida ao cliente."""
        return "pedido não encontrado"


@dataclass(eq=False)
class EmailAlreadyExists(DomainError):
    """Já existe usuário com esse e-mail."""

    def __str__(self) -> str:
        """Mensagem devolvida ao cliente."""
        return "e-mail já cadastrado"


@dataclass(eq=False)
class ProductsNotFound(DomainError):
    """O pedido cita produtos que não existem."""

    product_ids: list[UUID]

    def __str__(self) -> str:
        """Mensagem devolvida ao cliente, com os ids."""
        return f"produtos não encontrados: {[str(p) for p in self.product_ids]}"


@dataclass(eq=False)
class InsufficientStock(DomainError):
    """Algum produto não tem estoque para a quantidade pedida."""

    product_ids: list[UUID]

    def __str__(self) -> str:
        """Mensagem devolvida ao cliente, com os ids."""
        return f"estoque insuficiente: {[str(p) for p in self.product_ids]}"


@dataclass(eq=False)
class InvalidTransition(DomainError):
    """O pedido não pode ir do estado atual para o destino pedido."""

    current: OrderStatus
    target: OrderStatus

    def __str__(self) -> str:
        """Mensagem devolvida ao cliente, com os estados possíveis."""
        allowed = sorted(s.value for s in self.current.next_states)
        return f"{self.current} → {self.target} não permitido; possíveis: {allowed}"
