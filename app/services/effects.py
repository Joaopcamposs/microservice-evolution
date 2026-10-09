"""Efeitos externos de um pedido (cobrança e e-mail), fora do agregado e da transação.

Hoje o handler chama aqui direto; a ideia é virarem handlers de eventos do pedido.
"""

from typing import Annotated

from fastapi import Depends

from app.domain.order import Order
from app.domain.user import User
from app.services.gateways import EmailDep, EmailSender, PaymentDep, PaymentGateway


class OrderEffects:
    """Dispara cobrança e e-mail de um pedido nas integrações injetadas."""

    def __init__(self, payment: PaymentGateway, email: EmailSender) -> None:
        """Guarda as integrações usadas."""
        self.payment = payment
        self.email = email

    async def charge(self, order: Order) -> bool:
        """Cobra o total do pedido; `True` se aprovado."""
        return await self.payment.charge(order.id, order.total_cents)

    async def notify(self, order: Order, user: User) -> None:
        """Envia o e-mail do estado atual; só marca `notified_at` se o envio der certo."""
        if await self.email.send(order.id, user.email, order.status):
            order.mark_notified()


def get_order_effects(payment: PaymentDep, email: EmailDep) -> OrderEffects:
    """Dependência FastAPI: efeitos montados com as integrações em uso."""
    return OrderEffects(payment, email)


EffectsDep = Annotated[OrderEffects, Depends(get_order_effects)]
