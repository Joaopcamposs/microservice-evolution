"""Schemas Pydantic: formato de entrada e saída da API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.domain.status import OrderStatus


class UserCreate(BaseModel):
    """Dados para cadastrar um usuário; a senha só entra, nunca é devolvida."""

    name: str = Field(min_length=1, max_length=200)
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)


class UserRead(BaseModel):
    """Usuário devolvido pela API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: EmailStr
    created_at: datetime


class ProductCreate(BaseModel):
    """Dados para cadastrar um produto (preço em centavos)."""

    name: str = Field(min_length=1, max_length=200)
    price_cents: int = Field(gt=0)
    stock: int = Field(default=0, ge=0)


class ProductRead(BaseModel):
    """Produto devolvido pela API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    price_cents: int
    stock: int
    created_at: datetime


class OrderItemCreate(BaseModel):
    """Item pedido: produto e quantidade."""

    product_id: UUID
    quantity: int = Field(gt=0)


class OrderCreate(BaseModel):
    """Dados para criar um pedido; não aceita o mesmo produto em dois itens."""

    user_id: UUID
    items: list[OrderItemCreate] = Field(min_length=1)

    @field_validator("items")
    @classmethod
    def reject_duplicate_products(cls, items: list[OrderItemCreate]) -> list[OrderItemCreate]:
        """Exige produtos distintos; o cliente soma as quantidades."""
        ids = [i.product_id for i in items]
        if len(ids) != len(set(ids)):
            raise ValueError("product_id repetido nos itens")
        return items


class OrderItemRead(BaseModel):
    """Item de pedido devolvido pela API."""

    model_config = ConfigDict(from_attributes=True)

    product_id: UUID
    quantity: int
    unit_price_cents: int


class OrderRead(BaseModel):
    """Pedido devolvido pela API, com total calculado."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    status: OrderStatus
    total_cents: int
    created_at: datetime
    items: list[OrderItemRead]
