import ast
import uuid
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile
from pydantic import ValidationError
from starlette.datastructures import Headers

from api_manager_books.api.route import book_files as book_files_route
from api_manager_books.api.route import books as books_route
from api_manager_books.api.route.books import get_books
from api_manager_books.application.services.book_file_service import BookFileNotFoundInServiceError
from api_manager_books.db.Repository.BookRepository.book_repository import (
    BOOK_BINARY_CHUNK_SIZE,
    BookNotFoundError,
)
from api_manager_books.schemas import books as book_shems
from api_manager_books.schemas.books import BookListRead
from api_manager_books.schemas.enums import UserRole
from api_manager_books.schemas.users import UserRead

EPUB_BYTES = b"PK\x03\x04epub-payload"
WEBP_BYTES = b"RIFF\x0c\x00\x00\x00WEBPpayload"


def test_books_route_imports_book_dtos_from_schemas_package() -> None:
    """Проверяет импорт DTO из пакета схем."""
    route_path = Path(books_route.__file__)
    tree = ast.parse(route_path.read_text(encoding="utf-8"))
    dto_names = {"BookCreate", "BookListRead", "BookMetadataUpdate"}

    service_imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "api_manager_books.application.services.book_service"
        for alias in node.names
    }
    schema_imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "api_manager_books.schemas.books"
        for alias in node.names
    }

    assert service_imports.isdisjoint(dto_names)
    assert dto_names <= schema_imports


@dataclass
class FakeBook:
    """Тестовая модель книги."""
    id: uuid.UUID
    title: str
    author: str | None
    description: str | None
    series: str | None
    genres: str | None
    format: str | None
    cover: bytes | None
    file: bytes | None
    created_at: datetime


class FakeBookRepo:
    """Фейковый репозиторий книг."""
    def __init__(self, books: list[FakeBook]):
        """Инициализирует тестовый объект."""
        self.books = books
        self.calls: list[dict[str, object]] = []

    async def list_books(
        self,
        *,
        author: str | None,
        series: str | None,
        offset: int = 0,
        limit: int = 100,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
        user_id: uuid.UUID | None = None,
    ) -> list[FakeBook]:
        """Имитирует получение списка книг."""
        self.calls.append(
            {
                "author": author,
                "series": series,
                "offset": offset,
                "limit": limit,
                "sort_by": sort_by,
                "sort_dir": sort_dir,
                "user_id": user_id,
            }
        )
        return self.books


class FakeFavoriteBookRepo:
    """Фейковый репозиторий избранных книг."""
    def __init__(self, favorite_ids: set[uuid.UUID]):
        """Инициализирует тестовый объект."""
        self.favorite_ids = favorite_ids
        self.calls: list[tuple[uuid.UUID, list[uuid.UUID]]] = []

    async def list_favorite_book_ids(
        self,
        user_id: uuid.UUID,
        book_ids: list[uuid.UUID],
    ) -> set[uuid.UUID]:
        """Имитирует получение ID избранных книг."""
        self.calls.append((user_id, book_ids))
        return self.favorite_ids


class FakeBookService:
    """Фейковый сервис книг."""
    def __init__(self, books=None):
        """Инициализирует тестовый объект."""
        self.books = books or []
        self.list_calls: list[dict[str, object]] = []

    async def list_books(
        self,
        *,
        user_id: uuid.UUID,
        author: str | None,
        series: str | None,
        offset: int,
        limit: int,
        sort_by: str,
        sort_dir: str,
    ):
        """Имитирует получение списка книг."""
        self.list_calls.append(
            {
                "user_id": user_id,
                "author": author,
                "series": series,
                "offset": offset,
                "limit": limit,
                "sort_by": sort_by,
                "sort_dir": sort_dir,
            }
        )
        return self.books


class FakeFavoriteService:
    """Фейковый сервис избранного."""
    def __init__(self, *, favorite_exists: bool = True, unfavorite_exists: bool = True):
        """Инициализирует тестовый объект."""
        self.favorite_exists = favorite_exists
        self.unfavorite_exists = unfavorite_exists
        self.favorite_calls: list[tuple[uuid.UUID, uuid.UUID]] = []
        self.unfavorite_calls: list[tuple[uuid.UUID, uuid.UUID]] = []

    async def favorite_book(self, user_id: uuid.UUID, book_id: uuid.UUID) -> None:
        """Имитирует добавление книги в избранное."""
        self.favorite_calls.append((user_id, book_id))
        if not self.favorite_exists:
            raise BookNotFoundError

    async def unfavorite_book(self, user_id: uuid.UUID, book_id: uuid.UUID) -> None:
        """Имитирует удаление книги из избранного."""
        self.unfavorite_calls.append((user_id, book_id))
        if not self.unfavorite_exists:
            raise BookNotFoundError


