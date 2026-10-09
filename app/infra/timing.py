"""Middleware que devolve o tempo de processamento da request no header `X-Process-Time-Ms`."""

import time

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

HEADER = "X-Process-Time-Ms"


class ProcessTimeMiddleware:
    """ASGI puro (sem `BaseHTTPMiddleware`, que custa mais): mede do início até a resposta."""

    def __init__(self, app: ASGIApp) -> None:
        """Guarda a aplicação que será medida."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Mede requests HTTP e acrescenta o header ao iniciar a resposta."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start = time.perf_counter()

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                elapsed_ms = (time.perf_counter() - start) * 1000
                MutableHeaders(scope=message)[HEADER] = f"{elapsed_ms:.1f}"
            await send(message)

        await self.app(scope, receive, send_with_header)
