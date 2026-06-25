import pytest

from api_manager_books.db.Repository.BookChapterFileRepository.ORM import (
    BookChapterFile,
    BookChapterFileChunk,
)
from api_manager_books.db.Repository.BookChapterRepository.ORM import BookChapter
from api_manager_books.db.Repository.BookRepository.ORM import Book


@pytest.mark.asyncio
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
