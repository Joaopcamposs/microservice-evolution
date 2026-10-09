"""Rotas de usuários: cadastro e consulta."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.domain.schemas import UserCreate, UserRead
from app.domain.user import User
from app.infra.database import ReadSessionDep, WriteSessionDep
from app.repository.users import UserReader
from app.services import handlers

router = APIRouter(prefix="/users", tags=["users"])


@router.post(
    "",
    response_model=UserRead,
    status_code=201,
    summary="Cadastra usuário",
    description="Cria um usuário. O e-mail é único (409 se já existir).",
)
async def create_user(data: UserCreate, session: WriteSessionDep) -> User:
    """Cadastra um usuário."""
    return await handlers.create_user(session, data)


@router.get(
    "",
    response_model=list[UserRead],
    summary="Consulta usuários",
    description=(
        "Com `id`, devolve só aquele usuário (lista vazia se não existir). "
        "Sem `id`, lista paginada, mais recentes primeiro."
    ),
)
async def list_users(
    session: ReadSessionDep,
    user_id: Annotated[UUID | None, Query(alias="id")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[User]:
    """Consulta usuários por id ou lista paginada; sempre devolve lista."""
    return await UserReader(session).list(user_id, limit, offset)
