from collections.abc import Awaitable

from starlette.types import ASGIApp, Message, Receive, Scope, Send

FORM_URLENCODED_LIMIT_BYTES = 1024 * 1024
MULTIPART_LIMIT_BYTES = 300 * 1024 * 1024


class RequestBodyTooLargeError(Exception):
    """Тело запроса превысило разрешенный размер."""


class RequestBodyLimitMiddleware:
    """Ограничивает form/multipart body до парсинга FastAPI."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        form_urlencoded_limit: int = FORM_URLENCODED_LIMIT_BYTES,
        multipart_limit: int = MULTIPART_LIMIT_BYTES,
    ) -> None:
        self.app = app
        self.form_urlencoded_limit = form_urlencoded_limit
        self.multipart_limit = multipart_limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = self._limit_for_scope(scope)
        if limit is None:
            await self.app(scope, receive, send)
            return

        content_length = self._content_length(scope)
        if content_length is not None and content_length > limit:
            await self._send_413(send)
            return

        total_received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal total_received
            message = await receive()
            if message["type"] != "http.request":
                return message

            total_received += len(message.get("body", b""))
            if total_received > limit:
                raise RequestBodyTooLargeError
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except RequestBodyTooLargeError:
            if response_started:
                raise
            await self._send_413(send)

    def _limit_for_scope(self, scope: Scope) -> int | None:
        content_type = self._header(scope, b"content-type")
        if content_type is None:
            return None

        media_type = content_type.split(";", 1)[0].strip().lower()
        if media_type == "application/x-www-form-urlencoded":
            return self.form_urlencoded_limit
        if media_type == "multipart/form-data":
            return self.multipart_limit
        return None

    def _content_length(self, scope: Scope) -> int | None:
        raw_value = self._header(scope, b"content-length")
        if raw_value is None:
            return None
        try:
            return int(raw_value)
        except ValueError:
            return None

    @staticmethod
    def _header(scope: Scope, name: bytes) -> str | None:
        for header_name, value in scope["headers"]:
            if header_name.lower() == name:
                return value.decode("latin-1")
        return None

    @staticmethod
    def _send_413(send: Send) -> Awaitable[None]:
        async def send_response() -> None:
            await send(
                {
                    "type": "http.response.start",
                    "status": 413,
                    "headers": [(b"content-length", b"0")],
                }
            )
            await send({"type": "http.response.body", "body": b""})

        return send_response()