@dataclass(frozen=True)
class FakeBinaryMeta:
    """Тестовые метаданные бинарного файла."""
    content_type: str | None
    file_name: str | None
    size: int


class FakeBookFileService:
    """Фейковый сервис файлов книги."""
    def __init__(
        self,
        *,
        cover_meta: FakeBinaryMeta | None = None,
        file_meta: FakeBinaryMeta | None = None,
        cover_chunks: list[bytes] | None = None,
        file_chunks: list[bytes] | None = None,
        update_exists: bool = True,
    ):
        """Инициализирует тестовый объект."""
        self.cover_meta = cover_meta
        self.file_meta = file_meta
        self.cover_chunks = cover_chunks or []
        self.file_chunks = file_chunks or []
        self.update_exists = update_exists
        self.cover_updates = []
        self.file_updates = []

    async def get_cover_meta(self, book_id: uuid.UUID) -> FakeBinaryMeta | None:
        """Имитирует получение метаданных обложки."""
        return self.cover_meta

    async def get_file_meta(self, book_id: uuid.UUID) -> FakeBinaryMeta | None:
        """Имитирует получение метаданных файла."""
        return self.file_meta

    async def iter_cover_chunks(self, book_id: uuid.UUID):
        """Итерирует чанки тестовой обложки."""
        for chunk in self.cover_chunks:
            yield chunk

    async def iter_file_chunks(self, book_id: uuid.UUID):
        """Итерирует чанки тестового файла."""
        for chunk in self.file_chunks:
            yield chunk

    async def update_cover(self, user_id, book_id, content_type, cover_chunks):
        """Имитирует обновление обложки."""
        cover_data = [chunk async for chunk in cover_chunks]
        self.cover_updates.append(
            {
                "user_id": user_id,
                "book_id": book_id,
                "content_type": content_type,
                "cover_chunks": cover_data,
            }
        )
        if not self.update_exists:
            raise BookFileNotFoundInServiceError

    async def update_file(self, user_id, book_id, filename, content_type, file_chunks):
        """Имитирует обновление файла."""
        file_data = [chunk async for chunk in file_chunks]
        self.file_updates.append(
            {
                "user_id": user_id,
                "book_id": book_id,
                "filename": filename,
                "content_type": content_type,
                "file_chunks": file_data,
            }
        )
        if not self.update_exists:
            raise BookFileNotFoundInServiceError


def make_user() -> UserRead:
    """Создает тестового пользователя."""
    return UserRead(
        id=uuid.uuid4(),
        email="reader@example.com",
        role=UserRole.USER,
        is_active=True,
        created_at=datetime.now(),
    )


def make_admin() -> UserRead:
    """Создает тестового администратора."""
    return UserRead(
        id=uuid.uuid4(),
        email="admin@example.com",
        role=UserRole.ADMIN,
        is_active=True,
        created_at=datetime.now(),
    )


def make_book(title: str, author: str | None = None, series: str | None = None) -> FakeBook:
    """Создает тестовую книгу."""
    return FakeBook(
        id=uuid.uuid4(),
        title=title,
        author=author,
        description=None,
        series=series,
        genres=None,
        format="epub",
        cover=None,
        file=None,
        created_at=datetime.now(),
    )


def make_upload(filename: str, content: bytes, content_type: str) -> UploadFile:
    """Создает тестовую загрузку файла."""
    return UploadFile(
        filename=filename,
        file=BytesIO(content),
        headers=Headers({"content-type": content_type}),
    )


@pytest.mark.asyncio
async def test_get_books_marks_favorites_in_response():
    """Проверяет отметку избранного в ответе."""
    current_user = make_user()
    favorite_book = make_book("Favorite Book", author="Author A", series="Series A")
    regular_book = make_book("Regular Book", author="Author B", series="Series B")
    books = [
        BookListRead.model_validate(favorite_book, from_attributes=True).model_copy(
            update={"is_favorite": True}
        ),
        BookListRead.model_validate(regular_book, from_attributes=True),
    ]
    book_service = FakeBookService(books)

    result = await get_books(
        author=None,
        series=None,
        book_service=book_service,
        current_user=current_user,
    )

    assert [book.is_favorite for book in result] == [True, False]
    assert [book.id for book in result] == [favorite_book.id, regular_book.id]
    assert book_service.list_calls[0]["user_id"] == current_user.id


@pytest.mark.asyncio
async def test_get_books_returns_empty_list_without_favorite_lookup():
    """Проверяет список книг без запроса избранного."""
    current_user = make_user()
    book_service = FakeBookService([])

    result = await get_books(
        author=None,
        series=None,
        book_service=book_service,
        current_user=current_user,
    )

    assert result == []
    assert len(book_service.list_calls) == 1


