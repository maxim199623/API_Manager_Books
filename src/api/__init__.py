from src.DB.Repository.UserRepository.ORM import User # noqa: F401
from src.DB.Repository.BookRepository.ORM import Book # noqa: F401
from src.DB.Repository.BookChapterRepository.ORM import BookChapter # noqa: F401
from src.DB.Repository.LogRepository.ORM import LogEntry # noqa: F401


from fastapi import APIRouter
from src.api.route.users import router as user_router
from src.api.route.books import router as books_router
from src.api.route.settings import router as settings_router
from src.api.websocket.websocket import router as websocket_router

main_router = APIRouter()
main_router.include_router(websocket_router)
main_router.include_router(user_router)
main_router.include_router(books_router)
main_router.include_router(settings_router)
