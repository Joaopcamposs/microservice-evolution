"""Classe base das entidades de domínio."""

from dataclasses import dataclass, field
from uuid import UUID

from app.domain.ids import new_id


@dataclass(slots=True, eq=False, kw_only=True)
class Entity:
    """Entidade com identidade: o `id` (UUID v7) nasce com o objeto, não no banco."""

    id: UUID = field(default_factory=new_id)