@pytest.mark.asyncio
async def test_get_books_passes_author_and_series_filters_to_repository():
    """Проверяет передачу фильтров автора и серии."""
    current_user = make_user()
    book_service = FakeBookService([])

    await get_books(
        author="Arkady Strugatsky",
        series="Noon Universe",
        book_service=book_service,
        current_user=current_user,
    )

    assert book_service.list_calls == [
        {
            "user_id": current_user.id,
            "author": "Arkady Strugatsky",
            "series": "Noon Universe",
            "offset": 0,
            "limit": 100,
            "sort_by": "created_at",
            "sort_dir": "desc",
        }
    ]


@pytest.mark.asyncio
async def test_get_books_passes_sorting_to_repository():
    """Проверяет передачу сортировки в репозиторий."""
    current_user = make_user()
    book_service = FakeBookService([])

    await get_books(
        author=None,
        series=None,
        sort_by="progress",
        sort_dir="asc",
        book_service=book_service,
        current_user=current_user,
    )

    assert book_service.list_calls == [
        {
            "user_id": current_user.id,
            "author": None,
            "series": None,
            "offset": 0,
            "limit": 100,
            "sort_by": "progress",
            "sort_dir": "asc",
        }
    ]


@pytest.mark.asyncio
async def test_get_books_passes_pagination_to_repository():
    """Проверяет передачу пагинации в репозиторий."""
    current_user = make_user()
    book_service = FakeBookService([])

    await get_books(
        author=None,
        series=None,
        offset=20,
        limit=10,
        book_service=book_service,
        current_user=current_user,
    )

    assert book_service.list_calls == [
        {
            "user_id": current_user.id,
            "author": None,
            "series": None,
            "offset": 20,
            "limit": 10,
            "sort_by": "created_at",
            "sort_dir": "desc",
        }
    ]


@pytest.mark.asyncio
async def test_favorite_book_route_calls_service_with_current_user_id():
    """Проверяет вызов сервиса."""
    current_user = make_user()
    book_id = uuid.uuid4()
    favorite_service = FakeFavoriteService()

    result = await books_route.favorite_book(
        book_id=book_id,
        favorite_service=favorite_service,
        current_user=current_user,
    )

    assert result is None
    assert favorite_service.favorite_calls == [(current_user.id, book_id)]


@pytest.mark.asyncio
async def test_unfavorite_book_route_calls_service_with_current_user_id():
    """Проверяет вызов сервиса."""
    current_user = make_user()
    book_id = uuid.uuid4()
    favorite_service = FakeFavoriteService()

    result = await books_route.unfavorite_book(
        book_id=book_id,
        favorite_service=favorite_service,
        current_user=current_user,
    )

    assert result is None
    assert favorite_service.unfavorite_calls == [(current_user.id, book_id)]


@pytest.mark.asyncio
async def test_favorite_book_returns_404_when_book_missing():
    """Проверяет возврат 404 при ошибке."""
    current_user = make_user()
    book_id = uuid.uuid4()
    favorite_service = FakeFavoriteService(favorite_exists=False)

    with pytest.raises(HTTPException) as excinfo:
        await books_route.favorite_book(
            book_id=book_id,
            favorite_service=favorite_service,
            current_user=current_user,
        )

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Book not found"
    assert favorite_service.favorite_calls == [(current_user.id, book_id)]


@pytest.mark.asyncio
async def test_unfavorite_book_returns_404_when_book_missing():
    """Проверяет возврат 404 при ошибке."""
    current_user = make_user()
    book_id = uuid.uuid4()
    favorite_service = FakeFavoriteService(unfavorite_exists=False)

    with pytest.raises(HTTPException) as excinfo:
        await books_route.unfavorite_book(
            book_id=book_id,
            favorite_service=favorite_service,
            current_user=current_user,
        )

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Book not found"
    assert favorite_service.unfavorite_calls == [(current_user.id, book_id)]


@pytest.mark.asyncio
async def test_get_book_cover_streams_chunked_bytes_with_actual_mime():
    """Проверяет потоковую отдачу с реальным MIME."""
    book_file_service = FakeBookFileService(
        cover_meta=FakeBinaryMeta(content_type="image/webp", file_name=None, size=6),
        cover_chunks=[b"ab", b"cd", b"ef"],
    )

    response = await book_files_route.get_book_cover(
        book_id=uuid.uuid4(),
        book_file_service=book_file_service,
        current_user=make_user(),
    )

    body = b"".join([chunk async for chunk in response.body_iterator])

    assert response.media_type == "image/webp"
    assert body == b"abcdef"


