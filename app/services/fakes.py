"""Integrações fake (cobrança e e-mail): latência e taxa de falha configuráveis por env.

Simulam o trabalho lento e instável de serviços externos. Cada chamada vira um span OTel.
"""

import asyncio
import logging
import os
import random
from uuid import UUID

from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

CHARGE_LATENCY_MS = int(os.getenv("CHARGE_LATENCY_MS", "600"))
CHARGE_FAILURE_RATE = float(os.getenv("CHARGE_FAILURE_RATE", "0.1"))
EMAIL_LATENCY_MS = int(os.getenv("EMAIL_LATENCY_MS", "200"))
EMAIL_FAILURE_RATE = float(os.getenv("EMAIL_FAILURE_RATE", "0.05"))
# Variação da latência: ±40% em torno do valor configurado.
JITTER = 0.4


async def _simulate(latency_ms: int, failure_rate: float) -> bool:
    """Espera a latência (com variação) e devolve `True` se a chamada deu certo."""
    delay_ms = latency_ms * random.uniform(1 - JITTER, 1 + JITTER)
    await asyncio.sleep(delay_ms / 1000)
    return random.random() >= failure_rate


async def charge(order_id: UUID, amount_cents: int) -> bool:
    """Cobra o cliente; `False` se a cobrança foi recusada."""
    with tracer.start_as_current_span("charge") as span:
        span.set_attribute("order.id", str(order_id))
        span.set_attribute("order.amount_cents", amount_cents)
        logger.info("cobrança iniciada order_id=%s valor_cents=%d", order_id, amount_cents)
        approved = await _simulate(CHARGE_LATENCY_MS, CHARGE_FAILURE_RATE)
        span.set_attribute("charge.approved", approved)
        if approved:
            logger.info("cobrança aprovada order_id=%s", order_id)
        else:
            logger.warning("cobrança recusada order_id=%s", order_id)
        return approved


async def send_email(order_id: UUID, to: str, status: str) -> bool:
    """Envia o e-mail da mudança para `status`; `False` se o envio falhou."""
    with tracer.start_as_current_span("send_email") as span:
        span.set_attribute("order.id", str(order_id))
        span.set_attribute("order.status", status)
        logger.info("e-mail iniciado order_id=%s status=%s", order_id, status)
        sent = await _simulate(EMAIL_LATENCY_MS, EMAIL_FAILURE_RATE)
        span.set_attribute("email.sent", sent)
        if sent:
            logger.info("e-mail enviado order_id=%s status=%s", order_id, status)
        else:
            logger.warning("e-mail falhou order_id=%s status=%s", order_id, status)
        return sent
