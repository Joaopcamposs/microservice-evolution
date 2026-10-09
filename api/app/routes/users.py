"""Rotas de usuários."""

from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.deps import UserReaderDep, UserServiceDep
from app.schemas import UserIn, UserOut

router = APIRouter(prefix="/users", tags=["users"])


@router.post(
    "",
    response_model=UserOut,
    status_code=201,
    summary="Cadastra usuário",
    description="Cria um usuário com e-mail único. O id devolvido vai no header `X-User-Id`.",
)
async def create_user(data: UserIn, service: UserServiceDep, reader: UserReaderDep) -> UserOut:
    """Cadastra um usuário."""
    user = await reader.get(await service.register_user(data))
    assert user is not None
    return user


@router.get(
    "/{user_id}",
    response_model=UserOut,
    summary="Consulta usuário",
    description="Devolve o usuário pelo id.",
)
async def get_user(user_id: UUID, reader: UserReaderDep) -> UserOut:
    """Consulta um usuário."""
    user = await reader.get(user_id)
    if user is None:
        raise HTTPException(404, "usuário não encontrado")
    return user