@pytest.mark.asyncio
async def test_get_book_file_streams_chunked_bytes_and_sets_filename():
    """Проверяет имя файла в ответе."""
    book_file_service = FakeBookFileService(
        file_meta=FakeBinaryMeta(
            content_type="application/epub+zip",
            file_name="solo-leveling.epub",
            size=8,
        ),
        file_chunks=[b"Solo", b"Leve", b"ling"],
    )

    response = await book_files_route.get_book_file(
        book_id=uuid.uuid4(),
        book_file_service=book_file_service,
        current_user=make_user(),
    )

    body = b"".join([chunk async for chunk in response.body_iterator])

    assert response.media_type == "application/epub+zip"
    assert response.headers["Content-Disposition"] == 'attachment; filename="solo-leveling.epub"'
    assert body == b"SoloLeveling"


@pytest.mark.asyncio
async def test_get_book_file_sanitizes_unsafe_content_disposition_filename():
    """Проверяет безопасный заголовок скачивания файла книги."""
    book_file_service = FakeBookFileService(
        file_meta=FakeBinaryMeta(
            content_type="application/octet-stream",
            file_name='bad\r\n"name\\.epub',
            size=4,
        ),
        file_chunks=[b"data"],
    )

    response = await book_files_route.get_book_file(
        book_id=uuid.uuid4(),
        book_file_service=book_file_service,
        current_user=make_user(),
    )

    header = response.headers["Content-Disposition"]
    quoted = header.split('filename="', 1)[1].split('"', 1)[0]

    assert "\r" not in header
    assert "\n" not in header
    assert '"' not in quoted
    assert "\\" not in quoted


@pytest.mark.asyncio
async def test_update_book_cover_endpoint_replaces_cover_via_multipart():
    """Проверяет замену обложки через multipart."""
    book_id = uuid.uuid4()
    book_file_service = FakeBookFileService()
    current_user = make_admin()

    result = await book_files_route.update_book_cover(
        book_id=book_id,
        cover=make_upload("cover.webp", WEBP_BYTES, "image/webp"),
        book_file_service=book_file_service,
        current_user=current_user,
    )

    assert result is None
    assert book_file_service.cover_updates == [
        {
            "user_id": current_user.id,
            "book_id": book_id,
            "content_type": "image/webp",
            "cover_chunks": [WEBP_BYTES],
        }
    ]


@pytest.mark.asyncio
async def test_update_book_cover_rejects_invalid_signature_before_storage():
    """Проверяет отказ для поддельной обложки до записи."""
    book_file_service = FakeBookFileService()

    with pytest.raises(HTTPException) as excinfo:
        await book_files_route.update_book_cover(
            book_id=uuid.uuid4(),
            cover=make_upload("cover.png", b"MZ\x90\x00payload", "image/png"),
            book_file_service=book_file_service,
            current_user=make_admin(),
        )

    assert excinfo.value.status_code == 415
    assert book_file_service.cover_updates == []


@pytest.mark.asyncio
async def test_update_book_file_endpoint_replaces_file_via_chunked_multipart():
    """Проверяет замену файла через multipart."""
    book_id = uuid.uuid4()
    book_file_service = FakeBookFileService()
    current_user = make_admin()
    payload = EPUB_BYTES + (b"a" * (BOOK_BINARY_CHUNK_SIZE - len(EPUB_BYTES))) + b"tail"

    result = await book_files_route.update_book_file(
        book_id=book_id,
        file=make_upload("solo-leveling.epub", payload, "application/epub+zip"),
        book_file_service=book_file_service,
        current_user=current_user,
    )

    assert result is None
    assert book_file_service.file_updates == [
        {
            "user_id": current_user.id,
            "book_id": book_id,
            "filename": "solo-leveling.epub",
            "content_type": "application/epub+zip",
            "file_chunks": [payload[:-4], b"tail"],
        }
    ]


@pytest.mark.asyncio
async def test_update_book_file_rejects_disallowed_extension_before_storage():
    """Проверяет отказ до записи файла книги."""
    book_file_service = FakeBookFileService()

    with pytest.raises(HTTPException) as excinfo:
        await book_files_route.update_book_file(
            book_id=uuid.uuid4(),
            file=make_upload("payload.exe", b"bad", "application/octet-stream"),
            book_file_service=book_file_service,
            current_user=make_admin(),
        )

    assert excinfo.value.status_code == 415
    assert book_file_service.file_updates == []


def test_book_metadata_update_rejects_binary_fields_after_split_endpoints():
    """Проверяет запрет бинарных полей после разделения эндпоинтов."""
    payload_cls = book_shems.BookMetadataUpdate

    with pytest.raises(ValidationError):
        payload_cls.model_validate({"cover": "Y292ZXI=", "title": "Ignored"})


def test_book_metadata_update_accepts_metadata_fields():
    """Проверяет прием полей метаданных."""
    payload_cls = book_shems.BookMetadataUpdate

    payload = payload_cls.model_validate({"title": "Updated title", "description": "Changed"})

    assert payload.title == "Updated title"
    assert payload.description == "Changed"
