"""Telegram update handlers."""

from app.handlers.base import router as base_router
from app.handlers.business import router as business_router
from app.handlers.deleted import router as deleted_router
from app.handlers.edited import router as edited_router
from app.handlers.messages import router as messages_router

__all__ = [
    "base_router",
    "business_router",
    "deleted_router",
    "edited_router",
    "messages_router",
]
