"""Tradução dos erros de domínio para respostas HTTP, em um só lugar."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.domain.errors import (
    DomainError,
    EmailAlreadyExists,
    InsufficientStock,
    InvalidTransition,
    OrderNotFound,
    ProductsNotFound,
    UserNotFound,
)


class DomainErrorHandler:
    """Converte `DomainError` em resposta JSON `{"detail": ...}` com o status do tipo."""

    STATUS: dict[type[DomainError], int] = {
        UserNotFound: 404,
        OrderNotFound: 404,
        ProductsNotFound: 404,
        EmailAlreadyExists: 409,
        InsufficientStock: 409,
        InvalidTransition: 409,
    }

    @classmethod
    def register(cls, app: FastAPI) -> None:
        """Instala o tratador na aplicação."""
        app.add_exception_handler(DomainError, cls.handle)

    @classmethod
    async def handle(cls, request: Request, exc: Exception) -> JSONResponse:
        """Responde com o status do tipo do erro (500 se o tipo não estiver mapeado)."""
        return JSONResponse({"detail": str(exc)}, status_code=cls.STATUS.get(type(exc), 500))
