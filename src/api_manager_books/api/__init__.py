from fastapi import APIRouter
from api_manager_books.api.route.users import router as user_router
from api_manager_books.api.route.books import router as books_router
from api_manager_books.api.route.book_chapters import router as book_chapters_router
from api_manager_books.api.route.book_files import router as book_files_router
from api_manager_books.api.route.book_favorites import router as book_favorites_router
from api_manager_books.api.route.reading_history import router as reading_history_router
from api_manager_books.api.route.settings import router as settings_router
from api_manager_books.api.websocket.websocket import router as websocket_router

main_router = APIRouter()
main_router.include_router(websocket_router)
main_router.include_router(user_router)
main_router.include_router(books_router)
main_router.include_router(book_chapters_router)
main_router.include_router(book_files_router)
main_router.include_router(book_favorites_router)
main_router.include_router(reading_history_router)
main_router.include_router(settings_router)
