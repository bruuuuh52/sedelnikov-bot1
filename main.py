import asyncio
import logging
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

from bot.config import settings
from bot.config_loader import load_config
from bot.database import init_db
from bot.handlers import start_router, screening_router, admin_router


# Настройка логирования
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(dp: Dispatcher):
    """Lifespan для запуска/остановки."""
    # Startup
    logger.info("Starting bot...")
    await init_db()
    # Загружаем конфиг скрининга
    try:
        load_config()
        logger.info("Screening config loaded")
    except Exception as e:
        logger.error(f"Failed to load screening config: {e}")
        raise
    logger.info("Database initialized")

    yield

    # Shutdown
    logger.info("Shutting down bot...")


async def main():
    # Проверка токена
    if not settings.BOT_TOKEN:
        raise ValueError("BOT_TOKEN not set in .env")

    # Создаём бота и диспетчер
    bot = Bot(
        token=settings.BOT_TOKEN.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Регистрируем роутеры
    dp.include_router(start_router)
    dp.include_router(screening_router)
    dp.include_router(admin_router)

    # Запуск поллинга
    logger.info("Bot started polling...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.exception("Bot crashed: %s", e)
        raise