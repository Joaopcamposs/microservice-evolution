"""Estados do pedido e as transições permitidas entre eles."""

import enum


class OrderStatus(enum.StrEnum):
    """Estado do pedido; `can_transition_to` diz se o próximo estado é válido.

    RECEIVED → AWAITING_PAYMENT → PAID → AWAITING_SHIPMENT → SHIPPED → DELIVERED → COMPLETED,
    com AWAITING_PAYMENT → PAYMENT_FAILED como desvio. COMPLETED e PAYMENT_FAILED são finais.
    """

    RECEIVED = "RECEIVED"
    AWAITING_PAYMENT = "AWAITING_PAYMENT"
    PAID = "PAID"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    AWAITING_SHIPMENT = "AWAITING_SHIPMENT"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    COMPLETED = "COMPLETED"

    @property
    def next_states(self) -> frozenset["OrderStatus"]:
        """Estados para onde o pedido pode ir a partir deste (vazio nos finais)."""
        return _TRANSITIONS[self]

    def can_transition_to(self, target: "OrderStatus") -> bool:
        """Diz se a transição deste estado para `target` é permitida."""
        return target in self.next_states


_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.RECEIVED: frozenset({OrderStatus.AWAITING_PAYMENT}),
    OrderStatus.AWAITING_PAYMENT: frozenset({OrderStatus.PAID, OrderStatus.PAYMENT_FAILED}),
    OrderStatus.PAID: frozenset({OrderStatus.AWAITING_SHIPMENT}),
    OrderStatus.PAYMENT_FAILED: frozenset(),
    OrderStatus.AWAITING_SHIPMENT: frozenset({OrderStatus.SHIPPED}),
    OrderStatus.SHIPPED: frozenset({OrderStatus.DELIVERED}),
    OrderStatus.DELIVERED: frozenset({OrderStatus.COMPLETED}),
    OrderStatus.COMPLETED: frozenset(),
}
