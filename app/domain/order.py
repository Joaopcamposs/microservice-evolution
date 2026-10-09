"""Agregado `Order`: itens, estado e histórico, com a regra de montagem e de transição."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from uuid_utils.compat import uuid7

from app.domain.errors import InsufficientStock, InvalidTransition, ProductsNotFound
from app.domain.product import Product
from app.domain.schemas import OrderItemCreate
from app.domain.status import OrderStatus


@dataclass(eq=False, kw_only=True)
class OrderItem:
    """Item de um pedido; guarda o preço unitário do momento da compra."""

    id: UUID = field(default_factory=uuid7)
    product_id: UUID
    quantity: int
    unit_price_cents: int


@dataclass(eq=False, kw_only=True)
class OrderStatusChange:
    """Entrada do histórico; `notified_at` vazio = e-mail pendente ou falhou."""

    id: UUID = field(default_factory=uuid7)
    status: OrderStatus
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    notified_at: datetime | None = None


@dataclass(eq=False, kw_only=True)
class Order:
    """Pedido de um usuário. Nasce por `place` e só muda de estado por `move_to`."""

    id: UUID = field(default_factory=uuid7)
    user_id: UUID
    status: OrderStatus = OrderStatus.RECEIVED
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    items: list[OrderItem] = field(default_factory=list)
    history: list[OrderStatusChange] = field(default_factory=list)

    @classmethod
    def place(
        cls, user_id: UUID, items: list[OrderItemCreate], products: dict[UUID, Product]
    ) -> "Order":
        """Monta o pedido (`RECEIVED`) e reserva o estoque de cada produto.

        `items` são os itens pedidos; `products` são os produtos já carregados.
        Levanta `ProductsNotFound` se algum não estiver em `products` e `InsufficientStock`
        com todos os faltantes, sem reservar nada. O preço do item é copiado do produto.
        """
        missing = [i.product_id for i in items if i.product_id not in products]
        if missing:
            raise ProductsNotFound(sorted(missing))
        lines = [(products[i.product_id], i.quantity) for i in items]
        short = [p.id for p, quantity in lines if not p.has_stock(quantity)]
        if short:
            raise InsufficientStock(short)
        for product, quantity in lines:
            product.reserve(quantity)
        return cls(
            user_id=user_id,
            history=[OrderStatusChange(status=OrderStatus.RECEIVED)],
            items=[
                OrderItem(product_id=p.id, quantity=q, unit_price_cents=p.price_cents)
                for p, q in lines
            ],
        )

    @property
    def total_cents(self) -> int:
        """Soma quantidade x preço unitário dos itens."""
        return sum(i.quantity * i.unit_price_cents for i in self.items)

    def move_to(self, target: OrderStatus) -> None:
        """Muda o estado e registra no histórico; `InvalidTransition` se não for permitido."""
        if not self.status.can_transition_to(target):
            raise InvalidTransition(self.status, target)
        self.status = target
        self.history.append(OrderStatusChange(status=target))

    def begin_payment(self) -> None:
        """Passa para `AWAITING_PAYMENT`, o estado enquanto a cobrança roda."""
        self.move_to(OrderStatus.AWAITING_PAYMENT)

    def settle_payment(self, approved: bool) -> None:
        """Aplica o resultado da cobrança: `PAID` se aprovada, senão `PAYMENT_FAILED`."""
        self.move_to(OrderStatus.PAID if approved else OrderStatus.PAYMENT_FAILED)

    @property
    def releases_stock(self) -> bool:
        """Diz se o estoque dos itens deve voltar (pedido com cobrança recusada)."""
        return self.status is OrderStatus.PAYMENT_FAILED

    def mark_notified(self) -> None:
        """Marca o e-mail do estado atual como enviado."""
        self.history[-1].notified_at = datetime.now(UTC)
