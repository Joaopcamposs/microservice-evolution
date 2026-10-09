"""Configuração dos logs da aplicação (logger `app`) no stdout, nível por `LOG_LEVEL`."""

import logging
import os


def configure_logging() -> None:
    """Liga o logger `app` no stdout; o uvicorn só configura os logs dele.

    Os registros também sobem ao logger raiz, de onde o OpenTelemetry os exporta ao Loki.
    """
    logger = logging.getLogger("app")
    if logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
