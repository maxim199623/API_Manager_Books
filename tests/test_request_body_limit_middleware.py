from collections.abc import Iterable

import pytest
from fastapi import FastAPI, Request

from api_manager_books.api.request_body_limit import RequestBodyLimitMiddleware


def make_app() -> FastAPI:
    """Создает тестовое приложение с проверяемым middleware."""
    app = FastAPI()
    app.add_middleware(RequestBodyLimitMiddleware)

    @app.post("/form")
    async def form_endpoint(request: Request):
        form = await request.form()
        return {"fields": len(form)}

    return app


async def call_asgi_app(
    app: FastAPI,
    *,
    headers: Iterable[tuple[bytes, bytes]],
    body_chunks: list[bytes],
) -> tuple[int, bytes]:
    """Вызывает ASGI app без TestClient, чтобы не зависеть от httpx."""
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/form",
        "raw_path": b"/form",
        "query_string": b"",
        "headers": list(headers),
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    sent_messages = []
    chunks = list(body_chunks)

    async def receive():
        if chunks:
            body = chunks.pop(0)
            return {"type": "http.request", "body": body, "more_body": bool(chunks)}
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent_messages.append(message)

    await app(scope, receive, send)

    status = next(message["status"] for message in sent_messages if message["type"] == "http.response.start")
    body = b"".join(
        message.get("body", b"")
        for message in sent_messages
        if message["type"] == "http.response.body"
    )
    return status, body


@pytest.mark.asyncio
async def test_urlencoded_content_length_above_limit_returns_413():
    """Проверяет ранний 413 для большого form-urlencoded Content-Length."""
    app = make_app()

    status, _ = await call_asgi_app(
        app,
        headers=[
            (b"content-type", b"application/x-www-form-urlencoded"),
            (b"content-length", b"1048577"),
        ],
        body_chunks=[],
    )

    assert status == 413


@pytest.mark.asyncio
async def test_multipart_content_length_above_limit_returns_413():
    """Проверяет ранний 413 для большого multipart Content-Length."""
    app = make_app()

    status, _ = await call_asgi_app(
        app,
        headers=[
            (b"content-type", b"multipart/form-data; boundary=test"),
            (b"content-length", b"314572801"),
        ],
        body_chunks=[],
    )

    assert status == 413


@pytest.mark.asyncio
async def test_urlencoded_without_content_length_stops_after_limit():
    """Проверяет 413 при потоковом form-urlencoded без Content-Length."""
    app = make_app()

    status, _ = await call_asgi_app(
        app,
        headers=[(b"content-type", b"application/x-www-form-urlencoded")],
        body_chunks=[b"a=" + (b"x" * 1_048_576)],
    )

    assert status == 413
