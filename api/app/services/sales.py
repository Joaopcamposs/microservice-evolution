"""Caso de uso de escrita: venda (etapa 0, tudo síncrono dentro da request).

Fluxo: reserva estoque e grava PENDING (transação) -> cobra -> PAID/PAYMENT_FAILED
-> envia e-mail -> COMPLETED. Cobrança e e-mail são lentos e bloqueiam a resposta;
esse é o gargalo que as próximas etapas atacam. Cada passo usa sua própria transação.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from app.domain.errors import ProductNotFoundError, UserNotFoundError
from app.domain.repositories import UnitOfWork
from app.domain.sale import Sale, SaleItem
from app.integrations.email import EmailSender
from app.integrations.payment import PaymentGateway
from app.schemas import SaleItemIn

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PlacedSale:
    """Dados da venda recém-registrada necessários para cobrar e notificar."""

    sale_id: UUID
    total_cents: int
    user_email: str


class SaleService:
    """Orquestra registro, cobrança e notificação de uma venda."""

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        payment: PaymentGateway,
        email: EmailSender,
    ) -> None:
        """Recebe as dependências por injeção; não guarda estado mutável."""
        self._uow_factory = uow_factory
        self._payment = payment
        self._email = email

    async def create_sale(self, user_id: UUID, items: list[SaleItemIn]) -> UUID:
        """Registra, cobra e notifica uma venda; devolve o id (estado final no banco)."""
        placed = await self._place_sale(user_id, items)
        logger.info("venda registrada sale_id=%s", placed.sale_id)
        approved = await self._payment.charge(placed.sale_id, placed.total_cents)
        if not approved:
            await self._reject_sale(placed.sale_id)
            logger.info("cobranca recusada sale_id=%s", placed.sale_id)
            return placed.sale_id
        await self._pay_sale(placed.sale_id)
        await self._email.send_confirmation(placed.sale_id, placed.user_email)
        await self._complete_sale(placed.sale_id)
        logger.info("venda concluida sale_id=%s", placed.sale_id)
        return placed.sale_id

    async def _place_sale(self, user_id: UUID, items: list[SaleItemIn]) -> PlacedSale:
        """Reserva estoque e grava a venda PENDING numa única transação."""
        async with self._uow_factory() as uow:
            user = await uow.users.get(user_id)
            if user is None:
                raise UserNotFoundError(user_id)
            products = {
                p.id: p
                for p in await uow.products.get_many_for_update([i.product_id for i in items])
            }
            sale_items: list[SaleItem] = []
            for requested in items:
                product = products.get(requested.product_id)
                if product is None:
                    raise ProductNotFoundError(requested.product_id)
                product.reserve(requested.quantity)
                sale_items.append(
                    SaleItem(requested.product_id, requested.quantity, product.price_cents)
                )
            sale = Sale.place(user_id, sale_items)
            for product in products.values():
                await uow.products.save(product)
            await uow.sales.add(sale)
            return PlacedSale(sale.id, sale.total_cents, user.email)

    async def _pay_sale(self, sale_id: UUID) -> None:
        """Marca a venda como paga."""
        async with self._uow_factory() as uow:
            sale = await self._load_sale(uow, sale_id)
            sale.mark_paid()
            await uow.sales.save(sale)

    async def _complete_sale(self, sale_id: UUID) -> None:
        """Marca a venda como concluída."""
        async with self._uow_factory() as uow:
            sale = await self._load_sale(uow, sale_id)
            sale.complete()
            await uow.sales.save(sale)

    async def _reject_sale(self, sale_id: UUID) -> None:
        """Marca PAYMENT_FAILED e devolve o estoque reservado, atomicamente."""
        async with self._uow_factory() as uow:
            sale = await self._load_sale(uow, sale_id)
            sale.mark_payment_failed()
            await uow.sales.save(sale)
            products = await uow.products.get_many_for_update([i.product_id for i in sale.items])
            quantities = {i.product_id: i.quantity for i in sale.items}
            for product in products:
                product.restore(quantities[product.id])
                await uow.products.save(product)

    async def _load_sale(self, uow: UnitOfWork, sale_id: UUID) -> Sale:
        """Carrega a venda; ela existe porque acabou de ser criada neste fluxo."""
        sale = await uow.sales.get(sale_id)
        assert sale is not None
        return sale
