"""Estados do pedido."""

import enum


class OrderStatus(enum.StrEnum):
    """Ciclo do pedido: PENDING → PAID → COMPLETED, ou PENDING → PAYMENT_FAILED."""

    PENDING = "PENDING"
    PAID = "PAID"
    COMPLETED = "COMPLETED"
    PAYMENT_FAILED = "PAYMENT_FAILED"
