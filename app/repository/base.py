"""Base dos repositórios: guarda a sessão em que eles operam."""

from sqlalchemy.ext.asyncio import AsyncSession


class Repository:
    """Repositório ligado a uma sessão; leitores e escritores herdam daqui."""

    def __init__(self, session: AsyncSession) -> None:
        """Guarda a sessão (de leitura para `*Reader`, de escrita para `*Writer`)."""
        self.session = session
