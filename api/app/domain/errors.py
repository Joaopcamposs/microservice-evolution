"""Erros de domínio; a camada HTTP os traduz em status codes."""

from uuid import UUID


class DomainError(Exception):
    """Base de toda violação de regra de negócio."""


class InvalidValueError(DomainError):
    """Dado que viola uma invariante de um agregado (ex.: e-mail malformado)."""


class InsufficientStockError(DomainError):
    """Estoque menor que a quantidade pedida."""

    def __init__(self, product_id: UUID) -> None:
        """Guarda o produto sem estoque suficiente."""
        super().__init__(f"estoque insuficiente para o produto {product_id}")
        self.product_id = product_id


class InvalidSaleTransitionError(DomainError):
    """Mudança de status de venda não permitida pelo ciclo de vida."""


class UserNotFoundError(DomainError):
    """Usuário inexistente."""


class ProductNotFoundError(DomainError):
    """Produto inexistente."""


class EmailAlreadyRegisteredError(DomainError):
    """Já existe usuário com esse e-mail."""
