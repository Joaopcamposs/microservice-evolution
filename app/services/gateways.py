"""Contratos (Protocols) das integrações externas e injeção delas nas rotas.

Os handlers dependem só destes contratos; hoje a implementação é a fake (`fakes.py`), e trocar
por um provedor real, ou por um stub nos testes, não muda os handlers.
"""

import os
from typing import Annotated, Protocol
from uuid import UUID

from fastapi import Depends

from app.services.fakes import FakeEmailSender, FakePaymentGateway


class PaymentGateway(Protocol):
    """Contrato de um serviço de cobrança."""

    async def charge(self, order_id: UUID, amount_cents: int) -> bool:
        """Cobra o pedido; `True` se aprovado, `False` se recusado."""
        ...


class EmailSender(Protocol):
    """Contrato de um serviço de e-mail transacional."""

    async def send(self, order_id: UUID, to: str, status: str) -> bool:
        """Envia o e-mail da mudança de status; `True` se enviado, `False` se falhou."""
        ...


# Configuração por env (latência média em ms e taxa de falha de 0 a 1).
_payment = FakePaymentGateway(
    int(os.getenv("CHARGE_LATENCY_MS", "600")), float(os.getenv("CHARGE_FAILURE_RATE", "0.1"))
)
_email = FakeEmailSender(
    int(os.getenv("EMAIL_LATENCY_MS", "200")), float(os.getenv("EMAIL_FAILURE_RATE", "0.05"))
)


def get_payment_gateway() -> PaymentGateway:
    """Dependência FastAPI: o serviço de cobrança em uso."""
    return _payment


def get_email_sender() -> EmailSender:
    """Dependência FastAPI: o serviço de e-mail em uso."""
    return _email


PaymentDep = Annotated[PaymentGateway, Depends(get_payment_gateway)]
EmailDep = Annotated[EmailSender, Depends(get_email_sender)]
