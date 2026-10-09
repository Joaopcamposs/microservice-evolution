"""Gateway de cobrança fake.

Simula um provedor externo lento e instável. Fica atrás de um `Protocol` para que
a regra de venda não dependa da implementação (e possa ir para um worker depois).
"""

import asyncio
import random
from typing import Protocol
from uuid import UUID

from app.config import Settings


class PaymentGateway(Protocol):
    """Contrato de cobrança: devolve se o pagamento foi aprovado."""

    async def charge(self, sale_id: UUID, amount_cents: int) -> bool:
        """Cobra `amount_cents` da venda; `True` se aprovado, `False` se recusado."""
        ...


class FakePaymentGateway:
    """Cobrança simulada com latência aleatória e taxa de recusa configuráveis."""

    def __init__(self, settings: Settings) -> None:
        """Guarda os parâmetros de latência e falha vindos da configuração."""
        self._min_ms = settings.payment_latency_min_ms
        self._max_ms = settings.payment_latency_max_ms
        self._failure_rate = settings.payment_failure_rate

    async def charge(self, sale_id: UUID, amount_cents: int) -> bool:
        """Espera a latência simulada e recusa com probabilidade `failure_rate`."""
        await asyncio.sleep(random.uniform(self._min_ms, self._max_ms) / 1000)
        return random.random() >= self._failure_rate
