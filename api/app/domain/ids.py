"""Geração de identificadores: UUID v7 (ordenável por tempo), criado no domínio.

O Python 3.13 não tem `uuid.uuid7` (chega no 3.14), então usa-se `uuid-utils` e o
resultado é convertido para `uuid.UUID` da stdlib.
"""

from uuid import UUID

import uuid_utils


def new_id() -> UUID:
    """Gera um UUID v7: os 48 bits iniciais são o timestamp em ms (ordenável por tempo)."""
    return UUID(bytes=uuid_utils.uuid7().bytes)
