import pytest
import pytest_asyncio

from api_manager_books.db.Repository.BookChapterFileRepository.book_chapter_file_repository import (
    BookChapterFileRepository,
)
from api_manager_books.db.Repository.BookChapterFileRepository.ORM import (
    BookChapterFile,
    BookChapterFileChunk,
)
from api_manager_books.db.Repository.BookChapterRepository.ORM import BookChapter
from api_manager_books.db.Repository.BookRepository.ORM import Book

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def chapter_file_repo(repository_memory_session) -> BookChapterFileRepository:
    """Готовит репозиторий файлов глав."""
    return BookChapterFileRepository(repository_memory_session)


async def _create_chapter(repository_memory_session, chapter_number: int = 1) -> BookChapter:
    """Создает главу для проверки файлов."""
    book = Book(
        title=f"Test book {chapter_number}",
        author="Test author",
    )
    chapter = BookChapter(
        book=book,
        chapter=chapter_number,
        chapter_name=f"Chapter {chapter_number}",
        description="Chapter text",
    )

    repository_memory_session.add(book)
    await repository_memory_session.flush()
    await repository_memory_session.refresh(chapter)
    return chapter


async def test_chapter_file_models_can_be_persisted(repository_memory_session):
    book = Book(
        title="Test book",
        author="Test author",
    )
    chapter = BookChapter(
        book=book,
        chapter=1,
        chapter_name="Start",
        description="Chapter text",
    )
    chapter_file = BookChapterFile(
        chapter=chapter,
        file_name="chapter",
        extension="txt",
        content_type="text/plain",
        size=7,
        chunks_count=2,
    )
    chapter_file.chunks = [
        BookChapterFileChunk(chunk_index=0, data=b"abc"),
        BookChapterFileChunk(chunk_index=1, data=b"defg"),
    ]

    repository_memory_session.add(book)
    await repository_memory_session.commit()
    await repository_memory_session.refresh(chapter_file)

    assert chapter_file.id is not None
    assert chapter_file.chapter_id == chapter.id
    assert chapter_file.size == 7
    assert chapter_file.chunks_count == 2


async def test_one_chapter_can_store_multiple_files_with_same_name_and_extension(
    repository_memory_session,
    chapter_file_repo: BookChapterFileRepository,
):
    """Проверяет несколько файлов главы с одинаковым именем и расширением."""
    chapter = await _create_chapter(repository_memory_session)

    first = await chapter_file_repo.create_file(
        chapter.id,
        file_name="draft.PDF",
        content_type="application/pdf",
        chunks=[b"first"],
    )
    second = await chapter_file_repo.create_file(
        chapter.id,
        file_name="draft.PDF",
        content_type="application/pdf",
        chunks=[b"second"],
    )

    files = await chapter_file_repo.list_files(chapter.id)

    assert first.id != second.id
    assert {file.id for file in files} == {first.id, second.id}
    assert [file.file_name for file in files] == ["draft.PDF", "draft.PDF"]
    assert [file.extension for file in files] == ["pdf", "pdf"]


async def test_list_files_filters_by_extension_name_and_combined_filter(
    repository_memory_session,
    chapter_file_repo: BookChapterFileRepository,
):
    """Проверяет фильтры списка файлов главы."""
    chapter = await _create_chapter(repository_memory_session)

    final_pdf = await chapter_file_repo.create_file(
        chapter.id,
        file_name="report-final.PDF",
        content_type="application/pdf",
        chunks=[b"final pdf"],
    )
    draft_pdf = await chapter_file_repo.create_file(
        chapter.id,
        file_name="Report draft.pdf",
        content_type="application/pdf",
        chunks=[b"draft pdf"],
    )
    final_txt = await chapter_file_repo.create_file(
        chapter.id,
        file_name="final-notes.txt",
        content_type="text/plain",
        chunks=[b"final txt"],
    )

    pdf_files = await chapter_file_repo.list_files(chapter.id, extension="pdf")
    final_files = await chapter_file_repo.list_files(chapter.id, name="final")
    final_pdfs = await chapter_file_repo.list_files(
        chapter.id,
        name="final",
        extension=".PDF",
    )

    assert {file.id for file in pdf_files} == {final_pdf.id, draft_pdf.id}
    assert {file.id for file in final_files} == {final_pdf.id, final_txt.id}
    assert [file.id for file in final_pdfs] == [final_pdf.id]


async def test_create_file_stores_chunks_in_order_and_meta(
    repository_memory_session,
    chapter_file_repo: BookChapterFileRepository,
):
    """Проверяет метаданные и порядок чанков созданного файла."""
    chapter = await _create_chapter(repository_memory_session)

    created = await chapter_file_repo.create_file(
        chapter.id,
        file_name="Archive.Final.ZIP",
        content_type="application/zip",
        chunks=[b"abc", b"", b"defg", b"h"],
    )

    meta = await chapter_file_repo.get_file_meta(created.id)
    chunks = [chunk async for chunk in chapter_file_repo.iter_file_chunks(created.id)]
    is_valid = await chapter_file_repo.validate_integrity(created.id)

    assert meta == created
    assert created.chapter_id == chapter.id
    assert created.file_name == "Archive.Final.ZIP"
    assert created.extension == "zip"
    assert created.content_type == "application/zip"
    assert created.size == 8
    assert created.chunks_count == 3
    assert chunks == [b"abc", b"defg", b"h"]
    assert is_valid is True
