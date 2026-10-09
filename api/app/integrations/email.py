"""Envio de e-mail fake: só simula latência e registra em log."""

import asyncio
import logging
import random
from typing import Protocol
from uuid import UUID

from app.config import Settings

logger = logging.getLogger(__name__)


class EmailSender(Protocol):
    """Contrato de envio de e-mail de confirmação."""

    async def send_confirmation(self, sale_id: UUID, to: str) -> None:
        """Envia a confirmação da venda para `to`."""
        ...


class FakeEmailSender:
    """E-mail simulado com latência aleatória; nunca falha."""

    def __init__(self, settings: Settings) -> None:
        """Guarda os limites de latência vindos da configuração."""
        self._min_ms = settings.email_latency_min_ms
        self._max_ms = settings.email_latency_max_ms

    async def send_confirmation(self, sale_id: UUID, to: str) -> None:
        """Espera a latência simulada e registra o envio."""
        await asyncio.sleep(random.uniform(self._min_ms, self._max_ms) / 1000)
        logger.info("email enviado sale_id=%s to=%s", sale_id, to)
