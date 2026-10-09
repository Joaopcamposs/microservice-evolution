"""Configuração da aplicação lida de variáveis de ambiente.

Centraliza URL do banco e parâmetros das integrações fake (latência e taxa de
falha), para simular trabalho lento sem alterar código.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Parâmetros de execução; cada campo pode ser sobrescrito por variável de ambiente."""

    database_url: str = "postgresql+asyncpg://sales:sales@localhost:5432/sales"
    database_read_url: str | None = None
    payment_latency_min_ms: int = 300
    payment_latency_max_ms: int = 800
    payment_failure_rate: float = 0.1
    email_latency_min_ms: int = 100
    email_latency_max_ms: int = 300

    @property
    def read_url(self) -> str:
        """URL do banco de leitura; cai para o primário quando não há réplica configurada."""
        return self.database_read_url or self.database_url
