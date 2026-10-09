"""Modelos de borda (Pydantic): entrada HTTP e saída das consultas de leitura."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.sale import SaleStatus


class UserIn(BaseModel):
    """Payload de cadastro de usuário."""

    name: str = Field(min_length=1)
    email: str


class UserOut(BaseModel):
    """Usuário devolvido pela API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: str


class ProductIn(BaseModel):
    """Payload de cadastro de produto."""

    name: str = Field(min_length=1)
    price_cents: int = Field(gt=0)
    stock: int = Field(ge=0)


class ProductOut(BaseModel):
    """Produto devolvido pela API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    price_cents: int
    stock: int
    created_by: UUID


class SaleItemIn(BaseModel):
    """Item solicitado numa venda."""

    product_id: UUID
    quantity: int = Field(gt=0)


class SaleIn(BaseModel):
    """Payload de registro de venda; o comprador vem do header `X-User-Id`."""

    items: list[SaleItemIn] = Field(min_length=1)


class SaleItemOut(BaseModel):
    """Item de venda devolvido pela API."""

    model_config = ConfigDict(from_attributes=True)

    product_id: UUID
    quantity: int
    unit_price_cents: int


class SaleOut(BaseModel):
    """Venda devolvida pela API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    total_cents: int
    status: SaleStatus
    created_at: datetime
    items: list[SaleItemOut]
