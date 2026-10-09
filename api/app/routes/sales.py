"""Rotas de vendas."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app.deps import CurrentUserId, SaleReaderDep, SaleServiceDep
from app.domain.sale import SaleStatus
from app.schemas import SaleIn, SaleOut

router = APIRouter(prefix="/sales", tags=["sales"])


@router.post(
    "",
    response_model=SaleOut,
    status_code=201,
    summary="Registra venda",
    description=(
        "Compra em nome do usuário de `X-User-Id`: valida estoque, grava a venda, cobra (fake) "
        "e envia e-mail (fake) dentro da request. Cobrança recusada deixa a venda "
        "PAYMENT_FAILED e devolve o estoque."
    ),
)
async def create_sale(
    data: SaleIn, user_id: CurrentUserId, service: SaleServiceDep, reader: SaleReaderDep
) -> SaleOut:
    """Registra e processa uma venda."""
    sale = await reader.get(await service.create_sale(user_id, data.items))
    assert sale is not None
    return sale


@router.get(
    "/{sale_id}",
    response_model=SaleOut,
    summary="Consulta venda",
    description="Devolve a venda com itens e status atual.",
)
async def get_sale(sale_id: UUID, reader: SaleReaderDep) -> SaleOut:
    """Consulta uma venda pelo id."""
    sale = await reader.get(sale_id)
    if sale is None:
        raise HTTPException(404, "venda não encontrada")
    return sale


@router.get(
    "",
    response_model=list[SaleOut],
    summary="Lista vendas",
    description="Lista vendas (mais recentes primeiro), filtradas por status e usuário, paginadas.",
)
async def list_sales(
    reader: SaleReaderDep,
    status: SaleStatus | None = None,
    user_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[SaleOut]:
    """Lista vendas filtradas e paginadas."""
    return await reader.search(status, user_id, limit, offset)
