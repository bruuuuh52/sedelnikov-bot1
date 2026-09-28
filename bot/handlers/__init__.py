from bot.handlers.dynamic_start import router as start_router
from bot.handlers.dynamic_screening import router as screening_router
from bot.handlers.admin import router as admin_router

__all__ = ["start_router", "screening_router", "admin_router"]