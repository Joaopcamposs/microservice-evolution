"""Rotas de catálogo de produtos."""

from fastapi import APIRouter

from app.deps import CurrentUserId, ProductReaderDep, ProductServiceDep
from app.schemas import ProductIn, ProductOut

router = APIRouter(prefix="/products", tags=["products"])


@router.post(
    "",
    response_model=ProductOut,
    status_code=201,
    summary="Cadastra produto",
    description="Cria um produto (preço em centavos) em nome do usuário de `X-User-Id`.",
)
async def create_product(
    data: ProductIn,
    user_id: CurrentUserId,
    service: ProductServiceDep,
    reader: ProductReaderDep,
) -> ProductOut:
    """Cadastra um produto."""
    product = await reader.get(await service.create_product(user_id, data))
    assert product is not None
    return product


@router.get(
    "",
    response_model=list[ProductOut],
    summary="Lista produtos",
    description="Devolve todo o catálogo ordenado por id.",
)
async def list_products(reader: ProductReaderDep) -> list[ProductOut]:
    """Lista o catálogo."""
    return await reader.list_all()
