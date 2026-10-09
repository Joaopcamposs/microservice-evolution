"""Implementações fake de cobrança e e-mail: latência e taxa de falha configuráveis.

Simulam o trabalho lento e instável de serviços externos. Cada chamada vira um span OTel.
"""

import asyncio
import logging
import random
from uuid import UUID

from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# Variação da latência: ±40% em torno do valor configurado.
JITTER = 0.4


class BaseGateway:
    """Base das integrações fake: simulação de latência e falha compartilhada."""

    @staticmethod
    async def _simulate(latency_ms: int, failure_rate: float) -> bool:
        """Espera a latência (com variação) e devolve `True` se a chamada deu certo."""
        delay_ms = latency_ms * random.uniform(1 - JITTER, 1 + JITTER)
        await asyncio.sleep(delay_ms / 1000)
        return random.random() >= failure_rate


class FakePaymentGateway(BaseGateway):
    """Cobrança fake: espera `latency_ms` e recusa com probabilidade `failure_rate` (0 a 1).

    Idempotente por `order_id`: repetir a cobrança do mesmo pedido devolve o resultado da
    primeira, sem cobrar de novo (`charges` conta só as cobranças reais).
    """

    def __init__(self, latency_ms: int, failure_rate: float) -> None:
        """Define a latência média (ms) e a taxa de recusa."""
        self.latency_ms = latency_ms
        self.failure_rate = failure_rate
        self.charges = 0
        self._results: dict[UUID, bool] = {}

    async def charge(self, order_id: UUID, amount_cents: int) -> bool:
        """Cobra o cliente; `False` se recusada. `order_id` é a chave de idempotência."""
        if order_id in self._results:
            logger.info("cobrança repetida ignorada order_id=%s", order_id)
            return self._results[order_id]
        self.charges += 1
        with tracer.start_as_current_span("charge") as span:
            span.set_attribute("order.id", str(order_id))
            span.set_attribute("order.amount_cents", amount_cents)
            logger.info("cobrança iniciada order_id=%s valor_cents=%d", order_id, amount_cents)
            approved = await self._simulate(self.latency_ms, self.failure_rate)
            span.set_attribute("charge.approved", approved)
            if approved:
                logger.info("cobrança aprovada order_id=%s", order_id)
            else:
                logger.warning("cobrança recusada order_id=%s", order_id)
            self._results[order_id] = approved
            return approved


class FakeEmailSender(BaseGateway):
    """E-mail fake: espera `latency_ms` e falha com probabilidade `failure_rate` (0 a 1)."""

    def __init__(self, latency_ms: int, failure_rate: float) -> None:
        """Define a latência média (ms) e a taxa de falha."""
        self.latency_ms = latency_ms
        self.failure_rate = failure_rate

    async def send(self, order_id: UUID, to: str, status: str) -> bool:
        """Envia o e-mail da mudança para `status`; `False` se o envio falhou."""
        with tracer.start_as_current_span("send_email") as span:
            span.set_attribute("order.id", str(order_id))
            span.set_attribute("order.status", status)
            logger.info("e-mail iniciado order_id=%s status=%s", order_id, status)
            sent = await self._simulate(self.latency_ms, self.failure_rate)
            span.set_attribute("email.sent", sent)
            if sent:
                logger.info("e-mail enviado order_id=%s status=%s", order_id, status)
            else:
                logger.warning("e-mail falhou order_id=%s status=%s", order_id, status)
            return sent
